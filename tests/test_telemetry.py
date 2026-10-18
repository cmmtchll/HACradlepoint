"""Synthetic documentation-guided schema and rate tests, not hardware claims."""

import math

import pytest

from custom_components.cradlepoint.api import InvalidResponse
from custom_components.cradlepoint.telemetry import (
    GPS_MAX_AGE,
    GpsFix,
    WanDevice,
    coordinate,
    counter,
    number,
    parse_connection,
    parse_firmware,
    parse_gps,
    parse_primary,
    parse_wan,
    with_rates,
)


def gps_payload(**changes: object) -> dict[str, object]:
    """Build a synthetic fix, with no real location or modem identity."""
    return {
        "fix": {
            "lock": True,
            "age": 1,
            "latitude": {"degree": "0", "minute": "0", "second": "0"},
            "longitude": {"degree": "-0", "minute": "30", "second": "0"},
            "altitude_meters": -10,
            "ground_speed_knots": 2,
            "heading": 90,
            "satellites": 8,
            **changes,
        },
        "nmea": ["DO NOT RETAIN"],
    }


def wan_payload(received: object = 100, sent: object = 200) -> dict[str, object]:
    """Build a documented device tree with unretained secret-like fields."""
    return {
        "device-a": {
            "info": {"type": "ethernet", "uid": "PRIVATE", "model": "unused"},
            "status": {
                "connection_state": "connected",
                "link_state": "up",
                "ipinfo": {"ip_address": "PRIVATE"},
            },
            "stats": {"in": received, "out": sent},
            "passkey": "PRIVATE",
        }
    }


def test_wan_normalization_and_rates() -> None:
    """Allowlist fields and compute reset-safe per-device bytes per second."""
    first = parse_wan(wan_payload())
    assert first == (WanDevice("device-a", "ethernet", "connected", "up", 100, 200),)
    assert "PRIVATE" not in repr(first)
    second = with_rates(parse_wan(wan_payload(220, 440)), first, 60)
    assert second[0].received_rate == 2
    assert second[0].sent_rate == 4
    reset = with_rates(parse_wan(wan_payload(10, 20)), second, 60)
    assert reset[0].received_rate is None
    assert reset[0].sent_rate is None
    assert with_rates(first, (), 60) == first
    assert with_rates(first, first, 0)[0].received_rate is None
    assert with_rates(first, first, -1)[0].sent_rate is None
    assert with_rates(first, first, 60)[0].received_rate == 0
    assert (
        with_rates((WanDevice("device-a", None, None, None, 10**400, 200),), first, 60)[
            0
        ].received_rate
        is None
    )
    assert (
        with_rates(
            (WanDevice("device-a", None, None, None, 10**300, 200),), first, 1e-300
        )[0].received_rate
        is None
    )
    assert with_rates(parse_wan(wan_payload(None, None)), first, 60)[0].received is None
    assert (
        with_rates(first, parse_wan(wan_payload(None, None)), 60)[0].sent_rate is None
    )
    assert parse_wan({}) == ()
    assert parse_wan({"unknown-prefix": {}})[0].transport is None
    assert (
        parse_wan({"mdm-not-a-modem": {"info": {"type": "undocumented"}}})[0].transport
        is None
    )


@pytest.mark.parametrize(
    "payload",
    [
        [],
    ],
)
def test_invalid_wan(payload: object) -> None:
    """Reject a malformed top-level tree."""
    with pytest.raises(InvalidResponse):
        parse_wan(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"": {}},
        {123: {}},
        {"device": []},
        {"device": {"info": None}},
        {"device": {"status": []}},
        {"device": {"stats": None}},
        {"device": {"status": {"connection_state": "PRIVATE"}}},
        {"device": {"status": {"link_state": 1}}},
        wan_payload(-1),
        wan_payload(True),
        wan_payload(1.5),
        wan_payload("10"),
    ],
)
def test_invalid_wan_device(payload: dict[str, object]) -> None:
    """Skip malformed device shapes, states and traffic without losing peers."""
    assert parse_wan(payload) == ()
    healthy = wan_payload()
    assert parse_wan({**payload, **healthy}) == parse_wan(healthy)


