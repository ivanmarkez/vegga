from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import VeggaEntity, VeggaSectorEntity


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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    entities: list[ButtonEntity] = []

    for fallback, program in enumerate(data.get("programs", []), start=1):
        number = _number(program, fallback, ("number", "program", "programNumber", "id"))
        name = _name(program, f"Programa {fallback}", ("name", "description", "nombre", "programName"))
        entities.extend((VeggaProgramButton(coordinator, number, name, True), VeggaProgramButton(coordinator, number, name, False)))

    for fallback, sector in enumerate(data.get("sectors", []), start=1):
        number = sector.get("_agronic_number") if isinstance(sector.get("_agronic_number"), int) else fallback
        name = _name(sector, f"Sector {fallback}", ("name", "description", "nombre", "sectorName"))
        entities.extend((VeggaSectorButton(coordinator, number, name, True), VeggaSectorButton(coordinator, number, name, False)))

    async_add_entities(entities)


class VeggaProgramButton(VeggaEntity, ButtonEntity):
    def __init__(self, coordinator, program_number: int, program_name: str, start: bool) -> None:
        super().__init__(coordinator)
        self._number, self._item_name, self._start = program_number, program_name, start
        operation = "start" if start else "stop"
        self._attr_name = f"{'Iniciar' if start else 'Parar'} programa {program_name}"
        self._attr_unique_id = f"{coordinator.api.device_id}_program_{program_number}_{operation}"
        self._attr_icon = "mdi:play" if start else "mdi:stop"

    async def async_press(self) -> None:
        if self._start:
            await self.coordinator.api.start_program(self._number)
        else:
            await self.coordinator.api.stop_program(self._number)
        self.coordinator.record_command(f"{'Iniciar' if self._start else 'Parar'} programa {self._item_name}")
        await self.coordinator.async_request_refresh()


class VeggaSectorButton(VeggaSectorEntity, ButtonEntity):
    def __init__(self, coordinator, sector_number: int, sector_name: str, start: bool) -> None:
        super().__init__(coordinator, sector_number, sector_name)
        self._number, self._item_name, self._start = sector_number, sector_name, start
        operation = "start" if start else "stop"
        self._attr_name = "Iniciar riego" if start else "Parar riego"
        self._attr_unique_id = f"{coordinator.api.device_id}_sector_{sector_number}_{operation}"
        self._attr_icon = "mdi:water" if start else "mdi:water-off"

    async def async_press(self) -> None:
        if self._start:
            await self.coordinator.api.start_sector(self._number)
        else:
            await self.coordinator.api.stop_sector(self._number)
        self.coordinator.record_command(f"{'Iniciar' if self._start else 'Parar'} sector {self._item_name}")
        await self.coordinator.async_request_refresh()
