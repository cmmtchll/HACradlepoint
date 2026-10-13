"""Fixtures shared by the integration's Home Assistant tests."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.cradlepoint.api import ProductInfo, UnsupportedEndpoint


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the integration through Home Assistant."""


@pytest.fixture
def product_api(optional_api: AsyncMock) -> Iterator[AsyncMock]:
    """Mock only the router transport, not Home Assistant internals."""
    with patch(
        "custom_components.cradlepoint.api.CradlePointApi.async_get_product",
        new_callable=AsyncMock,
        return_value=ProductInfo("SERIAL-001", "E300"),
    ) as mock:
        yield mock


@pytest.fixture
def optional_api() -> Iterator[AsyncMock]:
    """Mock unsupported optional capabilities without real network I/O."""
    with patch(
        "custom_components.cradlepoint.api.CradlePointApi.async_get",
        new_callable=AsyncMock,
        side_effect=UnsupportedEndpoint(),
    ) as mock:
        yield mock
