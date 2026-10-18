"""Bound router-controlled input before decoding or publishing HA states."""

import gzip
import io
import zlib
from unittest.mock import MagicMock, patch

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from homeassistant.core import HomeAssistant
from test_api import make_client
from test_init import add_entry
from test_optional import sensor_state
from test_telemetry import wan_payload

from custom_components.cradlepoint.api import (
    MAX_JSON_DEPTH,
    MAX_RESPONSE_BYTES,
    MAX_STATE_LENGTH,
    RESPONSE_CHUNK_BYTES,
    CradlePointApi,
    InvalidResponse,
    ProductInfo,
)
from custom_components.cradlepoint.telemetry import (
    MAX_COUNTER_VALUE,
    MAX_WAN_DEVICES,
    MAX_WAN_KEY_LENGTH,
    counter,
    parse_firmware,
    parse_primary,
    parse_wan,
    with_rates,
)


@pytest.mark.parametrize("field", ["serial_num", "product_name"])
@pytest.mark.parametrize("length", [MAX_STATE_LENGTH, MAX_STATE_LENGTH + 1])
async def test_identity_bounds(field: str, length: int) -> None:
    """Bound normalized identity, including multibyte characters, without truncation."""
    value = "é" * length
    serial = value if field == "serial_num" else "SERIAL"
    product = value if field == "product_name" else "E300"
    api, _, _ = make_client(
        {
            "success": True,
            "data": {
                "manufacturing": {"serial_num": f" {serial} "},
                "product_name": f" {product} ",
            },
        }
    )
    if length == MAX_STATE_LENGTH:
        assert await api.async_get_product() == ProductInfo(serial, product)
    else:
        with pytest.raises(InvalidResponse):
            await api.async_get_product()


