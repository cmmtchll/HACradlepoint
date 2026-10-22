"""Bounded read-only client for documented local NCOS status endpoints."""

import asyncio
import ipaddress
import json
import zlib
from dataclasses import dataclass
from urllib.parse import urlsplit

import aiohttp

# HA states have a 255-character limit; identity uses the same conservative bound.
MAX_STATE_LENGTH = 255
# Allow detailed multi-modem trees; bound both wire and decompressed body bytes.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
RESPONSE_CHUNK_BYTES = 64 * 1024
MAX_JSON_DEPTH = 64


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate members instead of accepting ambiguous router identity."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON member")
        result[key] = value
    return result


def _check_json_depth(body: str) -> None:
    """Bound container nesting before invoking the recursive JSON decoder."""
    depth = 0
    quoted = escaped = False
    for character in body:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError("Excessive JSON nesting")
        elif character in "]}":
            depth -= 1


async def _read_body(response: aiohttp.ClientResponse) -> bytearray:
    """Bound wire bytes and incremental decompression before allocating JSON."""
    encoding = response.headers.get("Content-Encoding", "identity").strip().lower()
    if encoding not in ("identity", "gzip", "deflate"):
        raise InvalidResponse("Unsupported response encoding")
    decompressor = (
        zlib.decompressobj(
            16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS
        )
        if encoding != "identity"
        else None
    )
    body = bytearray()
    received = 0
    while chunk := await response.content.read(
        min(RESPONSE_CHUNK_BYTES, MAX_RESPONSE_BYTES - received + 1)
    ):
        received += len(chunk)
        if received > MAX_RESPONSE_BYTES:
            raise InvalidResponse("Response exceeds size limit")
        decoded = (
            decompressor.decompress(chunk, MAX_RESPONSE_BYTES - len(body) + 1)
            if decompressor is not None
            else chunk
        )
        if len(body) + len(decoded) > MAX_RESPONSE_BYTES:
            raise InvalidResponse("Response exceeds size limit")
        body.extend(decoded)
    if decompressor is not None and (not decompressor.eof or decompressor.unused_data):
        raise InvalidResponse("Invalid compressed response")
    return body


class CradlePointError(Exception):
    """Base error for router communication."""


class InvalidAuth(CradlePointError):
    """The router rejected the supplied credentials."""


class CannotConnect(CradlePointError):
    """The router could not be reached securely."""


class InvalidResponse(CradlePointError):
    """The router returned an unsupported product response."""


class UnsupportedEndpoint(InvalidResponse):
    """The endpoint is absent or explicitly unsupported."""


class EndpointNotFound(UnsupportedEndpoint):
    """Only a missing identity endpoint permits legacy fallback."""


def normalize_origin(value: str) -> str:
    """Validate and canonicalize an HTTPS origin without embedded credentials."""
    if not value or any(character.isspace() for character in value):
        raise ValueError("Invalid HTTPS origin")
    try:
        parsed = urlsplit(value)
        port = parsed.port
        host = parsed.hostname
    except ValueError:
        raise ValueError("Invalid HTTPS origin") from None
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or "?" in value
        or "#" in value
        or "\\" in value
        or "%" in host
        or parsed.netloc.endswith(":")
        or port == 0
    ):
        raise ValueError("Invalid HTTPS origin")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        try:
            host = host.encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise ValueError("Invalid HTTPS origin") from None
        if (
            any(
                not label
                or len(label) > 63
                or label.startswith("-")
                or label.endswith("-")
                or any(
                    not (char.isascii() and (char.isalnum() or char == "-"))
                    for char in label
                )
                for label in host.split(".")
            )
            or len(host) > 253
        ):
            raise ValueError("Invalid HTTPS origin") from None
    else:
        host = f"[{address.compressed}]" if address.version == 6 else str(address)
    return f"https://{host}" + (f":{port}" if port not in (None, 443) else "")


@dataclass(frozen=True, slots=True)
class ProductInfo:
    """Validated product fields supported by the documented API."""

    serial_number: str
    product_name: str


class CradlePointApi:
    """Use a borrowed Home Assistant session to read allowlisted status paths."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        origin: str,
        username: str,
        password: str,
        verify_ssl: bool = True,
    ) -> None:
        """Initialize the client without taking ownership of its session."""
        self._session = session
        self._verify_ssl = verify_ssl
        self._origin = normalize_origin(origin)
        self._username = username
        self._password = password

    async def async_get_product(self) -> ProductInfo:
        """Fetch and validate product information with verified TLS."""
        try:
            raw = await self.async_get("product_info")
        except EndpointNotFound:
            raw = await self.async_get("product")
            legacy = True
        else:
            legacy = False
        if not isinstance(raw, dict):
            raise InvalidResponse("Invalid product data")
        manufacturing = raw.get("manufacturing")
        serial = (
            raw.get("serial_number")
            if legacy
            else manufacturing.get("serial_num")
            if isinstance(manufacturing, dict)
            else None
        )
        product = raw.get("product_name")
        if (
            not isinstance(serial, str)
            or not serial.strip()
            or len(serial.strip()) > MAX_STATE_LENGTH
        ):
            raise InvalidResponse("Missing serial number")
        if (
            not isinstance(product, str)
            or not product.strip()
            or len(product.strip()) > MAX_STATE_LENGTH
        ):
            raise InvalidResponse("Missing product name")
        return ProductInfo(serial.strip(), product.strip())

    async def async_get(self, path: str) -> object:
        """Fetch one internal status path with bounded, verified transport."""
        if not self._username or not self._password:
            raise InvalidAuth("Username and password must be nonempty")
        try:
            authorization = aiohttp.encode_basic_auth(self._username, self._password)
        except ValueError, UnicodeError:
            raise InvalidAuth("Invalid authentication credentials") from None
        try:
            async with asyncio.timeout(10):
                async with self._session.get(
                    f"{self._origin}/api/status/{path}",
                    headers={
                        "Authorization": authorization,
                        "Accept-Encoding": "gzip, deflate",
                    },
                    allow_redirects=False,
                    # Per-request, so only this config entry skips verification.
                    ssl=self._verify_ssl,
                    auto_decompress=False,
                ) as response:
                    if response.status in (401, 403):
                        raise InvalidAuth("Authentication rejected")
                    if response.status == 404:
                        raise EndpointNotFound("Endpoint missing")
                    if response.status == 501:
                        raise UnsupportedEndpoint("Endpoint unsupported")
                    if response.status != 200:
                        raise InvalidResponse("Unexpected HTTP response")
                    if response.content_type != "application/json" and not (
                        response.content_type.startswith("application/")
                        and response.content_type.endswith("+json")
                    ):
                        raise InvalidResponse("Invalid JSON response")
                    try:
                        body = await _read_body(response)
                        encoded = body.decode("utf-8-sig")
                        _check_json_depth(encoded)
                        payload = json.loads(encoded, object_pairs_hook=_json_object)
                    except ValueError, UnicodeError, RecursionError, zlib.error:
                        raise InvalidResponse("Invalid JSON response") from None
        except aiohttp.ClientError, TimeoutError:
            raise CannotConnect("Secure router connection failed") from None
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise InvalidResponse("Unsuccessful product response")
        if "data" not in payload:
            raise InvalidResponse("Missing response data")
        return payload["data"]
