from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VeggaApi, VeggaApiError, VeggaAuthError
from .const import (
    CONF_DEVICE_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


class VeggaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure VEGGA."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            device_id = str(user_input[CONF_DEVICE_ID]).strip()
            token = str(user_input[CONF_TOKEN]).strip()

            api = VeggaApi(
                async_get_clientsession(self.hass),
                device_id,
                token,
            )
            try:
                await api.get_programs()
            except VeggaAuthError:
                errors["base"] = "invalid_auth"
            except VeggaApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Agrónic {device_id}",
                    data={
                        CONF_DEVICE_ID: device_id,
                        CONF_TOKEN: token,
                        CONF_SCAN_INTERVAL: int(
                            user_input[CONF_SCAN_INTERVAL]
                        ),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): str,
                vol.Required(CONF_TOKEN): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=DEFAULT_SCAN_INTERVAL,
                ): vol.All(vol.Coerce(int), vol.Range(min=15, max=3600)),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
