"""Coordinate identity-first polling and optional read-only telemetry."""

import asyncio
import logging
import time
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    CannotConnect,
    CradlePointApi,
    InvalidAuth,
    InvalidResponse,
)
from .const import DOMAIN, UPDATE_INTERVAL
from .telemetry import (
    RouterSnapshot,
    parse_connection,
    parse_firmware,
    parse_gps,
    parse_primary,
    parse_wan,
    with_rates,
)

_LOGGER = logging.getLogger(__name__)

type CradlePointConfigEntry = ConfigEntry[CradlePointCoordinator]


class CradlePointCoordinator(DataUpdateCoordinator[RouterSnapshot]):
    """Share telemetry polling while preserving the configured router identity."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CradlePointConfigEntry,
        api: CradlePointApi,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self.api = api
        self.serial_number = entry.unique_id
        self.gps_enabled = entry.options.get("gps_enabled", False) is True

    async def _optional[T](self, path: str, parser: Callable[[object], T]) -> T | None:
        """Isolate unavailable optional capabilities but never swallow auth."""
        try:
            return parser(await self.api.async_get(path))
        except (CannotConnect, InvalidResponse):
            return None

    async def _async_update_data(self) -> RouterSnapshot:
        """Read supported fields and translate communication failures."""
        try:
            product = await self.api.async_get_product()
            if product.serial_number != self.serial_number:
                raise InvalidResponse("Router identity changed")
            firmware, wan, primary, connection = await asyncio.gather(
                self._optional("fw_info", parse_firmware),
                self._optional("wan/devices", parse_wan),
                self._optional("wan/primary_device", parse_primary),
                self._optional("wan/connection_state", parse_connection),
            )
            sampled_at = time.monotonic()
            gps = await self._optional("gps", parse_gps) if self.gps_enabled else None
            if wan is not None and self.data is not None and self.last_update_success:
                wan = with_rates(
                    wan, self.data.wan or (), sampled_at - self.data.sampled_at
                )
            return RouterSnapshot(
                product, sampled_at, firmware, wan, primary, connection, gps
            )
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed("Authentication rejected") from err
        except (CannotConnect, InvalidResponse) as err:
            raise UpdateFailed("Router product information unavailable") from err
