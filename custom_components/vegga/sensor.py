from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
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


def _is_active(program: dict[str, Any]) -> bool:
    """Best-effort detection across common VEGGA program status fields."""
    for key in ("active", "isActive", "running", "isRunning", "executing", "inProgress"):
        value = program.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
    for key in ("status", "state", "estado"):
        value = program.get(key)
        if isinstance(value, str) and value.strip().lower() in {
            "active", "running", "executing", "in_progress", "watering",
            "activo", "ejecutando", "regando",
        }:
            return True
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            VeggaProgramsSensor(coordinator),
            VeggaActiveProgramsSensor(coordinator),
            VeggaLastCommandSensor(coordinator),
            VeggaLastUpdateSensor(coordinator),
        ]
    )


class VeggaProgramsSensor(VeggaEntity, SensorEntity):
    _attr_name = "Programas"
    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.api.device_id}_programs"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data or [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        programs = self.coordinator.data or []
        return {
            "device_id": self.coordinator.api.device_id,
            "program_names": [
                _program_name(program, index)
                for index, program in enumerate(programs, start=1)
            ],
        }


class VeggaActiveProgramsSensor(VeggaEntity, SensorEntity):
    _attr_name = "Programas activos"
    _attr_icon = "mdi:water-pump"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.api.device_id}_active_programs"

    @property
    def native_value(self) -> int:
        return len(self._active_names())

    def _active_names(self) -> list[str]:
        return [
            _program_name(program, index)
            for index, program in enumerate(self.coordinator.data or [], start=1)
            if _is_active(program)
        ]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"active_program_names": self._active_names()}


class VeggaLastCommandSensor(VeggaEntity, SensorEntity):
    _attr_name = "Última orden"
    _attr_icon = "mdi:history"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.api.device_id}_last_command"

    @property
    def native_value(self) -> str:
        return self.coordinator.last_command or "Ninguna"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"sent_at": self.coordinator.last_command_at}


class VeggaLastUpdateSensor(VeggaEntity, SensorEntity):
    _attr_name = "Última actualización"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:cloud-sync"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.api.device_id}_last_update"

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_successful_update
