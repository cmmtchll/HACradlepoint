"""Privacy-preserving, allowlisted integration diagnostics."""

from homeassistant.core import HomeAssistant

from .coordinator import CradlePointConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CradlePointConfigEntry
) -> dict[str, object]:
    """Return only non-identifying integration health and product type."""
    coordinator = entry.runtime_data
    return {
        "product_name": coordinator.data.product_name,
        "last_update_success": coordinator.last_update_success,
    }
