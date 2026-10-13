"""Exercise optional telemetry, dynamic entities and GPS consent in real HA."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from test_init import add_entry
from test_telemetry import gps_payload, wan_payload

from custom_components.cradlepoint.api import (
    CannotConnect,
    InvalidAuth,
    InvalidResponse,
    ProductInfo,
    UnsupportedEndpoint,
)
from custom_components.cradlepoint.const import DOMAIN
from custom_components.cradlepoint.diagnostics import async_get_config_entry_diagnostics


def readings(**changes: object) -> dict[str, object]:
    """Provide synthetic documented telemetry, never hardware claims."""
    return {
        "fw_info": {"major_version": 7, "minor_version": 26, "patch_version": 0},
        "wan/devices": wan_payload(),
        "wan/primary_device": "device-a",
        "wan/connection_state": "connected",
        "gps": gps_payload(),
        **changes,
    }


def mock_readings(api: AsyncMock, values: dict[str, object]) -> None:
    """Return synthetic endpoint data or raise a safe transport error."""

    async def fetch(path: str) -> object:
        value = values[path]
        if isinstance(value, Exception):
            raise value
        return value

    api.side_effect = fetch


def entity_id(hass: HomeAssistant, suffix: str) -> str:
    """Look up stable serial-based IDs instead of guessing display names."""
    result = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"SERIAL-001_{suffix}"
    )
    assert result
    return result


def sensor_state(hass: HomeAssistant, suffix: str) -> str:
    """Read the real HA sensor state."""
    state = hass.states.get(entity_id(hass, suffix))
    assert state
    return state.state


async def test_optional_and_dynamic_wan(
    hass: HomeAssistant, product_api: AsyncMock, optional_api: AsyncMock
) -> None:
    """Discover later WAN devices and safely handle removals, gaps and resets."""
    values = readings()
    values["wan/devices"] = {}
    mock_readings(optional_api, values)
    entry = add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert sensor_state(hass, "firmware") == "7.26.0"
    assert sensor_state(hass, "primary") == "device-a"
    assert sensor_state(hass, "wan_state") == "connected"
    assert not any(call.args == ("gps",) for call in optional_api.await_args_list)
    values["wan/devices"] = wan_payload()
    with patch(
        "custom_components.cradlepoint.coordinator.time.monotonic", return_value=100
    ):
        await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert sensor_state(hass, "device-a_wan_received") == "100"
    assert sensor_state(hass, "device-a_wan_received_rate") == "unknown"
    assert sensor_state(hass, "device-a_wan_connection") == "connected"
    assert sensor_state(hass, "device-a_wan_transport") == "ethernet"
    wan_id = entity_id(hass, "device-a_wan_received")
    values["wan/devices"] = wan_payload(220, 440)
    with patch(
        "custom_components.cradlepoint.coordinator.time.monotonic", return_value=160
    ):
        await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert sensor_state(hass, "device-a_wan_received_rate") == "2.0"
    assert sensor_state(hass, "device-a_wan_sent_rate") == "4.0"
    values["wan/devices"] = {}
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert sensor_state(hass, "device-a_wan_received") == "unavailable"
    values["wan/devices"] = wan_payload(10, None)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert entity_id(hass, "device-a_wan_received") == wan_id
    assert sensor_state(hass, "device-a_wan_sent") == "unknown"
    assert sensor_state(hass, "device-a_wan_received_rate") == "unknown"
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics == {"product_name": "E300", "last_update_success": True}
    assert "device-a" not in repr(diagnostics)
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "failure", [UnsupportedEndpoint(), CannotConnect(), InvalidResponse(), []]
)
async def test_optional_failure_isolation_and_recovery(
    hass: HomeAssistant,
    product_api: AsyncMock,
    optional_api: AsyncMock,
    failure: object,
) -> None:
    """Optional schema/network/unsupported failures never stale or break product."""
    values = readings()
    mock_readings(optional_api, values)
    entry = add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    values["wan/devices"] = failure
    values["fw_info"] = failure
    values["wan/primary_device"] = failure
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert sensor_state(hass, "product_name") == "E300"
    assert sensor_state(hass, "wan_state") == "connected"
    for suffix in ("device-a_wan_link", "firmware", "primary"):
        assert sensor_state(hass, suffix) == "unavailable"
    values.update(readings())
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert sensor_state(hass, "device-a_wan_received_rate") == "unknown"
    assert sensor_state(hass, "device-a_wan_link") == "up"


@pytest.mark.parametrize("endpoint", ["fw_info", "wan/devices", "gps"])
async def test_optional_authentication(
    hass: HomeAssistant, product_api: AsyncMock, optional_api: AsyncMock, endpoint: str
) -> None:
    """Every optional endpoint's auth failure triggers HA reauthentication."""
    values = readings()
    mock_readings(optional_api, values)
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    values[endpoint] = InvalidAuth()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert sensor_state(hass, "product_name") == "unavailable"
    assert any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )


