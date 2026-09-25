from __future__ import annotations

from typing import Any
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VeggaApi, VeggaApiError, VeggaAuthError
from .const import CONF_DEVICE_ID, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class VeggaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure VEGGA."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        debug_message = ""

        if user_input is not None:
            username = str(user_input[CONF_USERNAME]).strip()
            password = str(user_input[CONF_PASSWORD])
            device_id = str(user_input[CONF_DEVICE_ID]).strip()
            scan_interval = int(user_input[CONF_SCAN_INTERVAL])

            api = VeggaApi(
                async_get_clientsession(self.hass),
                username,
                password,
                device_id,
            )

            try:
                # Validate only the credentials here. Device discovery is skipped
                # because VEGGA uses an undocumented internal user identifier.
                await api.async_login()
            except VeggaAuthError as err:
                _LOGGER.error("VEGGA authentication failed: %s", err, exc_info=True)
                errors["base"] = "invalid_auth"
                debug_message = str(err)
            except VeggaApiError as err:
                _LOGGER.error("VEGGA connection failed: %s", err, exc_info=True)
                errors["base"] = "cannot_connect"
                debug_message = str(err)
            except Exception as err:
                _LOGGER.exception("Unexpected VEGGA config flow error: %s", err)
                errors["base"] = "unknown"
                debug_message = f"{type(err).__name__}: {err}"
            else:
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Agrónic {device_id}",
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_DEVICE_ID: device_id,
                        CONF_SCAN_INTERVAL: scan_interval,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_DEVICE_ID, default="17669"): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(vol.Coerce(int), vol.Range(min=15, max=3600)),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"debug": debug_message or "Sin errores."},
        )
