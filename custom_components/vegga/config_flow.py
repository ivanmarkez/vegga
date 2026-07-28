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


def _unit_id(unit: dict[str, Any]) -> str | None:
    for key in ("deviceId", "device_id", "unitId", "unit_id", "id", "pk"):
        value = unit.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _unit_label(unit: dict[str, Any], device_id: str) -> str:
    for key in ("name", "description", "alias", "deviceName", "unitName"):
        value = unit.get(key)
        if value:
            return f"{value} ({device_id})"
    return f"Agrónic {device_id}"


class VeggaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure VEGGA."""

    VERSION = 2

    def __init__(self) -> None:
        self._credentials: dict[str, Any] = {}
        self._devices: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        debug_message = ""

        if user_input is not None:
            username = str(user_input[CONF_USERNAME]).strip()
            password = str(user_input[CONF_PASSWORD])
            api = VeggaApi(async_get_clientsession(self.hass), username, password)
            try:
                await api.async_login()
                units = await api.get_units()
            except VeggaAuthError as err:
                _LOGGER.error("VEGGA authentication failed: %s", err, exc_info=True)
                errors["base"] = "invalid_auth"
                debug_message = str(err)
            except VeggaApiError as err:
                _LOGGER.error("VEGGA connection/device discovery failed: %s", err, exc_info=True)
                errors["base"] = "cannot_connect"
                debug_message = str(err)
            except Exception as err:  # Never hide unexpected config-flow failures
                _LOGGER.exception("Unexpected VEGGA config flow error: %s", err)
                errors["base"] = "unknown"
                debug_message = f"{type(err).__name__}: {err}"
            else:
                devices: dict[str, str] = {}
                for unit in units:
                    device_id = _unit_id(unit)
                    if device_id:
                        devices[device_id] = _unit_label(unit, device_id)

                if not devices:
                    errors["base"] = "no_devices"
                    debug_message = "El login funcionó, pero la lista de controladores quedó vacía."
                else:
                    self._credentials = {
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    }
                    self._devices = devices
                    if len(devices) == 1:
                        return await self._create_device_entry(next(iter(devices)))
                    return await self.async_step_device()

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(vol.Coerce(int), vol.Range(min=15, max=3600)),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"debug": debug_message or "Sin diagnóstico todavía."},
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._create_device_entry(str(user_input[CONF_DEVICE_ID]))

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE_ID): vol.In(self._devices)}
            ),
        )

    async def _create_device_entry(self, device_id: str) -> ConfigFlowResult:
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._devices.get(device_id, f"Agrónic {device_id}"),
            data={**self._credentials, CONF_DEVICE_ID: device_id},
        )
