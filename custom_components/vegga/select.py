from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import VeggaSectorEntity
from .runtime import program_for_sector, sector_is_irrigating

OPTIONS = ["Automático", "Marcha manual", "Paro manual"]

def _program_from_active_details(
    details: dict[Any, Any], target_sector: int
) -> int | None:
    """Resolve sector ownership from the same programSector row VEGGA displays."""
    for raw_program_number, detail in details.items():
        if not isinstance(detail, dict):
            continue
        rows = detail.get("programSector")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                active = int(row.get("xState", 0)) == 1
                sector = int(row.get("sector", 0))
            except (TypeError, ValueError):
                continue
            if not active or sector != target_sector:
                continue
            try:
                number = int(raw_program_number)
            except (TypeError, ValueError):
                for key in ("number", "program", "programNumber", "id"):
                    try:
                        number = int(detail.get(key))
                        break
                    except (TypeError, ValueError):
                        number = 0
            if number > 0:
                return number
    return None


def _sector_name(sector: dict[str, Any], fallback: int) -> str:
    for key in ("name", "description", "nombre", "sectorName", "sector_name", "label"):
        value = sector.get(key)
        if value not in (None, ""):
            return str(value)
    return f"Sector {fallback}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SelectEntity] = []
    for fallback, sector in enumerate((coordinator.data or {}).get("sectors", []), start=1):
        number = sector.get("_agronic_number")
        if not isinstance(number, int):
            number = fallback
        entities.append(VeggaSectorModeSelect(coordinator, number, _sector_name(sector, fallback)))
    async_add_entities(entities)


class VeggaSectorModeSelect(VeggaSectorEntity, SelectEntity):
    _attr_options = OPTIONS
    _attr_icon = "mdi:state-machine"

    def __init__(self, coordinator, sector_number: int, sector_name: str) -> None:
        super().__init__(coordinator, sector_number, sector_name)
        self._attr_name = "Modo de funcionamiento"
        self._attr_unique_id = f"{coordinator.api.device_id}_sector_{sector_number}_mode"

    @property
    def current_option(self) -> str:
        return self.coordinator.sector_mode(self._sector_number)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        sectors = data.get("sectors", [])
        runtime = data.get("irrigating_sectors", [])
        program_number = program_for_sector(runtime, sectors, self._sector_number)
        if program_number is None:
            program_number = _program_from_active_details(
                data.get("active_program_details", {}), self._sector_number
            )
        program_name = None
        programs = data.get("programs", [])
        if program_number is not None and 1 <= program_number <= len(programs):
            program = programs[program_number - 1]
            if isinstance(program, dict):
                program_name = next(
                    (
                        str(program.get(key))
                        for key in ("name", "description", "nombre", "programName")
                        if program.get(key) not in (None, "")
                    ),
                    None,
                )
        return {
            "sector_number": self._sector_number,
            "sector_name": self._sector_device_name,
            "irrigating": (
                program_number is not None
                or sector_is_irrigating(runtime, sectors, self._sector_number)
            ),
            "active_program_number": program_number,
            "active_program_name": program_name,
        }

    async def async_select_option(self, option: str) -> None:
        """Apply the selected sector mode to the Agrónic controller."""
        if option not in OPTIONS:
            raise ValueError(f"Modo de sector no válido: {option}")

        if option == "Marcha manual":
            await self.coordinator.api.start_sector(self._sector_number)
        elif option == "Paro manual":
            await self.coordinator.api.stop_sector(self._sector_number)
        else:
            await self.coordinator.api.automatic_sector(self._sector_number)

        self.coordinator.record_sector_mode(self._sector_number, option)
        self.coordinator.record_command(
            f"Sector {self._sector_device_name}: cambio a {option}"
        )
        await self.coordinator.async_request_refresh()