@pytest.mark.parametrize(
    "field", ["product_name", "primary", "firmware", "device-a_wan_received"]
)
async def test_entity_state_bounds_and_recovery(
    hass: HomeAssistant, field: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Exercise real HA entities and the real parser at and beyond its state bound."""
    product: dict[str, object] = {
        "manufacturing": {"serial_num": "SERIAL-001"},
        "product_name": "E300",
    }
    values: dict[str, object] = {
        "product_info": product,
        "wan/primary_device": "device-a",
        "fw_info": {"major_version": 1, "minor_version": 0, "patch_version": 0},
        "wan/devices": wan_payload(),
    }
    transport = MagicMock(spec=aiohttp.ClientSession)

    def request(url: str, **kwargs: object) -> MagicMock:
        path = url.removeprefix("https://router/api/status/")
        payload = {"success": True, "data": values.get(path)}
        _, session, _ = make_client(payload, 200 if path in values else 404)
        return session.get.return_value

    transport.get.side_effect = request

    def update_value(value: object) -> None:
        if field == "product_name":
            product["product_name"] = value
        elif field == "primary":
            values["wan/primary_device"] = value
        elif field == "firmware":
            values["fw_info"] = {
                "major_version": value,
                "minor_version": 0,
                "patch_version": 0,
            }
        else:
            values["wan/devices"] = wan_payload(value)

    entry = add_entry(hass)
    with patch(
        "custom_components.cradlepoint.async_get_clientsession", return_value=transport
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert sensor_state(hass, "product_name") == "E300"
        assert sensor_state(hass, "primary") == "device-a"
        if field == "firmware":
            component = 10 ** (MAX_STATE_LENGTH - 5)
            valid: object = component
            invalid: object = component * 10
            limit = f"{component}.0.0"
        elif field == "device-a_wan_received":
            valid = MAX_COUNTER_VALUE
            invalid = MAX_COUNTER_VALUE + 1
            limit = str(MAX_COUNTER_VALUE)
        else:
            valid = limit = "é" * MAX_STATE_LENGTH
            invalid = limit + "x"
        update_value(valid)
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert sensor_state(hass, field) == limit
        update_value(invalid)
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert sensor_state(hass, field) == "unavailable"
        if field != "product_name":
            assert sensor_state(hass, "product_name") == "E300"
        assert limit not in caplog.text
        product["product_name"] = "E300"
        values["wan/primary_device"] = "device-a"
        values["fw_info"] = {
            "major_version": 1,
            "minor_version": 0,
            "patch_version": 0,
        }
        values["wan/devices"] = wan_payload()
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert sensor_state(hass, "product_name") == "E300"
        assert sensor_state(hass, "primary") == "device-a"
        assert sensor_state(hass, "firmware") == "1.0.0"
        assert sensor_state(hass, "device-a_wan_received") == "100"
        assert await hass.config_entries.async_unload(entry.entry_id)


def test_wan_key_and_cardinality_bounds() -> None:
    """Accept exact limits and fail closed on excess before filtering devices."""
    key = "é" * MAX_WAN_KEY_LENGTH
    assert parse_wan({key: {}})[0].key == key
    assert parse_primary(key) == key
    assert parse_wan({key + "x": {}}) == ()
    assert parse_wan({" ": {}}) == ()
    with pytest.raises(InvalidResponse):
        parse_primary(key + "x")
    devices = {f"device-{index}": {} for index in range(MAX_WAN_DEVICES)}
    assert len(parse_wan(devices)) == MAX_WAN_DEVICES
    devices["extra"] = None
    with pytest.raises(InvalidResponse, match="Too many WAN devices"):
        parse_wan(devices)


def test_counter_decimal_state_bounds() -> None:
    """Use HA representability, not an invented vendor-specific counter maximum."""
    assert counter(MAX_COUNTER_VALUE) == MAX_COUNTER_VALUE
    assert len(str(MAX_COUNTER_VALUE)) == MAX_STATE_LENGTH
    assert parse_wan(wan_payload(MAX_COUNTER_VALUE))[0].received == MAX_COUNTER_VALUE
    with pytest.raises(InvalidResponse, match="Invalid counter"):
        counter(MAX_COUNTER_VALUE + 1)
    assert parse_wan(wan_payload(MAX_COUNTER_VALUE + 1)) == ()


@pytest.mark.parametrize("extra", [0, 1])
def test_complete_firmware_state_bound(extra: int) -> None:
    """Bound the complete joined version, rather than only its individual parts."""
    component = 10 ** (MAX_STATE_LENGTH - 5 + extra)
    data = {
        "major_version": component,
        "minor_version": 0,
        "patch_version": 0,
    }
    if extra:
        with pytest.raises(InvalidResponse, match="Invalid firmware version"):
            parse_firmware(data)
    else:
        assert len(parse_firmware(data)) == MAX_STATE_LENGTH


def test_malformed_peer_preserves_healthy_rates_and_recovery() -> None:
    """Only consecutive valid samples form a per-device rate baseline."""
    first = parse_wan({**wan_payload(), "bad": {"stats": {"in": 1, "out": 2}}})
    mixed = parse_wan({**wan_payload(220, 440), "bad": {"stats": {"in": "PRIVATE"}}})
    second = with_rates(mixed, first, 60)
    assert len(second) == 1
    assert second[0].received_rate == 2
    assert second[0].sent_rate == 4
    recovered = with_rates(
        parse_wan({**wan_payload(340, 680), "bad": {"stats": {"in": 300, "out": 400}}}),
        second,
        60,
    )
    assert recovered[0].received_rate == 2
    assert recovered[1].received_rate is None


@pytest.mark.parametrize("extra", [0, 1])
async def test_complete_response_limit(extra: int) -> None:
    """Count complete JSON bytes, even ignored strings, and stop at limit + 1."""
    prefix = b'{"success":true,"data":"'
    suffix = b'"}'
    body = (
        prefix
        + b"x" * (MAX_RESPONSE_BYTES - len(prefix) - len(suffix) + extra)
        + suffix
    )
    stream = io.BytesIO(body)
    api, _, response = make_client({})
    response.content.read.side_effect = stream.read
    if extra:
        with (
            patch("custom_components.cradlepoint.api.json.loads") as decode,
            pytest.raises(InvalidResponse, match="Response exceeds size limit"),
        ):
            await api.async_get("gps")
        decode.assert_not_called()
    else:
        assert await api.async_get("gps") == "x" * (
            MAX_RESPONSE_BYTES - len(prefix) - len(suffix)
        )
    assert stream.tell() == len(body)
    assert all(
        call.args[0] <= RESPONSE_CHUNK_BYTES
        for call in response.content.read.call_args_list
    )


@pytest.mark.parametrize(
    "body",
    [
        b'{"success":true,"data":{}, "data":{"secret":"PRIVATE"}}',
        b'{"success":true,"data":{"device-a":{},"device-a":{}}}',
        b'{"success":true,"data":{"manufacturing":'
        b'{"serial_num":"FIRST","serial_num":"SECOND"},"product_name":"E300"}}',
        b'{"success":true,"data":'
        + b"[" * MAX_JSON_DEPTH
        + b"0"
        + b"]" * MAX_JSON_DEPTH
        + b"}",
        b"[" * 2000 + b"0" + b"]" * 2000,
        b'{"success":true,"data":' + b"1" * 5000 + b"}",
    ],
)
async def test_ambiguous_or_excessive_json(body: bytes) -> None:
    """Translate duplicate, excessive-depth and integer decoding failures safely."""
    api, _, response = make_client({})
    response.content.read.side_effect = [body, b""]
    with pytest.raises(InvalidResponse, match="Invalid JSON response") as exc:
        await api.async_get("gps")
    assert exc.value.__suppress_context__
    assert "PRIVATE" not in str(exc.value)
    response.content.read.side_effect = [b'{"success":true,"data":{}}', b""]
    assert await api.async_get("gps") == {}


async def test_exact_json_depth_and_quoted_brackets() -> None:
    """Permit exact container depth, ignoring escaped quotes and brackets in strings."""
    data: object = 'escaped "\\ [ { ] }'
    for _ in range(MAX_JSON_DEPTH - 1):
        data = [data]
    api, _, _ = make_client({"success": True, "data": data})
    assert await api.async_get("gps") == data


@pytest.mark.parametrize("content_type", ["text/html", "application/problem+json"])
async def test_json_content_type(content_type: str) -> None:
    """Preserve JSON content-type validation while accepting structured JSON types."""
    api, _, response = make_client({"success": True, "data": {}})
    response.content_type = content_type
    if content_type == "text/html":
        with pytest.raises(InvalidResponse, match="Invalid JSON response"):
            await api.async_get("gps")
        response.content.read.assert_not_awaited()
    else:
        assert await api.async_get("gps") == {}


async def test_safe_decoder_recursion_failure() -> None:
    """Do not leak decoder failures even if recursion fails below the depth bound."""
    api, _, _ = make_client({"success": True, "data": {}})
    with (
        patch(
            "custom_components.cradlepoint.api.json.loads",
            side_effect=RecursionError("PRIVATE"),
        ),
        pytest.raises(InvalidResponse, match="Invalid JSON response") as exc,
    ):
        await api.async_get("gps")
    assert exc.value.__suppress_context__


@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
async def test_streamed_compressed_response(encoding: str) -> None:
    """Decode supported encodings across arbitrary transport chunk boundaries."""
    raw = b'{"success":true,"data":{"value":"synthetic"}}'
    body = gzip.compress(raw) if encoding == "gzip" else zlib.compress(raw)
    api, _, response = make_client({})
    response.headers = {"Content-Encoding": encoding}
    response.content.read.side_effect = [body[:3], body[3:8], body[8:], b""]
    assert await api.async_get("gps") == {"value": "synthetic"}


@pytest.mark.parametrize(
    ("encoding", "body"),
    [
        ("br", b"PRIVATE"),
        ("gzip", b"PRIVATE"),
        ("gzip", gzip.compress(b"{}")[:-2]),
        ("gzip", gzip.compress(b"{}") + b"trailing"),
        ("gzip", gzip.compress(b"{}") + gzip.compress(b"{}")),
    ],
)
async def test_invalid_compressed_response(encoding: str, body: bytes) -> None:
    """Fail closed on unsupported, corrupt, incomplete or concatenated encodings."""
    api, _, response = make_client({})
    response.headers = {"Content-Encoding": encoding}
    response.content.read.side_effect = [body, b""]
    with pytest.raises(InvalidResponse) as exc:
        await api.async_get("gps")
    assert "PRIVATE" not in str(exc.value)


@pytest.mark.usefixtures("socket_enabled")
@pytest.mark.parametrize("extra", [0, 1])
async def test_real_decompressed_response_limit(extra: int) -> None:
    """Exercise a real compressed HTTP transfer, not a mocked JSON decoder."""
    prefix = b'{"success":true,"data":"'
    suffix = b'"}'
    value = b"x" * (MAX_RESPONSE_BYTES - len(prefix) - len(suffix) + extra)
    compressed = gzip.compress(prefix + value + suffix)
    assert len(compressed) < MAX_RESPONSE_BYTES

    async def handler(request: web.Request) -> web.Response:
        return web.Response(
            body=compressed,
            headers={"Content-Encoding": "gzip", "Content-Type": "application/json"},
        )

    app = web.Application()
    app.router.add_get("/api/status/gps", handler)
    async with TestServer(app) as server, aiohttp.ClientSession() as session:
        transport = MagicMock(spec=aiohttp.ClientSession)
        transport.get.side_effect = lambda url, **kwargs: session.get(
            server.make_url("/api/status/gps"), **kwargs
        )
        api = CradlePointApi(transport, "https://router", "admin", "secret")
        if extra:
            with pytest.raises(InvalidResponse, match="Response exceeds size limit"):
                await api.async_get("gps")
        else:
            assert await api.async_get("gps") == value.decode()
        transport.get.assert_called_once()
