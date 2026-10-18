"""Tests for secure API requests and strictly validated product responses."""

import asyncio
import json
import ssl
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.cradlepoint.api import (
    CannotConnect,
    CradlePointApi,
    InvalidAuth,
    InvalidResponse,
    ProductInfo,
    normalize_origin,
)


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        ("https://ROUTER.Example", "https://router.example"),
        ("https://router.example/", "https://router.example"),
        ("https://router.example:443", "https://router.example"),
        ("HTTPS://router.example:8443", "https://router.example:8443"),
        ("https://192.168.1.1", "https://192.168.1.1"),
        ("https://[2001:DB8::1]:443", "https://[2001:db8::1]"),
        ("https://bücher.example", "https://xn--bcher-kva.example"),
    ],
)
def test_normalize_origin(origin: str, expected: str) -> None:
    """Canonicalize HTTPS router origins without retaining irrelevant spelling."""
    assert normalize_origin(origin) == expected


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "http://router",
        "router",
        "https://",
        "https://user@router",
        "https://@router",
        "https://router/api",
        "https://router?x=1",
        "https://router?",
        "https://router#fragment",
        "https://router#",
        "https://router:invalid",
        "https://router:65536",
        "https://router:0",
        "https://router:-1",
        "https://router:",
        "https://router\\evil",
        "https://router host",
        "https://[invalid]",
        "https://[::1]suffix",
        "https://[fe80::1%eth0]",
        "https://-router",
        "https://router-",
        "https://router..example",
        "https://router_example",
        "https://" + "a" * 64,
        "https://" + ".".join(["a" * 63] * 5),
        "https://\ud800.example",
    ],
)
def test_invalid_origin(origin: str) -> None:
    """Reject malformed origins and URL components that could leak credentials."""
    with pytest.raises(ValueError, match="Invalid HTTPS origin"):
        normalize_origin(origin)


def make_client(
    payload: object, status: int = 200
) -> tuple[CradlePointApi, MagicMock, MagicMock]:
    """Build a transport mock while preserving aiohttp request semantics."""
    response = MagicMock(status=status)
    response.headers = {}
    response.content_type = "application/json"
    response.content.read = AsyncMock(side_effect=[json.dumps(payload).encode(), b""])
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock(spec=aiohttp.ClientSession)
    session.get.return_value = context
    return (
        CradlePointApi(session, "https://ROUTER:443/", "admin", "secret"),
        session,
        response,
    )


async def test_product_request() -> None:
    """Read only the documented endpoint using Basic authentication and TLS."""
    api, session, _ = make_client(
        {
            "success": True,
            "data": {
                "manufacturing": {"serial_num": " SERIAL-001 "},
                "product_name": " E300 ",
            },
        }
    )
    assert await api.async_get_product() == ProductInfo("SERIAL-001", "E300")
    session.get.assert_called_once_with(
        "https://router/api/status/product_info",
        headers={
            "Authorization": aiohttp.encode_basic_auth("admin", "secret"),
            "Accept-Encoding": "gzip, deflate",
        },
        allow_redirects=False,
        ssl=True,
        auto_decompress=False,
    )
    session.close.assert_not_called()


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("invalid:username", "secret"),
        ("\ud800", "secret"),
        ("admin", "\ud800"),
        ("", "secret"),
        ("admin", ""),
    ],
)
async def test_invalid_credentials(username: str, password: str) -> None:
    """Handle credentials that cannot be safely encoded as HTTP Basic auth."""
    session = MagicMock(spec=aiohttp.ClientSession)
    api = CradlePointApi(session, "https://router", username, password)
    with pytest.raises(InvalidAuth):
        await api.async_get_product()
    session.get.assert_not_called()


async def test_unicode_credentials() -> None:
    """Encode non-Latin-1 credentials as UTF-8 without crashing the flow."""
    _, session, _ = make_client(
        {
            "success": True,
            "data": {"manufacturing": {"serial_num": "SERIAL"}, "product_name": "E300"},
        }
    )
    api = CradlePointApi(session, "https://router", "用户名", "密码")
    assert await api.async_get_product() == ProductInfo("SERIAL", "E300")
    assert session.get.call_args.kwargs["headers"] == {
        "Authorization": aiohttp.encode_basic_auth("用户名", "密码"),
        "Accept-Encoding": "gzip, deflate",
    }


@pytest.mark.parametrize("status", [401, 403])
async def test_authentication_error(status: int) -> None:
    """Classify rejected credentials separately from response and network errors."""
    api, _, response = make_client({}, status)
    with pytest.raises(InvalidAuth):
        await api.async_get_product()
    response.content.read.assert_not_awaited()


