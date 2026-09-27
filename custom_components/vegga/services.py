from __future__ import annotations

from copy import deepcopy
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
    pk = program.get("pk")
    if isinstance(pk, dict):
        try:
            value = int(pk.get("id"))
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value

    for key in (
        "programNumber",
        "program_number",
        "number",
        "program",
        "idProgram",
        "programId",
        "id",
    ):
        try:
            value = int(program.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return fallback


def _unwrap_program(data: Any) -> dict[str, Any] | None:
    """Extract one program object from possible VEGGA wrappers."""
    if isinstance(data, dict):
        # Direct program response.
        if isinstance(data.get("pk"), dict) or "monday" in data or "name" in data:
            return data

        for key in ("content", "data", "program", "item", "result"):
            value = data.get(key)
            found = _unwrap_program(value)
            if found is not None:
                return found

    if isinstance(data, list):
        for item in data:
            found = _unwrap_program(item)
            if found is not None:
                return found

    return None


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

        # Validate against the already loaded program list first.
        programs = (coordinator.data or {}).get("programs", [])
        listed_program: dict[str, Any] | None = None
        actual_program_number: int | None = None

        for fallback, item in enumerate(programs, start=1):
            if not isinstance(item, dict):
                continue
            number = _program_number(item, fallback)
            if number == requested_program:
                listed_program = item
                actual_program_number = number
                break

        if listed_program is None or actual_program_number is None:
            raise HomeAssistantError(
                f"No se encontró el programa {requested_program}"
            )

        if (
            _as_bool(listed_program.get("daysFreq"))
            or _as_bool(listed_program.get("daysFrequency"))
        ):
            raise HomeAssistantError(
                "Este programa usa frecuencia de días y no un calendario semanal"
            )

        # VEGGA's editor reads the individual program and saves it back with:
        # POST /units/{device_id}/programs/{program_number}
        #
        # Read immediately before writing so every setting (hours, sectors,
        # fertilizer, etc.) is kept exactly as VEGGA currently has it.
        try:
            response = await coordinator.api._request(
                "GET",
                f"/units/{coordinator.api.device_id}/programs/{actual_program_number}",
            )
        except VeggaApiError as err:
            raise HomeAssistantError(
                f"No se pudo leer el programa {actual_program_number} antes de guardarlo: {err}"
            ) from err

        current_program = _unwrap_program(response)
        if current_program is None:
            # The list entry is still a safe fallback because it comes from
            # VEGGA itself, but normally the individual GET should be used.
            current_program = listed_program

        payload = deepcopy(current_program)

        # Captured from VEGGA's own program-save payload.
        payload["progtype"] = "6"

        # Change ONLY the weekly calendar fields.
        for day in WEEKDAY_KEYS:
            payload[day] = day in requested_days

        try:
            await coordinator.api._request(
                "POST",
                f"/units/{coordinator.api.device_id}/programs/{actual_program_number}",
                json_data=payload,
            )
        except VeggaApiError as err:
            raise HomeAssistantError(
                "VEGGA rechazó el cambio de días. "
                "El programa se leyó justo antes del guardado y únicamente se "
                f"cambiaron monday..sunday. Detalle: {err}"
            ) from err

        # Update Home Assistant's coordinator cache immediately after VEGGA
        # confirms the POST. This prevents the frontend from momentarily
        # reverting to the old weekday state while the next cloud poll arrives.
        current_data = deepcopy(coordinator.data or {})
        cached_programs = list(current_data.get("programs", []))
        updated_programs: list[Any] = []

        for fallback, item in enumerate(cached_programs, start=1):
            if not isinstance(item, dict):
                updated_programs.append(item)
                continue

            cached = deepcopy(item)
            if _program_number(cached, fallback) == actual_program_number:
                for day in WEEKDAY_KEYS:
                    cached[day] = payload[day]
            updated_programs.append(cached)

        current_data["programs"] = updated_programs
        coordinator.async_set_updated_data(current_data)

        active = [key for key in WEEKDAY_KEYS if payload[key]]
        coordinator.record_command(
            f"Programa {actual_program_number}: días "
            + (", ".join(active) if active else "ninguno")
        )

        # Do not force an immediate cloud refresh here. VEGGA may need a brief
        # moment to expose the just-written data through GET; the normal
        # coordinator polling will reconcile it shortly afterwards.

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
