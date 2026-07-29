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


def _format_remaining(value: Any, unit: Any) -> tuple[int | None, str | None]:
    """Format an A-5500 pending xValue using VEGGA's irrigation units."""
    seconds = _integer(value)
    unit_number = _integer(unit)
    if seconds is None or seconds < 0:
        return None, None

    # VEGGA A-5500: 0 = hours/minutes; 3 = minutes/seconds.
    if unit_number == 0:
        rounded_minutes = (seconds + 59) // 60
        hours, minutes = divmod(rounded_minutes, 60)
        return seconds, f"{hours:02d}:{minutes:02d}"
    if unit_number == 3:
        minutes, remaining_seconds = divmod(seconds, 60)
        return seconds, f"{minutes:02d}:{remaining_seconds:02d}"
    return None, None


def _program_unit(program: dict[str, Any]) -> int | None:
    for key in (
        "irrigUnits",
        "irrigUnitsSubp",
        "irrigationUnits",
        "unit",
        "units",
    ):
        unit = _integer(program.get(key))
        if unit is not None:
            return unit
    return None


def _remaining_time(
    program: dict[str, Any],
    program_number: int,
    irrigating_sectors: list[dict[str, Any]],
) -> tuple[int | None, str | None]:
    """Read pending time from the live A-5500 program or associated sector."""
    program_unit = _program_unit(program)

    # A-5500 program rows expose the current pending value directly. This is
    # the normal fallback when the list response contains ``subprograms: null``.
    direct = _format_remaining(program.get("xValue"), program_unit)
    if direct[1] is not None:
        return direct

    subprograms = program.get("subprograms")
    if isinstance(subprograms, list) and subprograms:
        # A-5500 is one-based; A-4000 exposes zero-based xSubprogramCourse.
        current = _integer(program.get("xSubProgramInProgress"))
        index = current - 1 if current and current > 0 else None
        if index is None:
            course = _integer(program.get("xSubprogramCourse"))
            index = course if course is not None and course >= 0 else None
        if index is not None and index < len(subprograms):
            subprogram = subprograms[index]
            if isinstance(subprogram, dict):
                subprogram_unit = _program_unit(subprogram)
                formatted = _format_remaining(
                    subprogram.get("xValue"),
                    subprogram_unit if subprogram_unit is not None else program_unit,
                )
                if formatted[1] is not None:
                    return formatted

    # The official A-5500 sector detail uses sector.xValue as the program's
    # pending value. Match it through xProgramN, using the program unit when
    # the sector row does not repeat the format.
    for sector in irrigating_sectors:
        if not isinstance(sector, dict) or not is_active(sector):
            continue
        referenced = _integer(sector.get("xProgramN"))
        if referenced != program_number:
            continue
        sector_unit = _program_unit(sector)
        formatted = _format_remaining(
            sector.get("xValue"),
            sector_unit if sector_unit is not None else program_unit,
        )
        if formatted[1] is not None:
            return formatted
    return None, None


def _program_is_active(
    program: dict[str, Any] | None,
    program_number: int,
    irrigating_sectors: list[dict[str, Any]],
) -> bool:
    """Resolve program activity from A-5500 live program and sector fields."""
    if program:
        # The official VEGGA program detail treats xState=0 as stopped and any
        # other state as a running, waiting, suspended, or finishing program.
        state = _integer(program.get("xState"))
        if state is not None:
            return state != 0
        if is_active(program):
            return True

    # The sectors endpoint is the authoritative live source already used for
    # the working active-sector counter. Scheduled irrigation identifies its
    # parent program through xProgramN.
    for sector in irrigating_sectors:
        if not isinstance(sector, dict) or not is_active(sector):
            continue
        referenced = None
        for key in ("xProgramN", "xprogramn", "program", "programNumber", "programId"):
            referenced = _integer(sector.get(key))
            if referenced is not None:
                break
        if referenced == program_number:
            return True
    return False


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
        data = self.coordinator.data or {}
        programs = data.get("programs", [])
        program = _program_runtime(programs, self._number)
        active = _program_is_active(
            program,
            self._number,
            data.get("irrigating_sectors", []),
        )
        seconds, display = (
            _remaining_time(
                program,
                self._number,
                data.get("irrigating_sectors", []),
            )
            if active and program
            else (None, None)
        )
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
