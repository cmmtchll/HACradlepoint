"""Independent GPS scheduling, consent, freshness and task lifecycle tests."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from test_device_tracker import assert_no_position, tracker_state
from test_init import add_entry
from test_optional import mock_readings, readings, sensor_state
from test_telemetry import gps_payload

from custom_components.cradlepoint.api import (
    CannotConnect,
    InvalidAuth,
    InvalidResponse,
    ProductInfo,
)
from custom_components.cradlepoint.const import UPDATE_INTERVAL


async def test_scheduled_priority_gps(
    hass: HomeAssistant,
    product_api: AsyncMock,
    optional_api: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A real scheduled GPS update publishes while a WAN refresh is blocked."""
    values = readings()
    mock_readings(optional_api, values)
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    gps = entry.runtime_data.gps
    assert gps is not None
    assert gps.update_interval == UPDATE_INTERVAL
    updated = asyncio.Event()
    entry.async_on_unload(gps.async_add_listener(updated.set))
    blocked = asyncio.Event()
    release = asyncio.Event()

    async def fetch(path: str) -> object:
        if path == "fw_info":
            blocked.set()
            await release.wait()
        return values[path]

    optional_api.side_effect = fetch
    refresh = asyncio.create_task(entry.runtime_data.async_refresh())
    await blocked.wait()
    values["gps"] = gps_payload(latitude={"degree": "1", "minute": "0", "second": "0"})
    freezer.tick(UPDATE_INTERVAL.total_seconds() + 1)
    async_fire_time_changed(hass, dt_util.utcnow())
    await updated.wait()
    await hass.async_block_till_done()
    assert not refresh.done()
    assert sensor_state(hass, "gps_latitude") == "1.0"
    assert tracker_state(hass).attributes["latitude"] == 1.0
    updated.clear()
    values["gps"] = gps_payload(lock=False)
    freezer.tick(UPDATE_INTERVAL.total_seconds() + 1)
    async_fire_time_changed(hass, dt_util.utcnow())
    await updated.wait()
    await hass.async_block_till_done()
    assert not refresh.done()
    assert sensor_state(hass, "gps_lock") == "False"
    assert sensor_state(hass, "gps_latitude") == "unavailable"
    assert_no_position(hass)
    values["gps"] = gps_payload()
    await gps.async_refresh()
    assert sensor_state(hass, "gps_latitude") == "0.0"
    assert tracker_state(hass).attributes["latitude"] == 0.0
    release.set()
    await refresh
    assert await hass.config_entries.async_unload(entry.entry_id)
    count = optional_api.await_count
    freezer.tick(300)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert optional_api.await_count == count
    assert gps._expiry is None


@pytest.mark.parametrize("failure", [CannotConnect(), InvalidResponse(), []])
async def test_gps_failure_recovery_and_identity(
    hass: HomeAssistant,
    product_api: AsyncMock,
    optional_api: AsyncMock,
    failure: object,
) -> None:
    """GPS errors affect only GPS, and wrong identity prevents location reads."""
    values = readings()
    mock_readings(optional_api, values)
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    gps = entry.runtime_data.gps
    assert gps is not None
    values["gps"] = failure
    await gps.async_refresh()
    assert sensor_state(hass, "gps_latitude") == "unavailable"
    assert sensor_state(hass, "product_name") == "E300"
    values["gps"] = gps_payload()
    await gps.async_refresh()
    assert sensor_state(hass, "gps_latitude") == "0.0"
    product_api.return_value = ProductInfo("OTHER", "Other router")
    optional_api.reset_mock()
    await gps.async_refresh()
    optional_api.assert_not_awaited()
    assert sensor_state(hass, "gps_latitude") == "unavailable"


