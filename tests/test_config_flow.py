"""Exercise all UI flow branches using the real Home Assistant flow manager."""

from unittest.mock import AsyncMock, patch

import probatio as vol
import pytest
from homeassistant.config_entries import (
    SOURCE_DHCP,
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    SOURCE_USER,
    ConfigEntryState,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cradlepoint.api import (
    CannotConnect,
    InvalidAuth,
    InvalidResponse,
    ProductInfo,
)
from custom_components.cradlepoint.const import DOMAIN

INPUT = {"origin": "https://ROUTER:443/", "username": "admin", "password": "secret"}
DATA = {**INPUT, "origin": "https://router"}


async def test_user_flow(hass: HomeAssistant, product_api: AsyncMock) -> None:
    """Validate a live connection before creating an identified entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    with patch("custom_components.cradlepoint.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], INPUT
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "E300"
    assert result["data"] == DATA
    assert result["result"].unique_id == "SERIAL-001"
    product_api.assert_awaited_once()


async def test_dhcp_flow(hass: HomeAssistant, product_api: AsyncMock) -> None:
    """Offer credentials form with the DHCP-discovered router address."""
    discovery_info = DhcpServiceInfo(
        ip="192.0.2.10",
        hostname="router",
        macaddress="003044000001",
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=discovery_info
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "dhcp_confirm"
    schema = result["data_schema"]
    assert schema({"username": "admin", "password": "secret"}) == {
        "origin": "https://192.0.2.10",
        "username": "admin",
        "password": "secret",
    }
    with patch("custom_components.cradlepoint.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "origin": "https://192.0.2.10",
                "username": "admin",
                "password": "secret",
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "SERIAL-001"
    assert result["data"]["origin"] == "https://192.0.2.10"
    product_api.assert_awaited_once()


async def test_dhcp_flow_duplicate_serial(
    hass: HomeAssistant, product_api: AsyncMock
) -> None:
    """Reject discovered routers whose serial already has an entry."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="SERIAL-001", data=DATA)
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=DhcpServiceInfo(
            ip="192.0.2.10", hostname="router", macaddress="003044000001"
        ),
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "origin": "https://192.0.2.10",
            "username": "admin",
            "password": "secret",
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data == DATA


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (InvalidAuth(), "invalid_auth"),
        (CannotConnect(), "cannot_connect"),
        (InvalidResponse(), "invalid_response"),
    ],
)
async def test_flow_errors(
    hass: HomeAssistant, product_api: AsyncMock, error: Exception, expected: str
) -> None:
    """Display distinct safe errors and allow the user to retry."""
    product_api.side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data=INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_invalid_origin(hass: HomeAssistant, product_api: AsyncMock) -> None:
    """Reject insecure origins before attempting network access."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={**INPUT, "origin": "http://router"},
    )
    assert result["errors"] == {"origin": "invalid_origin"}
    product_api.assert_not_awaited()


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("", "secret"),
        ("admin", ""),
        ("invalid:username", "secret"),
        ("\ud800", "secret"),
        ("admin", "\ud800"),
    ],
)
async def test_invalid_credentials(
    hass: HomeAssistant, username: str, password: str
) -> None:
    """Keep invalid credentials in the UI form without performing a request."""
    with patch("aiohttp.ClientSession.get") as request:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={**INPUT, "username": username, "password": password},
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    request.assert_not_called()


async def test_duplicate(hass: HomeAssistant, product_api: AsyncMock) -> None:
    """Identify duplicates by serial even when the origin changes."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="SERIAL-001", data=DATA)
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={**INPUT, "origin": "https://new-router"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data == DATA


@pytest.mark.parametrize("source", [SOURCE_REAUTH, SOURCE_RECONFIGURE])
@pytest.mark.parametrize("wrong_router", [False, True])
async def test_update_flow(
    hass: HomeAssistant, product_api: AsyncMock, source: str, wrong_router: bool
) -> None:
    """Update entries only after checking the original router identity."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="SERIAL-001", data=DATA)
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": source, "entry_id": entry.entry_id},
        data=entry.data if source == SOURCE_REAUTH else None,
    )
    assert result["type"] is FlowResultType.FORM
    expected_step = "reauth_confirm" if source == SOURCE_REAUTH else "reconfigure"
    assert result["step_id"] == expected_step
    if wrong_router:
        product_api.return_value = ProductInfo("OTHER", "E300")
    updated = {**DATA, "origin": "https://new-router", "password": "replacement"}
    with patch.object(hass.config_entries, "async_reload", return_value=True) as reload:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], updated
        )
        await hass.async_block_till_done()
    if wrong_router:
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "wrong_device"}
        assert entry.data == DATA
        reload.assert_not_called()
    else:
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == (
            "reauth_successful" if source == SOURCE_REAUTH else "reconfigure_successful"
        )
        assert entry.data == updated
        assert entry.unique_id == "SERIAL-001"
        reload.assert_awaited_once_with(entry.entry_id)


@pytest.mark.parametrize("source", [SOURCE_REAUTH, SOURCE_RECONFIGURE])
@pytest.mark.parametrize(
    "initial_state",
    [
        ConfigEntryState.LOADED,
        ConfigEntryState.NOT_LOADED,
        ConfigEntryState.SETUP_RETRY,
    ],
)
@pytest.mark.parametrize("changed", [False, True])
async def test_update_flow_real_reload(
    hass: HomeAssistant,
    product_api: AsyncMock,
    source: str,
    initial_state: ConfigEntryState,
    changed: bool,
) -> None:
    """Reload exactly once through real HA setup/unload, even on unchanged input."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="SERIAL-001", data=DATA)
    entry.add_to_hass(hass)
    if initial_state is ConfigEntryState.SETUP_RETRY:
        product_api.side_effect = CannotConnect()
        assert not await hass.config_entries.async_setup(entry.entry_id)
        product_api.side_effect = None
    elif initial_state is ConfigEntryState.LOADED:
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is initial_state
    previous_coordinator = getattr(entry, "runtime_data", None)
    calls_before = product_api.await_count
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": source, "entry_id": entry.entry_id},
        data=entry.data if source == SOURCE_REAUTH else None,
    )
    updated = {**DATA, "password": "replacement"} if changed else DATA
    with patch.object(
        hass.config_entries, "async_reload", wraps=hass.config_entries.async_reload
    ) as reload:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], updated
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == (
        "reauth_successful" if source == SOURCE_REAUTH else "reconfigure_successful"
    )
    reload.assert_awaited_once_with(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data == updated
    assert entry.runtime_data is not previous_coordinator
    assert not entry.update_listeners
    assert product_api.await_count == calls_before + 2
    assert await hass.config_entries.async_unload(entry.entry_id)
