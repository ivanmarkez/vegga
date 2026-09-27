from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .api import VeggaApiError
from .const import DOMAIN

SERVICE_SET_PROGRAM_DAYS = "set_program_days"

WEEKDAY_KEYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on", "si", "sí"}
    return False


def _program_number(program: dict[str, Any], fallback: int) -> int:
    for key in (
        "programNumber",
        "program_number",
        "number",
        "program",
        "idProgram",
        "programId",
    ):
        try:
            value = int(program.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return fallback


async def async_register_services(hass: HomeAssistant) -> None:
    """Register VEGGA services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_PROGRAM_DAYS):
        return

    async def handle_set_program_days(call: ServiceCall) -> None:
        controller = str(call.data["controller"]).strip()
        requested_program = int(call.data["program"])
        requested_days = {str(day) for day in call.data["days"]}

        coordinators = hass.data.get(DOMAIN, {})
        coordinator = next(
            (
                item
                for item in coordinators.values()
                if str(item.api.device_id) == controller
                or controller.endswith(f"_{item.api.device_id}")
            ),
            None,
        )
        if coordinator is None:
            raise HomeAssistantError(
                f"No se encontró el controlador VEGGA {controller}"
            )

        programs = (coordinator.data or {}).get("programs", [])
        program_data: dict[str, Any] | None = None
        actual_program_number: int | None = None

        for fallback, item in enumerate(programs, start=1):
            if not isinstance(item, dict):
                continue
            number = _program_number(item, fallback)
            if number == requested_program:
                program_data = item
                actual_program_number = number
                break

        if program_data is None or actual_program_number is None:
            raise HomeAssistantError(
                f"No se encontró el programa {requested_program}"
            )

        if (
            _as_bool(program_data.get("daysFreq"))
            or _as_bool(program_data.get("daysFrequency"))
        ):
            raise HomeAssistantError(
                "Este programa usa frecuencia de días y no un calendario semanal"
            )

        try:
            program_type = int(
                program_data.get(
                    "type",
                    program_data.get(
                        "programType",
                        program_data.get("startType", 0),
                    ),
                )
            )
        except (TypeError, ValueError):
            program_type = 0

        if program_type == 1:
            raise HomeAssistantError(
                "Este programa es secuencial y no usa calendario semanal"
            )

        payload = {key: key in requested_days for key in WEEKDAY_KEYS}

        try:
            # Escritura deliberadamente mínima:
            # solo se envían monday..sunday. No se mandan horas, sectores,
            # fertilización ni ningún otro parámetro del programa.
            await coordinator.api._request(
                "PATCH",
                f"/units/{coordinator.api.device_id}/programs/{actual_program_number}",
                json_data=payload,
            )
        except VeggaApiError as err:
            raise HomeAssistantError(
                "VEGGA rechazó el cambio de días. "
                "No se ha enviado ningún otro parámetro del programa. "
                f"Detalle: {err}"
            ) from err

        active = [key for key in WEEKDAY_KEYS if payload[key]]
        coordinator.record_command(
            f"Programa {actual_program_number}: días "
            + (", ".join(active) if active else "ninguno")
        )
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PROGRAM_DAYS,
        handle_set_program_days,
        schema=vol.Schema(
            {
                vol.Required("controller"): cv.string,
                vol.Required("program"): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1),
                ),
                vol.Required("days"): vol.All(
                    cv.ensure_list,
                    [vol.In(WEEKDAY_KEYS)],
                ),
            }
        ),
    )
