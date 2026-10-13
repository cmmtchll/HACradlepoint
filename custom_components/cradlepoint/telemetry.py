"""Allowlisted, immutable snapshots for experimental documented NCOS telemetry."""

import math
from dataclasses import dataclass, replace

from .api import InvalidResponse, ProductInfo

GPS_MAX_AGE = 120
CONNECTION_STATES = ("connected", "disconnected", "connecting")


def object_data(value: object) -> dict[str, object]:
    """Require a JSON object without retaining unrecognized fields."""
    if not isinstance(value, dict):
        raise InvalidResponse("Invalid telemetry object")
    return value


def number(value: object) -> float | None:
    """Normalize finite numbers, including documented GPS numeric strings."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise InvalidResponse("Invalid numeric reading")
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise InvalidResponse("Invalid numeric reading") from None
    if not math.isfinite(result):
        raise InvalidResponse("Invalid numeric reading")
    return result


def counter(value: object) -> int | None:
    """Require nonnegative integer counters; missing readings remain unknown."""
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise InvalidResponse("Invalid counter")
    return value


def state(value: object, choices: tuple[str, ...]) -> str | None:
    """Validate documented states without exporting arbitrary status text."""
    if value is None:
        return None
    if not isinstance(value, str) or value not in choices:
        raise InvalidResponse("Invalid state")
    return value


@dataclass(frozen=True, slots=True)
class WanDevice:
    """Only explicitly documented, non-secret per-WAN fields."""

    key: str
    transport: str | None
    connection_state: str | None
    link_state: str | None
    received: int | None
    sent: int | None
    received_rate: float | None = None
    sent_rate: float | None = None


def parse_wan(value: object) -> tuple[WanDevice, ...]:
    """Parse the documented device-keyed WAN tree, not key prefixes."""
    devices = object_data(value)
    result = []
    for key, raw in devices.items():
        if not isinstance(key, str) or not key:
            raise InvalidResponse("Invalid WAN key")
        device = object_data(raw)
        info = object_data(device.get("info", {}))
        transport = info.get("type")
        status = object_data(device.get("status", {}))
        stats = object_data(device.get("stats", {}))
        result.append(
            WanDevice(
                key,
                transport
                if isinstance(transport, str) and transport in ("mdm", "ethernet")
                else None,
                state(status.get("connection_state"), CONNECTION_STATES),
                state(status.get("link_state"), ("up", "down", "unknown")),
                counter(stats.get("in")),
                counter(stats.get("out")),
            )
        )
    return tuple(result)


def parse_firmware(value: object) -> str:
    """Read only the documented integer version components."""
    data = object_data(value)
    parts = [
        counter(data.get(field))
        for field in ("major_version", "minor_version", "patch_version")
    ]
    if None in parts:
        raise InvalidResponse("Incomplete firmware version")
    return ".".join(str(part) for part in parts)


def parse_primary(value: object) -> str | None:
    """Read the documented primary device key, allowing no selected device."""
    if not isinstance(value, str):
        raise InvalidResponse("Invalid primary device")
    return value or None


def parse_connection(value: object) -> str | None:
    """Read the WAN connection state, not Internet health."""
    return state(value, CONNECTION_STATES)


def with_rates(
    devices: tuple[WanDevice, ...],
    previous: tuple[WanDevice, ...],
    elapsed: float,
) -> tuple[WanDevice, ...]:
    """Compute bytes/second only between consecutive valid monotonic samples."""
    old = {device.key: device for device in previous}

    def rate(current: int | None, before: int | None) -> float | None:
        if current is None or before is None or current < before or elapsed <= 0:
            return None
        try:
            result = (current - before) / elapsed
        except OverflowError:
            return None
        return result if math.isfinite(result) else None

    return tuple(
        replace(
            device,
            received_rate=rate(device.received, old[device.key].received),
            sent_rate=rate(device.sent, old[device.key].sent),
        )
        if device.key in old
        else device
        for device in devices
    )


def coordinate(value: object, limit: int) -> float | None:
    """Convert signed DMS to decimal degrees, preserving signed zero."""
    if value is None:
        return None
    dms = object_data(value)
    degree, minute, second = (
        number(dms.get(field)) for field in ("degree", "minute", "second")
    )
    if degree is None or minute is None or second is None:
        return None
    if degree != math.trunc(degree) or not 0 <= minute < 60 or not 0 <= second < 60:
        raise InvalidResponse("Invalid coordinate")
    result = math.copysign(abs(degree) + minute / 60 + second / 3600, degree)
    if abs(result) > limit:
        raise InvalidResponse("Invalid coordinate")
    return result


@dataclass(frozen=True, slots=True)
class GpsFix:
    """Validated GPS fields; coordinates require a fresh locked fix."""

    lock: bool | None
    age: float | None
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    speed: float | None = None
    heading: float | None = None
    satellites: int | None = None


def parse_gps(value: object) -> GpsFix:
    """Reject stale/unlocked positions and invalid ranges without zero defaults."""
    fix = object_data(object_data(value).get("fix"))
    lock = fix.get("lock")
    if lock is not None and not isinstance(lock, bool):
        raise InvalidResponse("Invalid GPS lock")
    age = number(fix.get("age"))
    if age is not None and age < 0:
        raise InvalidResponse("Invalid GPS age")
    satellites = counter(fix.get("satellites"))
    if lock is not True or age is None or age > GPS_MAX_AGE:
        return GpsFix(lock, age, satellites=satellites)
    latitude = coordinate(fix.get("latitude"), 90)
    longitude = coordinate(fix.get("longitude"), 180)
    altitude = number(fix.get("altitude_meters"))
    speed = number(fix.get("ground_speed_knots"))
    heading = number(fix.get("heading"))
    if (speed is not None and speed < 0) or (
        heading is not None and not 0 <= heading < 360
    ):
        raise InvalidResponse("Invalid GPS motion")
    return GpsFix(lock, age, latitude, longitude, altitude, speed, heading, satellites)


@dataclass(frozen=True, slots=True)
class RouterSnapshot:
    """Identity plus independently available optional capabilities."""

    product: ProductInfo
    sampled_at: float
    firmware: str | None = None
    wan: tuple[WanDevice, ...] | None = None
    primary: str | None = None
    connection_state: str | None = None
    gps: GpsFix | None = None

    @property
    def product_name(self) -> str:
        """Preserve the product sensor's existing contract."""
        return self.product.product_name

    @property
    def serial_number(self) -> str:
        """Return stable router identity."""
        return self.product.serial_number
