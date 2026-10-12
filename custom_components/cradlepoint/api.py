"""Read-only client for the documented NCOS product-information endpoint."""

import asyncio
import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

import aiohttp


class CradlePointError(Exception):
    """Base error for router communication."""


class InvalidAuth(CradlePointError):
    """The router rejected the supplied credentials."""


class CannotConnect(CradlePointError):
    """The router could not be reached securely."""


class InvalidResponse(CradlePointError):
    """The router returned an unsupported product response."""


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
    if parsed.netloc.startswith("["):
        suffix = parsed.netloc[parsed.netloc.index("]") + 1 :]
        if suffix and not (
            suffix.startswith(":")
            and suffix[1:].isascii()
            and suffix[1:].isdigit()
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
    """Use a borrowed Home Assistant session to read router product information."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        origin: str,
        username: str,
        password: str,
    ) -> None:
        """Initialize the client without taking ownership of its session."""
        self._session = session
        self._origin = normalize_origin(origin)
        self._username = username
        self._password = password

    async def async_get_product(self) -> ProductInfo:
        """Fetch and validate product information with verified TLS."""
        try:
            authorization = aiohttp.encode_basic_auth(self._username, self._password)
        except (ValueError, UnicodeError):
            raise InvalidAuth("Invalid authentication credentials") from None
        try:
            async with asyncio.timeout(10):
                async with self._session.get(
                    f"{self._origin}/api/status/product",
                    headers={"Authorization": authorization},
                    allow_redirects=False,
                    ssl=True,
                ) as response:
                    if response.status in (401, 403):
                        raise InvalidAuth("Authentication rejected")
                    if response.status != 200:
                        raise InvalidResponse("Unexpected HTTP response")
                    try:
                        payload = await response.json()
                    except (ValueError, aiohttp.ContentTypeError):
                        raise InvalidResponse("Invalid JSON response") from None
        except (aiohttp.ClientError, TimeoutError):
            raise CannotConnect("Secure router connection failed") from None
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise InvalidResponse("Unsuccessful product response")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise InvalidResponse("Invalid product data")
        serial = data.get("serial_number")
        product = data.get("product_name")
        if not isinstance(serial, str) or not serial.strip():
            raise InvalidResponse("Missing serial number")
        if not isinstance(product, str) or not product.strip():
            raise InvalidResponse("Missing product name")
        return ProductInfo(serial.strip(), product.strip())
