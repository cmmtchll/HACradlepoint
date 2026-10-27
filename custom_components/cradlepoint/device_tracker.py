"""Opted-in router location from the shared, freshness-filtered GPS stream."""

from homeassistant.components.device_tracker.const import SourceType
from homeassistant.components.device_tracker.entity import TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    CradlePointConfigEntry,
    CradlePointCoordinator,
    CradlePointGpsCoordinator,
)
from .telemetry import GpsFix

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlePointConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a tracker to the router only when GPS consent is enabled."""
    if (gps := entry.runtime_data.gps) is not None:
        async_add_entities([CradlePointTracker(entry.runtime_data, gps)])


class CradlePointTracker(CoordinatorEntity[CradlePointGpsCoordinator], TrackerEntity):
    """Combine validated coordinates without making independent GPS requests."""

    _attr_has_entity_name = True
    _attr_translation_key = "gps_location"

    def __init__(
        self,
        router: CradlePointCoordinator,
        coordinator: CradlePointGpsCoordinator,
    ) -> None:
        """Associate a stable tracker identity with the existing router device."""
        super().__init__(coordinator)
        serial = router.data.serial_number
        self._attr_unique_id = f"{serial}_gps_location"
        self._device_info = DeviceInfo(identifiers={(DOMAIN, serial)})

    @property
    def device_info(self) -> DeviceInfo:
        """Attach the tracker to the router rather than a separate tracked device."""
        return self._device_info

    @property
    def _fix(self) -> GpsFix | None:
        """Suppress both coordinates unless a successful, complete fix is current."""
        fix = self.coordinator.current_fix
        if (
            not self.coordinator.last_update_success
            or fix is None
            or fix.latitude is None
            or fix.longitude is None
        ):
            return None
        return fix

    @property
    def available(self) -> bool:
        """Never present a stale or partial position as a tracked location."""
        return super().available and self._fix is not None

    @property
    def source_type(self) -> SourceType:
        """Identify the documented GPS source to Home Assistant."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude only while the whole position is valid."""
        return fix.latitude if (fix := self._fix) is not None else None

    @property
    def longitude(self) -> float | None:
        """Return longitude only while the whole position is valid."""
        return fix.longitude if (fix := self._fix) is not None else None
