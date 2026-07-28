from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import VeggaEntity


def _program_number(program: dict[str, Any], fallback: int) -> int:
    for key in ("id", "number", "program", "programNumber", "pk"):
        value = program.get(key)
        if isinstance(value, int):
            # The programs endpoint may return either 0-based or 1-based ids.
            # VEGGA manual parameter1 is always zero-based, so entity calls use
            # the visible/fallback program number established below.
            if key in ("number", "program", "programNumber") and value >= 1:
                return value
    return fallback


def _program_name(program: dict[str, Any], fallback: int) -> str:
    for key in ("name", "description", "nombre", "programName"):
        value = program.get(key)
        if value:
            return str(value)
    return f"Programa {fallback}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = []

    for fallback, program in enumerate(coordinator.data or [], start=1):
        number = _program_number(program, fallback)
        name = _program_name(program, fallback)
        entities.extend(
            [
                VeggaProgramButton(
                    coordinator, number, name, True
                ),
                VeggaProgramButton(
                    coordinator, number, name, False
                ),
            ]
        )

    async_add_entities(entities)


class VeggaProgramButton(VeggaEntity, ButtonEntity):
    """Start or stop one irrigation program."""

    def __init__(
        self,
        coordinator,
        program_number: int,
        program_name: str,
        start: bool,
    ) -> None:
        super().__init__(coordinator)
        self._program_number = program_number
        self._start = start

        operation = "start" if start else "stop"
        operation_name = "Iniciar" if start else "Parar"
        self._attr_name = f"{operation_name} {program_name}"
        self._attr_unique_id = (
            f"{coordinator.api.device_id}_program_"
            f"{program_number}_{operation}"
        )
        self._attr_icon = "mdi:play" if start else "mdi:stop"

    async def async_press(self) -> None:
        if self._start:
            await self.coordinator.api.start_program(
                self._program_number
            )
        else:
            await self.coordinator.api.stop_program(
                self._program_number
            )
        await self.coordinator.async_request_refresh()
