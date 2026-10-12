"""Coordinate read-only product updates."""

import logging

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
    ProductInfo,
)
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type CradlePointConfigEntry = ConfigEntry[CradlePointCoordinator]


class CradlePointCoordinator(DataUpdateCoordinator[ProductInfo]):
    """Poll product information while preserving the configured router identity."""

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

    async def _async_update_data(self) -> ProductInfo:
        """Read supported fields and translate communication failures."""
        try:
            product = await self.api.async_get_product()
            if product.serial_number != self.serial_number:
                raise InvalidResponse("Router identity changed")
            return product
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed("Authentication rejected") from err
        except (CannotConnect, InvalidResponse) as err:
            raise UpdateFailed("Router product information unavailable") from err