@pytest.mark.parametrize(
    "value", [True, [], {}, "NaN", "inf", "-inf", "bad", "", 10**400]
)
def test_invalid_number(value: object) -> None:
    """Reject nonfinite, unparseable and nonnumeric values without raw text."""
    with pytest.raises(InvalidResponse, match="Invalid numeric reading"):
        number(value)


def test_optional_numbers_and_states() -> None:
    """Keep null readings unknown and require documented firmware parts."""
    assert number(None) is None
    assert number("1.5") == 1.5
    assert counter(None) is None
    assert parse_connection(None) is None
    assert parse_primary("") is None
    assert parse_primary("device-a") == "device-a"
    assert parse_connection("disconnected") == "disconnected"
    assert (
        parse_firmware({"major_version": 7, "minor_version": 26, "patch_version": 0})
        == "7.26.0"
    )
    with pytest.raises(InvalidResponse):
        parse_primary(None)
    with pytest.raises(InvalidResponse):
        parse_firmware({"major_version": 6})


def test_gps_normalization() -> None:
    """Accept numeric strings and genuine zero only in fresh locked fixes."""
    fix = parse_gps(gps_payload())
    assert fix == GpsFix(True, 1, 0, -0.5, -10, 2, 90, 8)
    assert "DO NOT RETAIN" not in repr(fix)
    assert coordinate({"degree": -30, "minute": 15, "second": 36}, 90) == -30.26
    assert (
        math.copysign(1, coordinate({"degree": "-0", "minute": 0, "second": 0}, 90)) < 0
    )
    assert parse_gps(gps_payload(ground_speed_knots=None, heading=None)).speed is None
    assert coordinate(None, 90) is None
    assert coordinate({"degree": 0}, 90) is None
    assert parse_gps(gps_payload(latitude=None)).latitude is None
    assert parse_gps(gps_payload(age=GPS_MAX_AGE)).latitude == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"lock": False},
        {"lock": None},
        {"age": None},
        {"age": GPS_MAX_AGE + 1},
    ],
)
def test_gps_no_current_location(changes: dict[str, object]) -> None:
    """Never fabricate zeros from stale or unlocked data, including lastpos."""
    payload = gps_payload(**changes)
    payload["lastpos"] = {"latitude": 0, "longitude": 0}
    fix = parse_gps(payload)
    assert fix.latitude is fix.longitude is fix.altitude is fix.speed is None


@pytest.mark.parametrize(
    "changes",
    [
        {"lock": 1},
        {"age": -1},
        {"satellites": -1},
        {"satellites": 1.5},
        {"latitude": []},
        {"latitude": {"degree": 90, "minute": 1, "second": 0}},
        {"latitude": {"degree": 1.5, "minute": 0, "second": 0}},
        {"latitude": {"degree": 1, "minute": 60, "second": 0}},
        {"longitude": {"degree": 181, "minute": 0, "second": 0}},
        {"longitude": {"degree": 1, "minute": 0, "second": -1}},
        {"altitude_meters": float("nan")},
        {"ground_speed_knots": -1},
        {"heading": 360},
        {"heading": -1},
    ],
)
def test_invalid_gps(changes: dict[str, object]) -> None:
    """Validate finite coordinates, age, satellite counts and physical units."""
    with pytest.raises(InvalidResponse):
        parse_gps(gps_payload(**changes))


@pytest.mark.parametrize("payload", [None, [], {}, {"fix": None}, {"fix": []}])
def test_invalid_gps_shape(payload: object) -> None:
    """Require an actual fix object, not an arbitrary response."""
    with pytest.raises(InvalidResponse):
        parse_gps(payload)
