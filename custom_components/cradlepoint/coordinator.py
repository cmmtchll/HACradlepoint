"""Coordinate identity-first polling and optional read-only telemetry."""

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import timedelta

from homeassistant.config_entries import (
    SIGNAL_CONFIG_ENTRY_CHANGED,
    ConfigEntry,
    ConfigEntryChange,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_call_later
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
    GPS_MAX_AGE,
    GpsFix,
    RouterSnapshot,
    WanDevice,
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
        self.gps = (
            CradlePointGpsCoordinator(hass, entry, api)
            if entry.options.get("gps_enabled", False) is True
            else None
        )

    async def _optional[T](self, path: str, parser: Callable[[object], T]) -> T | None:
        """Isolate unavailable optional capabilities but never swallow auth."""
        try:
            return parser(await self.api.async_get(path))
        except (CannotConnect, InvalidResponse):
            return None

    async def _async_wan_sample(self) -> tuple[tuple[WanDevice, ...] | None, float]:
        """Timestamp the WAN read independently of other endpoint latency."""
        wan = await self._optional("wan/devices", parse_wan)
        return wan, time.monotonic()

    async def _async_update_data(self) -> RouterSnapshot:
        """Read supported fields and translate communication failures."""
        try:
            product = await self.api.async_get_product()
            if product.serial_number != self.serial_number:
                raise InvalidResponse("Router identity changed")
            tasks = (
                asyncio.create_task(self._optional("fw_info", parse_firmware)),
                asyncio.create_task(self._async_wan_sample()),
                asyncio.create_task(
                    self._optional("wan/primary_device", parse_primary)
                ),
                asyncio.create_task(
                    self._optional("wan/connection_state", parse_connection)
                ),
            )
            try:
                firmware, wan_sample, primary, connection = await asyncio.gather(*tasks)
            finally:
                # gather propagates auth immediately, but does not stop siblings.
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            wan, sampled_at = wan_sample
            if wan is not None and self.data is not None and self.last_update_success:
                wan = with_rates(
                    wan, self.data.wan or (), sampled_at - self.data.sampled_at
                )
            return RouterSnapshot(
                product, sampled_at, firmware, wan, primary, connection
            )
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed("Authentication rejected") from err
        except (CannotConnect, InvalidResponse) as err:
            raise UpdateFailed("Router product information unavailable") from err


class CradlePointGpsCoordinator(DataUpdateCoordinator[GpsFix | None]):
    """Poll opted-in GPS independently of unrelated telemetry latency."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CradlePointConfigEntry,
        api: CradlePointApi,
    ) -> None:
        """Share transport and router identity, but not the telemetry poll lock."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_gps",
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self.entry = entry
        self._sampled_at = 0.0
        self._expiry: Callable[[], None] | None = None
        self._request_task: asyncio.Task[GpsFix | None] | None = None
        self._stopped = False
        entry.async_on_unload(
            async_dispatcher_connect(
                hass, SIGNAL_CONFIG_ENTRY_CHANGED, self._async_entry_updated
            )
        )

    @property
    def consent(self) -> bool:
        """Read live consent, including when a requested reload has failed."""
        return (
            not self._stopped and self.entry.options.get("gps_enabled", False) is True
        )

    @property
    def current_fix(self) -> GpsFix | None:
        """Never expose revoked or expired coordinates, including direct reads."""
        if not self.consent or self.data is None:
            return None
        if self.data.age is not None and (
            self.data.age + time.monotonic() - self._sampled_at >= GPS_MAX_AGE
        ):
            return GpsFix(
                self.data.lock, self.data.age, satellites=self.data.satellites
            )
        return self.data

    @callback
    def _async_entry_updated(
        self, change: ConfigEntryChange, entry: ConfigEntry
    ) -> None:
        """Redact existing states even if platform unload or reload fails."""
        if entry is self.entry and not self.consent:
            self.async_revoke_consent()

    @callback
    def async_revoke_consent(self) -> None:
        """Immediately redact GPS and cancel work before persisting an opt-out."""
        if self._stopped:
            return
        self._stopped = True
        self.async_set_updated_data(None)
        self._cancel_expiry()
        self._unschedule_refresh()
        if self._request_task is not None and not self._request_task.cancelling():
            self._request_task.cancel()
        self.hass.async_create_task(self.async_shutdown())

    @callback
    def _cancel_expiry(self) -> None:
        """Cancel the one pending freshness deadline."""
        if self._expiry is not None:
            self._expiry()
            self._expiry = None

    @callback
    def _expire(self, _now: object) -> None:
        """Publish freshness loss without waiting for a network poll."""
        self._expiry = None
        self.async_update_listeners()

    async def async_shutdown(self) -> None:
        """Stop polling and freshness callbacks with the entry lifecycle."""
        self._stopped = True
        self._cancel_expiry()
        if self._request_task is not None:
            if not self._request_task.cancelling():
                self._request_task.cancel()
            await asyncio.gather(self._request_task, return_exceptions=True)
        await super().async_shutdown()

    async def _async_update_data(self) -> GpsFix | None:
        """Own and drain the cancellable GPS operation independently of HA tasks."""
        task = self._request_task = asyncio.create_task(self._async_read())
        try:
            return await task
        except asyncio.CancelledError:
            if not self.consent:
                return None
            raise
        finally:
            self._request_task = None

    async def _async_read(self) -> GpsFix | None:
        """Check identity and consent before reading and before publishing GPS."""
        if not self.consent:
            return None
        try:
            product = await self.api.async_get_product()
            if product.serial_number != self.entry.unique_id:
                raise InvalidResponse("Router identity changed")
            if not self.consent:
                return None
            sampled_at = time.monotonic()
            fix = parse_gps(await self.api.async_get("gps"))
            if not self.consent:
                return None
            self._cancel_expiry()
            self._sampled_at = sampled_at
            if fix.age is not None and fix.lock is True:
                remaining = GPS_MAX_AGE - fix.age - (time.monotonic() - sampled_at)
                if remaining <= 0:
                    return GpsFix(fix.lock, fix.age, satellites=fix.satellites)
                self._expiry = async_call_later(
                    self.hass, timedelta(seconds=remaining), self._expire
                )
            return fix
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed("Authentication rejected") from err
        except (CannotConnect, InvalidResponse) as err:
            raise UpdateFailed("Router GPS unavailable") from err
