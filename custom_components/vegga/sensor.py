from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import VeggaEntity
from .history import analyse_sector


def _program_name(program: dict[str, Any], fallback: int) -> str:
    for key in ("name", "description", "nombre", "programName"):
        value = program.get(key)
        if value:
            return str(value)
    return f"Programa {fallback}"


def _is_active(item: dict[str, Any]) -> bool:
    for key in ("active", "isActive", "running", "isRunning", "executing", "inProgress", "enabled", "irrigating"):
        value = item.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
    for key in ("status", "state", "estado"):
        value = item.get(key)
        if isinstance(value, str) and value.strip().lower() in {
            "active", "running", "executing", "in_progress", "watering",
            "activo", "ejecutando", "regando", "on", "irrigating",
        }:
            return True
    return False


def _sector_number(item: dict[str, Any], fallback: int) -> int:
    for key in ("number", "sector", "sectorNumber", "sector_number", "id"):
        value = item.get(key)
        if isinstance(value, int):
            return value if value >= 1 else value + 1
        if isinstance(value, str) and value.strip().isdigit():
            number = int(value.strip())
            return number if number >= 1 else number + 1
    return fallback


def _sector_name(sector: dict[str, Any], fallback: int) -> str:
    for key in ("name", "description", "nombre", "sectorName", "sector_name", "label"):
        value = sector.get(key)
        if value:
            return str(value)
    return f"Sector {fallback}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        VeggaProgramsSensor(coordinator),
        VeggaActiveProgramsSensor(coordinator),
        VeggaSectorsSensor(coordinator),
        VeggaActiveSectorsSensor(coordinator),
        VeggaAnomalyCountSensor(coordinator),
        VeggaLastCommandSensor(coordinator),
        VeggaLastUpdateSensor(coordinator),
        VeggaLastHistoryUpdateSensor(coordinator),
        VeggaHistoryDiagnosticSensor(coordinator),
    ]
    for fallback, sector in enumerate((coordinator.data or {}).get("sectors", []), start=1):
        entities.append(
            VeggaSectorConsumptionSensor(
                coordinator,
                _sector_number(sector, fallback),
                _sector_name(sector, fallback),
            )
        )
    async_add_entities(entities)


class VeggaProgramsSensor(VeggaEntity, SensorEntity):
    _attr_name = "Programas"
    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.api.device_id}_programs"

    @property
    def native_value(self) -> int:
        return len((self.coordinator.data or {}).get("programs", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        programs = (self.coordinator.data or {}).get("programs", [])
        return {
            "device_id": self.coordinator.api.device_id,
            "program_names": [_program_name(program, index) for index, program in enumerate(programs, start=1)],
        }


class VeggaActiveProgramsSensor(VeggaEntity, SensorEntity):
    _attr_name = "Programas activos"
    _attr_icon = "mdi:water-pump"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.api.device_id}_active_programs"

    def _active_names(self) -> list[str]:
        return [
            _program_name(program, index)
            for index, program in enumerate((self.coordinator.data or {}).get("programs", []), start=1)
            if _is_active(program)
        ]

    @property
    def native_value(self) -> int:
        return len(self._active_names())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"active_program_names": self._active_names()}


class VeggaSectorsSensor(VeggaEntity, SensorEntity):
    _attr_name = "Sectores"
    _attr_icon = "mdi:pipe-valve"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.api.device_id}_sectors"

    @property
    def native_value(self) -> int:
        return len((self.coordinator.data or {}).get("sectors", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        sectors = (self.coordinator.data or {}).get("sectors", [])
        return {"sector_names": [_sector_name(s, i) for i, s in enumerate(sectors, 1)]}


class VeggaActiveSectorsSensor(VeggaEntity, SensorEntity):
    _attr_name = "Sectores activos"
    _attr_icon = "mdi:water-pump"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.api.device_id}_active_sectors"

    def _active_names(self) -> list[str]:
        return [_sector_name(s, i) for i, s in enumerate((self.coordinator.data or {}).get("sectors", []), 1) if _is_active(s)]

    @property
    def native_value(self) -> int:
        return len(self._active_names())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"active_sector_names": self._active_names()}


class VeggaSectorConsumptionSensor(VeggaEntity, SensorEntity):
    """Last consumption and automatic baseline comparison for one sector."""

    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_device_class = SensorDeviceClass.VOLUME
    _attr_icon = "mdi:chart-bell-curve-cumulative"

    def __init__(self, coordinator, number: int, name: str) -> None:
        super().__init__(coordinator)
        self._number = number
        self._sector_name = name
        self._attr_name = f"Consumo {name}"
        self._attr_unique_id = f"{coordinator.api.device_id}_sector_{number}_consumption_analysis"

    def _analysis(self):
        return analyse_sector((self.coordinator.data or {}).get("history", []), self._number, self._sector_name)

    @property
    def native_value(self) -> float | None:
        return self._analysis().last_volume_m3

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        analysis = self._analysis()
        direction = None
        if analysis.deviation_percent is not None:
            direction = "alto" if analysis.deviation_percent > 0 else "bajo"
        return {
            "sector_number": analysis.sector_number,
            "sector_name": analysis.sector_name,
            "baseline_volume_m3": analysis.baseline_volume_m3,
            "deviation_percent": analysis.deviation_percent,
            "deviation_direction": direction,
            "analysis_level": analysis.level,
            "sample_count": analysis.sample_count,
            "last_duration_minutes": analysis.last_duration_minutes,
            "average_flow_m3h": analysis.average_flow_m3h,
            "last_started_at": analysis.last_started_at,
            "last_ended_at": analysis.last_ended_at,
        }


class VeggaAnomalyCountSensor(VeggaEntity, SensorEntity):
    _attr_name = "Sectores con consumo anómalo"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.api.device_id}_history_anomaly_count"

    def _analyses(self):
        sectors = (self.coordinator.data or {}).get("sectors", [])
        history = (self.coordinator.data or {}).get("history", [])
        return [analyse_sector(history, _sector_number(s, i), _sector_name(s, i)) for i, s in enumerate(sectors, 1)]

    @property
    def native_value(self) -> int:
        return sum(analysis.anomalous for analysis in self._analyses())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "anomalies": [
                {
                    "sector": a.sector_name,
                    "level": a.level,
                    "deviation_percent": a.deviation_percent,
                    "last_volume_m3": a.last_volume_m3,
                    "baseline_volume_m3": a.baseline_volume_m3,
                }
                for a in self._analyses()
                if a.anomalous
            ]
        }


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


class VeggaLastHistoryUpdateSensor(VeggaEntity, SensorEntity):
    _attr_name = "Última actualización del histórico"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:database-clock"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.api.device_id}_last_history_update"

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_history_update


class VeggaHistoryDiagnosticSensor(VeggaEntity, SensorEntity):
    """Expose the last history response shape for temporary diagnostics."""

    _attr_name = "Diagnóstico histórico VEGGA"
    _attr_icon = "mdi:bug-outline"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.api.device_id}_history_diagnostic"

    @property
    def native_value(self) -> str:
        debug = (self.coordinator.data or {}).get("history_debug", {})
        count = debug.get("parsed_record_count")
        return f"{count} registros interpretados" if count is not None else "Sin diagnóstico"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("history_debug", {})
