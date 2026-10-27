"""GPS tracker identity, location, consent and freshness in real Home Assistant."""

from unittest.mock import AsyncMock, patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from test_init import add_entry
from test_optional import mock_readings, readings
from test_telemetry import gps_payload

from custom_components.cradlepoint.api import (
    CannotConnect,
    InvalidAuth,
    InvalidResponse,
    ProductInfo,
)
from custom_components.cradlepoint.const import DOMAIN
from custom_components.cradlepoint.diagnostics import async_get_config_entry_diagnostics


def tracker_state(hass: HomeAssistant) -> State:
    """Find the tracker by its stable registry identity."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "device_tracker", DOMAIN, "SERIAL-001_gps_location"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    return state


def assert_no_position(hass: HomeAssistant) -> None:
    """Unavailable tracker states must not retain either coordinate."""
    state = tracker_state(hass)
    assert state.state == "unavailable"
    assert "latitude" not in state.attributes
    assert "longitude" not in state.attributes


async def test_tracker_disabled_by_default(
    hass: HomeAssistant, product_api: AsyncMock, optional_api: AsyncMock
) -> None:
    """No tracker or GPS request exists without explicit location consent."""
    entry = add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.states.async_entity_ids("device_tracker")
    assert not any(
        entity.domain == "device_tracker"
        for entity in er.async_get(hass).entities.values()
    )
    assert not any(call.args == ("gps",) for call in optional_api.await_args_list)


async def test_tracker_location_identity_and_reload(
    hass: HomeAssistant, product_api: AsyncMock, optional_api: AsyncMock
) -> None:
    """Combine coordinates on the existing device, retaining identity on reload."""
    values = readings()
    mock_readings(optional_api, values)
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = tracker_state(hass)
    assert state.state == "not_home"
    assert state.attributes["source_type"] == "gps"
    assert state.attributes["latitude"] == 0.0
    assert state.attributes["longitude"] == -0.5
    registry_entry = er.async_get(hass).async_get(state.entity_id)
    assert registry_entry is not None
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, "SERIAL-001"), entry.entry_id
    )
    assert device is not None
    assert registry_entry.device_id == device.id
    assert len(dr.async_get(hass).devices) == 1
    assert sum(call.args == ("gps",) for call in optional_api.await_args_list) == 1
    gps = entry.runtime_data.gps
    assert gps is not None
    values["gps"] = gps_payload(
        latitude={"degree": "1", "minute": "0", "second": "0"},
        longitude={"degree": "0", "minute": "0", "second": "0"},
    )
    await gps.async_refresh()
    assert tracker_state(hass).attributes["latitude"] == 1.0
    assert tracker_state(hass).attributes["longitude"] == 0.0
    assert await async_get_config_entry_diagnostics(hass, entry) == {
        "product_name": "E300",
        "last_update_success": True,
    }
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert tracker_state(hass).entity_id == state.entity_id
    assert len(hass.states.async_entity_ids("device_tracker")) == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert_no_position(hass)
    optional_api.reset_mock()
    await gps.async_refresh()
    optional_api.assert_not_awaited()


@pytest.mark.parametrize(
    "fix",
    [
        {"lock": False},
        {"age": None},
        {"age": 120},
        {"latitude": None},
        {"longitude": None},
    ],
)
async def test_tracker_invalid_fix_and_recovery(
    hass: HomeAssistant,
    product_api: AsyncMock,
    optional_api: AsyncMock,
    fix: dict[str, object],
) -> None:
    """Reject unlocked, stale and incomplete fixes without caching coordinates."""
    values = readings()
    mock_readings(optional_api, values)
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    gps = entry.runtime_data.gps
    assert gps is not None
    values["gps"] = gps_payload(**fix)
    await gps.async_refresh()
    assert_no_position(hass)
    values["gps"] = gps_payload()
    await gps.async_refresh()
    assert tracker_state(hass).attributes["longitude"] == -0.5


@pytest.mark.parametrize(
    "failure", [CannotConnect(), InvalidResponse(), [], InvalidAuth()]
)
async def test_tracker_failure_and_recovery(
    hass: HomeAssistant,
    product_api: AsyncMock,
    optional_api: AsyncMock,
    failure: object,
) -> None:
    """API failures redact location, and authentication starts reauthentication."""
    values = readings(gps=failure)
    mock_readings(optional_api, values)
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert_no_position(hass)
    if isinstance(failure, InvalidAuth):
        assert any(
            flow["context"]["source"] == "reauth"
            for flow in hass.config_entries.flow.async_progress()
        )
    gps = entry.runtime_data.gps
    assert gps is not None
    values["gps"] = gps_payload()
    await gps.async_refresh()
    assert tracker_state(hass).attributes["latitude"] == 0.0
    values["gps"] = failure
    await gps.async_refresh()
    assert_no_position(hass)


async def test_tracker_wrong_router(
    hass: HomeAssistant, product_api: AsyncMock, optional_api: AsyncMock
) -> None:
    """Changed router identity prevents GPS reads and removes a previous position."""
    mock_readings(optional_api, readings())
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    gps = entry.runtime_data.gps
    assert gps is not None
    product_api.return_value = ProductInfo("OTHER", "Other router")
    optional_api.reset_mock()
    await gps.async_refresh()
    optional_api.assert_not_awaited()
    assert_no_position(hass)
    product_api.return_value = ProductInfo("SERIAL-001", "E300")
    await gps.async_refresh()
    assert tracker_state(hass).attributes["latitude"] == 0.0


async def test_tracker_freshness_expiry(
    hass: HomeAssistant,
    product_api: AsyncMock,
    optional_api: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The freshness callback removes location without another GPS request."""
    mock_readings(optional_api, readings(gps=gps_payload(age=119)))
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert tracker_state(hass).attributes["latitude"] == 0.0
    count = optional_api.await_count
    freezer.tick(2)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert_no_position(hass)
    assert optional_api.await_count == count


@pytest.mark.parametrize("unload_success", [False, True])
async def test_tracker_consent_revocation(
    hass: HomeAssistant,
    product_api: AsyncMock,
    optional_api: AsyncMock,
    unload_success: bool,
) -> None:
    """Disabling GPS immediately redacts the tracker, even if unload fails."""
    mock_readings(optional_api, readings())
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    gps = entry.runtime_data.gps
    assert gps is not None
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    if unload_success:
        await hass.config_entries.options.async_configure(
            flow["flow_id"], user_input={"gps_enabled": False}
        )
        await hass.async_block_till_done()
    else:
        with patch.object(
            hass.config_entries, "async_unload_platforms", return_value=False
        ):
            await hass.config_entries.options.async_configure(
                flow["flow_id"], user_input={"gps_enabled": False}
            )
            await hass.async_block_till_done()
    assert_no_position(hass)
    optional_api.reset_mock()
    await gps.async_refresh()
    optional_api.assert_not_awaited()
