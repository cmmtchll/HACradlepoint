"""Shared-coordinator product, experimental WAN and opted-in GPS sensors."""

from dataclasses import dataclass
from typing import Literal, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CradlePointConfigEntry, CradlePointCoordinator
from .telemetry import GpsFix, RouterSnapshot, WanDevice

PARALLEL_UPDATES = 0

DESCRIPTION = SensorEntityDescription(
    key="product_name",
    translation_key="product_name",
    entity_category=EntityCategory.DIAGNOSTIC,
)


@dataclass(frozen=True, kw_only=True)
class TelemetryDescription(SensorEntityDescription):
    """Map a translated entity to one allowlisted normalized field."""

    source: Literal["router", "wan", "gps"]
    field: str


ROUTER_SENSORS = (
    TelemetryDescription(
        key="firmware",
        translation_key="firmware",
        source="router",
        field="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    TelemetryDescription(
        key="primary", translation_key="primary", source="router", field="primary"
    ),
    TelemetryDescription(
        key="wan_state",
        translation_key="wan_state",
        source="router",
        field="connection_state",
    ),
)
WAN_SENSORS = (
    TelemetryDescription(
        key="wan_connection",
        translation_key="wan_connection",
        source="wan",
        field="connection_state",
    ),
    TelemetryDescription(
        key="wan_link", translation_key="wan_link", source="wan", field="link_state"
    ),
    TelemetryDescription(
        key="wan_transport",
        translation_key="wan_transport",
        source="wan",
        field="transport",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    *(
        TelemetryDescription(
            key=f"wan_{field}",
            translation_key=f"wan_{field}",
            source="wan",
            field=field,
            native_unit_of_measurement=UnitOfInformation.BYTES,
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.TOTAL_INCREASING,
        )
        for field in ("received", "sent")
    ),
    *(
        TelemetryDescription(
            key=f"wan_{field}",
            translation_key=f"wan_{field}",
            source="wan",
            field=field,
            native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
            device_class=SensorDeviceClass.DATA_RATE,
            state_class=SensorStateClass.MEASUREMENT,
        )
        for field in ("received_rate", "sent_rate")
    ),
)
GPS_SENSORS = tuple(
    TelemetryDescription(
        key=f"gps_{field}",
        translation_key=f"gps_{field}",
        source="gps",
        field=field,
        native_unit_of_measurement=unit,
        device_class=device_class,
        state_class=SensorStateClass.MEASUREMENT if unit else None,
    )
    for field, unit, device_class in (
        ("lock", None, None),
        ("age", UnitOfTime.SECONDS, SensorDeviceClass.DURATION),
        ("latitude", "°", None),
        ("longitude", "°", None),
        ("altitude", UnitOfLength.METERS, SensorDeviceClass.DISTANCE),
        ("speed", UnitOfSpeed.KNOTS, SensorDeviceClass.SPEED),
        ("heading", "°", None),
        ("satellites", None, None),
    )
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlePointConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up router sensors and discover WAN entities from shared updates."""
    coordinator = entry.runtime_data
    async_add_entities(
        [CradlePointProductSensor(coordinator)]
        + [CradlePointTelemetrySensor(coordinator, desc) for desc in ROUTER_SENSORS]
        + [
            CradlePointTelemetrySensor(coordinator, desc)
            for desc in GPS_SENSORS
            if coordinator.gps_enabled
        ]
    )
    known: set[str] = set()

    @callback
    def discover() -> None:
        """Discover new WAN keys from shared snapshots, without extra requests."""
        entities: list[CradlePointTelemetrySensor] = []
        for device in coordinator.data.wan or ():
            if device.key not in known:
                known.add(device.key)
                entities.extend(
                    CradlePointTelemetrySensor(coordinator, desc, device.key)
                    for desc in WAN_SENSORS
                )
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class CradlePointProductSensor(CoordinatorEntity[CradlePointCoordinator], SensorEntity):
    """Expose the documented product name with stable router identity."""

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
    def native_value(self) -> str | int | float | bool | None:
        """Return the current product name."""
        return self.coordinator.data.product_name


class CradlePointTelemetrySensor(CradlePointProductSensor):
    """Expose a normalized capability, never an arbitrary payload attribute."""

    entity_description: TelemetryDescription

    def __init__(
        self,
        coordinator: CradlePointCoordinator,
        description: TelemetryDescription,
        wan_key: str | None = None,
    ) -> None:
        """Use stable router serial and documented WAN device keys."""
        super().__init__(coordinator)
        self.entity_description = description
        self._wan_key = wan_key
        suffix = f"{wan_key}_{description.key}" if wan_key else description.key
        self._attr_unique_id = f"{coordinator.serial_number}_{suffix}"
        if wan_key:
            self._attr_translation_placeholders = {"wan": wan_key}

    @property
    def _source(self) -> RouterSnapshot | WanDevice | GpsFix | None:
        """Select one normalized snapshot capability."""
        if self.entity_description.source == "gps":
            return self.coordinator.data.gps
        if self.entity_description.source == "wan":
            return next(
                (
                    device
                    for device in self.coordinator.data.wan or ()
                    if device.key == self._wan_key
                ),
                None,
            )
        return self.coordinator.data

    @property
    def available(self) -> bool:
        """Optional failures and missing GPS positions cannot expose stale data."""
        if not super().available or self._source is None:
            return False
        if self.entity_description.key in (
            "firmware",
            "primary",
            "wan_state",
            "gps_latitude",
            "gps_longitude",
            "gps_altitude",
            "gps_speed",
            "gps_heading",
        ):
            return self.native_value is not None
        return True

    @property
    def native_value(self) -> str | int | float | bool | None:
        """Return only the description's allowlisted typed field."""
        return cast(
            str | int | float | bool | None,
            getattr(self._source, self.entity_description.field, None),
        )