async def test_identity_precedes_optional_reads(
    hass: HomeAssistant, product_api: AsyncMock, optional_api: AsyncMock
) -> None:
    """Reject a different router before making any telemetry requests."""
    entry = add_entry(hass)
    product_api.return_value = ProductInfo("OTHER", "IBR1700-600M")
    assert not await hass.config_entries.async_setup(entry.entry_id)
    optional_api.assert_not_awaited()


@pytest.mark.parametrize("major", [6, 7])
async def test_experimental_family_and_wan_types(
    hass: HomeAssistant, product_api: AsyncMock, optional_api: AsyncMock, major: int
) -> None:
    """Exercise generic contracts for synthetic targets without certifying them."""
    product_api.return_value = ProductInfo("SERIAL-001", "IBR1700-600M")
    values = readings()
    values["fw_info"] = {"major_version": major, "minor_version": 1, "patch_version": 0}
    values["wan/devices"] = {
        **wan_payload(),
        "mdm-not-classified": {
            "info": {"type": "unverified-wifi-type"},
            "status": {"connection_state": "connecting", "link_state": "unknown"},
            "stats": {},
        },
        "device-b": {
            "info": {"type": "mdm"},
            "status": {"connection_state": "disconnected", "link_state": "down"},
            "stats": {"in": 0, "out": 0},
        },
    }
    mock_readings(optional_api, values)
    entry = add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert sensor_state(hass, "product_name") == "IBR1700-600M"
    assert sensor_state(hass, "firmware") == f"{major}.1.0"
    assert sensor_state(hass, "mdm-not-classified_wan_transport") == "unknown"
    assert sensor_state(hass, "mdm-not-classified_wan_received") == "unknown"
    assert sensor_state(hass, "device-b_wan_transport") == "mdm"
    assert sensor_state(hass, "device-b_wan_received") == "0"
    assert sensor_state(hass, "device-b_wan_received_rate") == "unknown"
    product_api.assert_awaited_once()
    assert optional_api.await_count == 4
    assert len(er.async_get(hass).entities) == 25
    assert "PRIVATE" not in repr(entry.runtime_data.data)


async def test_gps_options_reload_and_privacy(
    hass: HomeAssistant, product_api: AsyncMock, optional_api: AsyncMock
) -> None:
    """Consent creates GPS entities, reloads, and disabling stops GPS requests."""
    values = readings()
    mock_readings(optional_api, values)
    entry = add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["data_schema"]({}) == {"gps_enabled": False}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"gps_enabled": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert sensor_state(hass, "gps_latitude") == "0.0"
    assert sensor_state(hass, "gps_longitude") == "-0.5"
    assert sensor_state(hass, "gps_speed") == "2.0"
    assert sensor_state(hass, "gps_lock") == "True"
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert set(diagnostics) == {"product_name", "last_update_success"}
    values["gps"] = gps_payload(lock=False)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert sensor_state(hass, "gps_latitude") == "unavailable"
    assert sensor_state(hass, "gps_lock") == "False"
    values["gps"] = CannotConnect()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert sensor_state(hass, "gps_lock") == "unavailable"
    values["gps"] = gps_payload()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert sensor_state(hass, "gps_latitude") == "0.0"
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["data_schema"]({}) == {"gps_enabled": True}
    await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"gps_enabled": False}
    )
    await hass.async_block_till_done()
    optional_api.reset_mock()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert not any(call.args == ("gps",) for call in optional_api.await_args_list)
    assert sensor_state(hass, "gps_latitude") == "unavailable"