@pytest.mark.parametrize("status", [301, 302, 307, 308, 500])
async def test_http_error_and_redirect(status: int) -> None:
    """Reject HTTP errors and redirects rather than forwarding credentials."""
    api, session, response = make_client({}, status)
    with pytest.raises(InvalidResponse):
        await api.async_get_product()
    assert session.get.call_count == 1
    response.content.read.assert_not_awaited()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"success": 1, "data": {}},
        {"success": False},
        {"success": True, "data": []},
        {"success": True, "data": {}},
        {"success": True, "data": {"serial_number": 123, "product_name": "E300"}},
        {"success": True, "data": {"serial_number": " ", "product_name": "E300"}},
        {"success": True, "data": {"serial_number": "SERIAL", "product_name": 123}},
        {"success": True, "data": {"serial_number": "SERIAL", "product_name": " "}},
    ],
)
async def test_schema_error(payload: object) -> None:
    """Require the success flag and both nonempty documented product strings."""
    api, _, _ = make_client(payload)
    with pytest.raises(InvalidResponse):
        await api.async_get_product()


@pytest.mark.parametrize(
    "error",
    [
        aiohttp.ClientConnectionError("sensitive URL"),
        aiohttp.ClientError("sensitive URL"),
        TimeoutError("sensitive URL"),
        aiohttp.ClientConnectorCertificateError(
            MagicMock(), ssl.CertificateError("untrusted certificate")
        ),
    ],
)
async def test_network_and_tls_errors(error: Exception) -> None:
    """Translate timeouts and certificate failures without exposing URLs."""
    api, session, _ = make_client({})
    session.get.side_effect = error
    with pytest.raises(CannotConnect, match="Secure router connection failed") as exc:
        await api.async_get_product()
    assert exc.value.__suppress_context__
    assert "sensitive" not in str(exc.value)


async def test_async_timeout() -> None:
    """Enforce the client timeout independently of a session's defaults."""
    api, _, response = make_client({})

    async def slow_read(size: int) -> bytes:
        await asyncio.sleep(0.02)
        return b""

    response.content.read.side_effect = slow_read
    from unittest.mock import patch

    with (
        patch(
            "custom_components.cradlepoint.api.asyncio.timeout",
            return_value=asyncio.timeout(0.001),
        ),
        pytest.raises(CannotConnect),
    ):
        await api.async_get_product()


@pytest.mark.parametrize("body", [b"raw secret", b"\xff", b'{"secret":'])
async def test_json_errors(body: bytes) -> None:
    """Hide raw response decoding errors behind a safe schema error."""
    api, _, response = make_client({})
    response.content.read.side_effect = [body, b""]
    with pytest.raises(InvalidResponse, match="Invalid JSON response") as exc:
        await api.async_get_product()
    assert exc.value.__suppress_context__


@pytest.mark.parametrize("status", [404, 501])
async def test_unsupported_optional_endpoint(status: int) -> None:
    """Distinguish absent/unsupported optional endpoints from transport failure."""
    from custom_components.cradlepoint.api import UnsupportedEndpoint

    api, session, _ = make_client({}, status)
    with pytest.raises(UnsupportedEndpoint):
        await api.async_get("gps")
    assert session.get.call_count == 1


async def test_legacy_fallback() -> None:
    """Fallback only when documented product_info is missing; preserve serial."""
    api, session, response = make_client(
        {"success": True, "data": {"serial_number": "SERIAL", "product_name": "E300"}}
    )
    missing = MagicMock(status=404)
    context = MagicMock()
    context.__aenter__ = AsyncMock(side_effect=[missing, response])
    context.__aexit__ = AsyncMock(return_value=False)
    session.get.return_value = context
    assert await api.async_get_product() == ProductInfo("SERIAL", "E300")
    assert [call.args[0] for call in session.get.call_args_list] == [
        "https://router/api/status/product_info",
        "https://router/api/status/product",
    ]


async def test_missing_data() -> None:
    """Require a data key in a generic successful envelope."""
    api, _, _ = make_client({"success": True})
    with pytest.raises(InvalidResponse, match="Missing response data"):
        await api.async_get("gps")


@pytest.mark.parametrize(
    "data",
    [
        {"manufacturing": {"serial_num": " "}, "product_name": "E300"},
        {"manufacturing": {"serial_num": 1}, "product_name": "E300"},
        {"manufacturing": {"serial_num": "SERIAL"}, "product_name": " "},
        {"manufacturing": {"serial_num": "SERIAL"}, "product_name": 1},
    ],
)
async def test_documented_invalid_identity(data: object) -> None:
    """Malformed documented identity never tries a legacy endpoint."""
    api, session, _ = make_client({"success": True, "data": data})
    with pytest.raises(InvalidResponse):
        await api.async_get_product()
    assert session.get.call_count == 1
