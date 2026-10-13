"""Read-only Home Assistant integration for CradlePoint routers."""

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CradlePointApi
from .const import CONF_ORIGIN
from .coordinator import CradlePointConfigEntry, CradlePointCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: CradlePointConfigEntry) -> bool:
    """Set up the integration after a successful initial product read."""
    api = CradlePointApi(
        async_get_clientsession(hass),
        entry.data[CONF_ORIGIN],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = CradlePointCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_reload_entry(
    hass: HomeAssistant, entry: CradlePointConfigEntry
) -> None:
    """Apply changed options through the normal unload/setup lifecycle."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: CradlePointConfigEntry
) -> bool:
    """Unload the integration's platforms."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