async def test_real_options_revocation_survives_failed_reload(
    hass: HomeAssistant,
    product_api: AsyncMock,
    optional_api: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Real automatic reload failure cannot preserve GPS reads or publications."""
    mock_readings(optional_api, readings())
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    gps = entry.runtime_data.gps
    assert gps is not None
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=False
    ):
        result = await hass.config_entries.options.async_configure(
            flow["flow_id"], user_input={"gps_enabled": False}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
    assert entry.options["gps_enabled"] is False
    assert entry.runtime_data.gps is gps
    assert sensor_state(hass, "gps_latitude") == "unavailable"
    assert gps.data is None
    optional_api.reset_mock()
    for _ in range(2):
        freezer.tick(UPDATE_INTERVAL.total_seconds() + 1)
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
        assert sensor_state(hass, "gps_latitude") == "unavailable"
        assert_no_position(hass)
        assert gps.current_fix is None
    assert not any(call.args == ("gps",) for call in optional_api.await_args_list)
    assert not entry.update_listeners


async def test_initial_gps_failure_does_not_block_router_setup(
    hass: HomeAssistant, product_api: AsyncMock, optional_api: AsyncMock
) -> None:
    """An unavailable optional GPS endpoint does not prevent loading entities."""
    values = readings(gps=CannotConnect())
    mock_readings(optional_api, values)
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert sensor_state(hass, "gps_latitude") == "unavailable"
    assert sensor_state(hass, "product_name") == "E300"
    gps = entry.runtime_data.gps
    assert gps is not None
    values["gps"] = gps_payload()
    await gps.async_refresh()
    assert sensor_state(hass, "gps_latitude") == "0.0"


async def test_revoke_during_request_and_failed_unload(
    hass: HomeAssistant, product_api: AsyncMock, optional_api: AsyncMock
) -> None:
    """Live revocation redacts entities and rejects an already in-flight fix."""
    values = readings()
    mock_readings(optional_api, values)
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    gps = entry.runtime_data.gps
    assert gps is not None
    started = asyncio.Event()
    release = asyncio.Event()

    async def fetch(path: str) -> object:
        started.set()
        await release.wait()
        return values[path]

    optional_api.side_effect = fetch
    refresh = asyncio.create_task(gps.async_refresh())
    await started.wait()
    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=False
    ):
        hass.config_entries.async_update_entry(entry, options={"gps_enabled": False})
        assert sensor_state(hass, "gps_latitude") == "unavailable"
        assert not await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
    assert sensor_state(hass, "gps_latitude") == "unavailable"
    assert gps.current_fix is None
    assert gps._expiry is None
    release.set()
    await refresh
    assert gps.data is None
    optional_api.reset_mock()
    await gps.async_refresh()
    assert await gps._async_update_data() is None
    optional_api.assert_not_awaited()
    assert sensor_state(hass, "gps_latitude") == "unavailable"


async def test_revoke_during_identity(
    hass: HomeAssistant, product_api: AsyncMock, optional_api: AsyncMock
) -> None:
    """Consent is checked again after an awaited identity verification."""
    values = readings()
    mock_readings(optional_api, values)
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    gps = entry.runtime_data.gps
    assert gps is not None
    started = asyncio.Event()
    release = asyncio.Event()

    async def product() -> ProductInfo:
        started.set()
        await release.wait()
        return ProductInfo("SERIAL-001", "E300")

    product_api.side_effect = product
    optional_api.reset_mock()
    refresh = asyncio.create_task(gps.async_refresh())
    await started.wait()
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": False})
    release.set()
    await refresh
    await hass.async_block_till_done()
    optional_api.assert_not_awaited()
    assert gps.current_fix is None


async def test_synchronous_revoke_before_options_persistence(
    hass: HomeAssistant, product_api: AsyncMock, optional_api: AsyncMock
) -> None:
    """The options hook redacts immediately, even before the options are saved."""
    mock_readings(optional_api, readings())
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    gps = entry.runtime_data.gps
    assert gps is not None
    gps.async_revoke_consent()
    gps.async_revoke_consent()
    assert entry.options["gps_enabled"] is True
    assert sensor_state(hass, "gps_latitude") == "unavailable"
    assert gps._expiry is None
    optional_api.reset_mock()
    await gps.async_refresh()
    optional_api.assert_not_awaited()


async def test_gps_external_cancellation_drains_read(
    hass: HomeAssistant, product_api: AsyncMock, optional_api: AsyncMock
) -> None:
    """Cancelling a GPS refresh propagates and closes its child HTTP operation."""
    mock_readings(optional_api, readings())
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    gps = entry.runtime_data.gps
    assert gps is not None
    started = asyncio.Event()
    drained = asyncio.Event()

    async def fetch(path: str) -> object:
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            drained.set()

    optional_api.side_effect = fetch
    refresh = asyncio.create_task(gps.async_refresh())
    await started.wait()
    refresh.cancel()
    with pytest.raises(asyncio.CancelledError):
        await refresh
    assert drained.is_set()
    assert gps._request_task is None


async def test_unload_drains_inflight_gps(
    hass: HomeAssistant, product_api: AsyncMock, optional_api: AsyncMock
) -> None:
    """A successful unload cancels GPS HTTP work as well as scheduled timers."""
    mock_readings(optional_api, readings())
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    gps = entry.runtime_data.gps
    assert gps is not None
    started = asyncio.Event()
    drained = asyncio.Event()

    async def fetch(path: str) -> object:
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            drained.set()

    optional_api.side_effect = fetch
    refresh = asyncio.create_task(gps.async_refresh())
    await started.wait()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await refresh
    assert drained.is_set()
    assert gps._request_task is None
    assert gps._expiry is None
    assert gps.current_fix is None


async def test_freshness_expiry_during_blocked_poll(
    hass: HomeAssistant,
    product_api: AsyncMock,
    optional_api: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Expire published coordinates on time, even while the next GPS read hangs."""
    values = readings(gps=gps_payload(age=119))
    mock_readings(optional_api, values)
    entry = add_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"gps_enabled": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    gps = entry.runtime_data.gps
    assert gps is not None
    assert sensor_state(hass, "gps_latitude") == "0.0"
    started = asyncio.Event()
    release = asyncio.Event()

    async def fetch(path: str) -> object:
        started.set()
        await release.wait()
        return values[path]

    optional_api.side_effect = fetch
    refresh = asyncio.create_task(gps.async_refresh())
    await started.wait()
    freezer.tick(2)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert sensor_state(hass, "gps_latitude") == "unavailable"
    assert gps.current_fix is not None
    assert gps.current_fix.latitude is None
    assert gps.data is not None
    assert gps.data.latitude is None
    assert_no_position(hass)
    release.set()
    await refresh
    assert sensor_state(hass, "gps_latitude") == "unavailable"
    mock_readings(optional_api, readings())
    await gps.async_refresh()
    assert sensor_state(hass, "gps_latitude") == "0.0"


@pytest.mark.parametrize("cancel", [False, True])
async def test_auth_and_cancellation_drain_optional_siblings(
    hass: HomeAssistant,
    product_api: AsyncMock,
    optional_api: AsyncMock,
    cancel: bool,
) -> None:
    """Auth and external cancellation both drain every optional child task."""
    mock_readings(optional_api, readings())
    entry = add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    started = asyncio.Event()
    trigger = asyncio.Event()
    drained: set[str] = set()

    async def fetch(path: str) -> object:
        try:
            if path == "fw_info":
                await started.wait()
                await trigger.wait()
                raise InvalidAuth()
            started.set()
            await asyncio.Event().wait()
        finally:
            drained.add(path)

    optional_api.side_effect = fetch
    refresh = asyncio.create_task(entry.runtime_data.async_refresh())
    await started.wait()
    if cancel:
        refresh.cancel()
        with pytest.raises(asyncio.CancelledError):
            await refresh
    else:
        trigger.set()
        await refresh
        await hass.async_block_till_done()
        assert any(
            flow["context"]["source"] == "reauth"
            for flow in hass.config_entries.flow.async_progress()
        )
    assert drained == {
        "fw_info",
        "wan/devices",
        "wan/primary_device",
        "wan/connection_state",
    }
