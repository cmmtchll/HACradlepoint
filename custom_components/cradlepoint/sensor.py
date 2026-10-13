"""Diagnostic product-name sensor for CradlePoint routers."""

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CradlePointConfigEntry, CradlePointCoordinator

PARALLEL_UPDATES = 0

DESCRIPTION = SensorEntityDescription(
    key="product_name",
    translation_key="product_name",
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlePointConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the product-name sensor."""
    async_add_entities([CradlePointProductSensor(entry.runtime_data)])


class CradlePointProductSensor(CoordinatorEntity[CradlePointCoordinator], SensorEntity):
    """Expose the documented product name without speculative telemetry."""

    _attr_has_entity_name = True
    entity_description = DESCRIPTION

    def __init__(self, coordinator: CradlePointCoordinator) -> None:
        """Initialize stable serial-based entity and device identifiers."""
        super().__init__(coordinator)
        product = coordinator.data
        self._attr_unique_id = f"{product.serial_number}_product_name"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, product.serial_number)},
            manufacturer="CradlePoint",
            model=product.product_name,
            name=product.product_name,
            serial_number=product.serial_number,
        )

    @property
    def native_value(self) -> str:
        """Return the current product name."""
        return self.coordinator.data.product_name
