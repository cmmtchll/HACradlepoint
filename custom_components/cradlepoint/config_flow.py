"""Validated UI configuration for CradlePoint routers."""

from collections.abc import Mapping
from typing import Any

import probatio as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    CannotConnect,
    CradlePointApi,
    InvalidAuth,
    InvalidResponse,
    normalize_origin,
)
from .const import CONF_ORIGIN, DOMAIN


class CradlePointConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure or update credentials without changing router identity."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial user configuration."""
        return await self._async_connection_step("user", user_input)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start credential reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate replacement credentials against the original router."""
        return await self._async_connection_step("reauth_confirm", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate a changed origin or credentials against the original router."""
        return await self._async_connection_step("reconfigure", user_input)

    async def _async_connection_step(
        self, step: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Share secure connection validation between supported flow steps."""
        errors: dict[str, str] = {}
        entry = None
        if step == "reauth_confirm":
            entry = self._get_reauth_entry()
        elif step == "reconfigure":
            entry = self._get_reconfigure_entry()
        if user_input is not None:
            data = dict(user_input)
            try:
                data[CONF_ORIGIN] = normalize_origin(data[CONF_ORIGIN])
            except ValueError:
                errors[CONF_ORIGIN] = "invalid_origin"
            else:
                api = CradlePointApi(
                    async_get_clientsession(self.hass),
                    data[CONF_ORIGIN],
                    data[CONF_USERNAME],
                    data[CONF_PASSWORD],
                )
                try:
                    product = await api.async_get_product()
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidResponse:
                    errors["base"] = "invalid_response"
                else:
                    await self.async_set_unique_id(product.serial_number)
                    if entry is not None:
                        if product.serial_number != entry.unique_id:
                            errors["base"] = "wrong_device"
                        else:
                            return self.async_update_reload_and_abort(
                                entry,
                                data_updates=data,
                                reason=(
                                    "reauth_successful"
                                    if step == "reauth_confirm"
                                    else "reconfigure_successful"
                                ),
                            )
                    else:
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=product.product_name, data=data
                        )
        defaults = user_input or (dict(entry.data) if entry else {})
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ORIGIN, default=defaults.get(CONF_ORIGIN, vol.UNDEFINED)
                ): str,
                vol.Required(
                    CONF_USERNAME, default=defaults.get(CONF_USERNAME, vol.UNDEFINED)
                ): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id=step, data_schema=schema, errors=errors)
