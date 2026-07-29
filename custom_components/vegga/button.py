from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import VeggaEntity
from .runtime import is_active


def _number(item: dict[str, Any], fallback: int, keys: tuple[str, ...]) -> int:
    for key in keys:
        value = item.get(key)
        if isinstance(value, int):
            return value if value >= 1 else value + 1
        if isinstance(value, str) and value.strip().isdigit():
            number = int(value.strip())
            return number if number >= 1 else number + 1
    return fallback


def _name(item: dict[str, Any], fallback: str, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return fallback


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _program_runtime(
    programs: list[dict[str, Any]], program_number: int
) -> dict[str, Any] | None:
    """Return the live program row corresponding to a controller number."""
    for fallback, program in enumerate(programs, start=1):
        if not isinstance(program, dict):
            continue
        number = _number(
            program, fallback, ("number", "program", "programNumber", "id")
        )
        if number == program_number:
            return program
    return None


def _remaining_time(program: dict[str, Any]) -> tuple[int | None, str | None]:
    """Read the A-5500 current subprogram xValue using VEGGA's time formats."""
    subprograms = program.get("subprograms")
    if not isinstance(subprograms, list) or not subprograms:
        return None, None

    # A-5500 is one-based; A-4000 exposes the zero-based xSubprogramCourse.
    current = _integer(program.get("xSubProgramInProgress"))
    index = current - 1 if current and current > 0 else None
    if index is None:
        course = _integer(program.get("xSubprogramCourse"))
        index = course if course is not None and course >= 0 else None
    if index is None or index >= len(subprograms):
        return None, None

    subprogram = subprograms[index]
    if not isinstance(subprogram, dict):
        return None, None
    seconds = _integer(subprogram.get("xValue"))
    if seconds is None or seconds < 0:
        return None, None

    unit = _integer(subprogram.get("irrigUnits"))
    if unit is None:
        unit = _integer(subprogram.get("unit"))
    if unit is None:
        unit = _integer(program.get("irrigUnits"))

    # VEGGA A-5500: 0 = hours/minutes; 3 = minutes/seconds.
    if unit == 0:
        rounded_minutes = (seconds + 59) // 60
        hours, minutes = divmod(rounded_minutes, 60)
        return seconds, f"{hours:02d}:{minutes:02d}"
    if unit == 3:
        minutes, remaining_seconds = divmod(seconds, 60)
        return seconds, f"{minutes:02d}:{remaining_seconds:02d}"
    return None, None


def _remove_legacy_sector_buttons(
    hass: HomeAssistant,
    device_id: str,
    sector_numbers: list[int],
) -> None:
    """Remove obsolete sector buttons from the entity registry.

    Sector operation is now handled exclusively by the three-state select
    (Automatic / Manual start / Manual stop). This also clears entities left
    behind by versions prior to 0.4.20.
    """
    registry = er.async_get(hass)
    operations = ("start", "stop", "manual_start", "manual_stop", "automatic", "confirm_mode")

    for sector_number in sector_numbers:
        for operation in operations:
            unique_id = f"{device_id}_sector_{sector_number}_{operation}"
            entity_id = registry.async_get_entity_id("button", DOMAIN, unique_id)
            if entity_id is not None:
                registry.async_remove(entity_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    entities: list[ButtonEntity] = []

    # Program start/stop controls remain available.
    for fallback, program in enumerate(data.get("programs", []), start=1):
        number = _number(program, fallback, ("number", "program", "programNumber", "id"))
        name = _name(program, f"Programa {fallback}", ("name", "description", "nombre", "programName"))
        entities.extend(
            (
                VeggaProgramButton(coordinator, number, name, True),
                VeggaProgramButton(coordinator, number, name, False),
            )
        )

    sector_numbers: list[int] = []
    for fallback, sector in enumerate(data.get("sectors", []), start=1):
        number = sector.get("_agronic_number")
        sector_numbers.append(number if isinstance(number, int) else fallback)

    _remove_legacy_sector_buttons(
        hass,
        str(coordinator.api.device_id),
        sector_numbers,
    )

    async_add_entities(entities)


class VeggaProgramButton(VeggaEntity, ButtonEntity):
    def __init__(self, coordinator, program_number: int, program_name: str, start: bool) -> None:
        super().__init__(coordinator)
        self._number, self._item_name, self._start = program_number, program_name, start
        operation = "start" if start else "stop"
        self._attr_name = f"{'Iniciar' if start else 'Parar'} programa {program_name}"
        self._attr_unique_id = f"{coordinator.api.device_id}_program_{program_number}_{operation}"
        self._attr_icon = "mdi:play" if start else "mdi:stop"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        programs = (self.coordinator.data or {}).get("programs", [])
        program = _program_runtime(programs, self._number)
        active = bool(program and is_active(program))
        seconds, display = _remaining_time(program) if active and program else (None, None)
        return {
            "program_number": self._number,
            "program_name": self._item_name,
            "active": active,
            "remaining_seconds": seconds,
            "remaining_time": display,
        }

    async def async_press(self) -> None:
        if self._start:
            await self.coordinator.api.start_program(self._number)
        else:
            await self.coordinator.api.stop_program(self._number)
        self.coordinator.record_command(
            f"{'Iniciar' if self._start else 'Parar'} programa {self._item_name}"
        )
        await self.coordinator.async_request_refresh()
