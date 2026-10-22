"""Read-only Home Assistant integration for CradlePoint routers."""

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CradlePointApi
from .const import CONF_ORIGIN, CONF_VERIFY_SSL
from .coordinator import CradlePointConfigEntry, CradlePointCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: CradlePointConfigEntry) -> bool:
    """Set up the integration after a successful initial product read."""
    api = CradlePointApi(
        async_get_clientsession(hass),
        entry.data[CONF_ORIGIN],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_VERIFY_SSL, True),
    )
    coordinator = CradlePointCoordinator(hass, entry, api)
    if coordinator.gps is not None:
        await coordinator.gps.async_refresh()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: CradlePointConfigEntry
) -> bool:
    """Unload the integration's platforms."""
    coordinator = entry.runtime_data
    if coordinator.gps is not None and not coordinator.gps.consent:
        coordinator.gps.async_set_updated_data(None)
        await coordinator.gps.async_shutdown()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and coordinator.gps is not None:
        await coordinator.gps.async_shutdown()
    return unloaded
