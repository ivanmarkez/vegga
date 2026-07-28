from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import VeggaEntity


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
    async_add_entities([VeggaProgramsSensor(coordinator)])


class VeggaProgramsSensor(VeggaEntity, SensorEntity):
    """Summary sensor containing all discovered programs."""

    _attr_name = "Programas"
    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.api.device_id}_programs"
        )

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data or [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        programs = self.coordinator.data or []
        names = [
            _program_name(program, index)
            for index, program in enumerate(programs, start=1)
        ]
        return {
            "device_id": self.coordinator.api.device_id,
            "program_names": names,
            "note": "La numeración enviada a VEGGA comienza en cero.",
        }
