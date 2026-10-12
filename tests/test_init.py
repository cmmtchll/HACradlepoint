"""Integration lifecycle, coordinator, entity and privacy tests."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cradlepoint.api import (
    CannotConnect,
    InvalidAuth,
    InvalidResponse,
    ProductInfo,
)
from custom_components.cradlepoint.const import DOMAIN, UPDATE_INTERVAL
from custom_components.cradlepoint.diagnostics import async_get_config_entry_diagnostics

DATA = {"origin": "https://router", "username": "admin", "password": "secret"}


def add_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Add a configured router to Home Assistant."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="SERIAL-001", data=DATA, title="E300"
    )
    entry.add_to_hass(hass)
    return entry


async def test_setup_and_unload(hass: HomeAssistant, product_api: AsyncMock) -> None:
    """Create a diagnostic entity and physical device with stable identifiers."""
    entry = add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.update_interval == UPDATE_INTERVAL
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, "SERIAL-001_product_name"
    )
    assert entity_id is not None
    entity = registry.async_get(entity_id)
    assert entity is not None
    assert entity.entity_category.value == "diagnostic"
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "E300"
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, "SERIAL-001"), entry.entry_id
    )
    assert device is not None
    assert device.manufacturer == "CradlePoint"
    assert device.model == "E300"
    assert device.serial_number == "SERIAL-001"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    unloaded_state = hass.states.get(entity_id)
    assert unloaded_state is not None
    assert unloaded_state.state == "unavailable"
    assert unloaded_state.attributes["restored"] is True


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (CannotConnect(), ConfigEntryState.SETUP_RETRY),
        (InvalidResponse(), ConfigEntryState.SETUP_RETRY),
        (InvalidAuth(), ConfigEntryState.SETUP_ERROR),
    ],
)
async def test_first_refresh_errors(
    hass: HomeAssistant,
    product_api: AsyncMock,
    error: Exception,
    expected: ConfigEntryState,
) -> None:
    """Require first-refresh success and trigger reauthentication on auth errors."""
    entry = add_entry(hass)
    product_api.side_effect = error
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is expected
    assert not er.async_get(hass).entities
    if isinstance(error, InvalidAuth):
        flows = hass.config_entries.flow.async_progress()
        assert any(flow["context"]["source"] == "reauth" for flow in flows)


@pytest.mark.parametrize(
    "error",
    [CannotConnect(), InvalidResponse(), ProductInfo("OTHER", "E300"), InvalidAuth()],
)
async def test_unavailable_and_recovery(
    hass: HomeAssistant, product_api: AsyncMock, error: object
) -> None:
    """Mark entities unavailable on errors and recover after a same-router read."""
    entry = add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, "SERIAL-001_product_name"
    )
    assert entity_id
    if isinstance(error, Exception):
        product_api.side_effect = error
    else:
        product_api.return_value = error
    await entry.runtime_data.async_request_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unavailable"
    product_api.side_effect = None
    product_api.return_value = ProductInfo("SERIAL-001", "E300 updated")
    await entry.runtime_data.async_request_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "E300 updated"


async def test_diagnostics(hass: HomeAssistant, product_api: AsyncMock) -> None:
    """Allowlist diagnostic fields rather than including entry data or raw JSON."""
    entry = add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics == {"product_name": "E300", "last_update_success": True}
    assert all(
        value not in str(diagnostics)
        for value in ["router", "admin", "secret", "SERIAL-001"]
    )


async def test_unload_failure(hass: HomeAssistant, product_api: AsyncMock) -> None:
    """Return platform unload failure without pretending the entry was unloaded."""
    entry = add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=False
    ):
        assert not await hass.config_entries.async_unload(entry.entry_id)
