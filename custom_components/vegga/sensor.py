from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import VeggaEntity, VeggaSectorEntity
from .history import analyse_sector, sector_volume_for_date


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
    value = item.get("_agronic_number")
    if isinstance(value, int) and value >= 1:
        return value
    return fallback


def _sector_name(sector: dict[str, Any], fallback: int) -> str:
    for key in ("name", "description", "nombre", "sectorName", "sector_name", "label"):
        value = sector.get(key)
        if value:
            return str(value)
    return f"Sector {fallback}"


def _runtime_program_number(sector: dict[str, Any]) -> int:
    for key in ("xProgramN", "xprogramn", "program", "programNumber", "programId"):
        value = sector.get(key)
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return 0


def _runtime_sector_number(sector: dict[str, Any], fallback: int = 0) -> int:
    pk = sector.get("pk")
    candidates = [
        sector.get("_agronic_number"),
        sector.get("sector"),
        sector.get("sectorNumber"),
        sector.get("number"),
        sector.get("id"),
        pk.get("id") if isinstance(pk, dict) else None,
    ]
    for value in candidates:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return fallback



def _sample_payload(value: Any, depth: int = 0) -> Any:
    if depth >= 5:
        return f"<{type(value).__name__}>"
    if isinstance(value, dict):
        return {str(k): _sample_payload(v, depth + 1) for k, v in list(value.items())[:40]}
    if isinstance(value, list):
        return [_sample_payload(v, depth + 1) for v in value[:8]]
    if isinstance(value, str):
        return value[:300]
    return value


def _find_active_refs(payload: Any, kind: str) -> list[dict[str, Any]]:
    """Best-effort extraction of active program/sector references."""
    results: list[dict[str, Any]] = []
    number_keys = {
        "program": ("program", "programnumber", "program_number", "programid", "program_id", "prog"),
        "sector": ("sector", "sectornumber", "sector_number", "sectorid", "sector_id"),
    }[kind]

    def walk(value: Any, path: str = "root") -> None:
        if isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, f"{path}[{i}]")
            return
        if not isinstance(value, dict):
            return
        normalized = {str(k).casefold().replace("-", "").replace("_", ""): v for k, v in value.items()}
        active = _is_active(value)
        ref = None
        for key in number_keys:
            nk = key.casefold().replace("-", "").replace("_", "")
            if nk in normalized and isinstance(normalized[nk], (int, float, str)):
                ref = normalized[nk]
                break
        path_l = path.casefold()
        if active and (ref is not None or kind in path_l):
            results.append({"reference": ref, "path": path, "data": _sample_payload(value, 0)})
        for key, child in value.items():
            walk(child, f"{path}.{key}")

    walk(payload)
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in results:
        marker = repr((item.get("reference"), item.get("path")))
        if marker not in seen:
            seen.add(marker)
            unique.append(item)
    return unique


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
        VeggaLiveStatusDiagnosticSensor(coordinator),
    ]
    for fallback, sector in enumerate((coordinator.data or {}).get("sectors", []), start=1):
        number = _sector_number(sector, fallback)
        name = _sector_name(sector, fallback)
        entities.extend([
            VeggaSectorConsumptionSensor(coordinator, number, name),
            VeggaSectorBaselineConsumptionSensor(coordinator, number, name),
            VeggaSectorConsumptionDeviationSensor(coordinator, number, name),
            VeggaSectorLastIrrigationSensor(coordinator, number, name),
            VeggaSectorLastDurationSensor(coordinator, number, name),
            VeggaSectorExpectedFlowSensor(coordinator, number, name),
            VeggaSectorActualFlowSensor(coordinator, number, name),
            VeggaSectorFlowDeviationSensor(coordinator, number, name),
        ])
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
        data = self.coordinator.data or {}
        runtime = data.get("irrigating_sectors", [])
        numbers = [_runtime_program_number(item) for item in runtime if isinstance(item, dict)]
        if not any(numbers):
            refs = _find_active_refs(data.get("unit_status"), "program")
            numbers = []
            for item in refs:
                try:
                    numbers.append(int(item.get("reference")))
                except (TypeError, ValueError):
                    pass
        names: list[str] = []
        programs = data.get("programs", [])
        for number in numbers:
            if 1 <= number <= len(programs):
                names.append(_program_name(programs[number - 1], number))
            elif number >= 0:
                # Some controller fields are zero-based.
                if 0 <= number < len(programs):
                    names.append(_program_name(programs[number], number + 1))
                else:
                    names.append(f"Programa {number}")
        return list(dict.fromkeys(names))

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
        data = self.coordinator.data or {}
        runtime = data.get("irrigating_sectors", [])
        numbers = [
            _runtime_sector_number(item, index)
            for index, item in enumerate(runtime, start=1)
            if isinstance(item, dict) and (_runtime_program_number(item) > 0 or _is_active(item))
        ]
        # The endpoint is already filtered with irrigation=true. Some firmware
        # versions omit an explicit active flag but still return only active rows.
        if runtime and not numbers:
            numbers = [
                _runtime_sector_number(item, index)
                for index, item in enumerate(runtime, start=1)
                if isinstance(item, dict)
            ]
        if not numbers:
            refs = _find_active_refs(data.get("unit_status"), "sector")
            numbers = []
            for item in refs:
                try:
                    numbers.append(int(item.get("reference")))
                except (TypeError, ValueError):
                    pass
        sectors = data.get("sectors", [])
        names: list[str] = []
        for number in numbers:
            if 1 <= number <= len(sectors):
                names.append(_sector_name(sectors[number - 1], number))
            elif 0 <= number < len(sectors):
                names.append(_sector_name(sectors[number], number + 1))
        return list(dict.fromkeys(names))

    @property
    def native_value(self) -> int:
        return len(self._active_names())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"active_sector_names": self._active_names()}



class VeggaLiveStatusDiagnosticSensor(VeggaEntity, SensorEntity):
    _attr_name = "Diagnóstico estado en tiempo real"
    _attr_icon = "mdi:access-point"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.api.device_id}_live_status_diagnostic"

    @property
    def native_value(self) -> str:
        payload = (self.coordinator.data or {}).get("unit_status")
        return "Estado recibido" if payload is not None else "Sin estado"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        payload = (self.coordinator.data or {}).get("unit_status")
        return {
            "top_level_keys": list(payload.keys()) if isinstance(payload, dict) else [],
            "active_program_candidates": _find_active_refs(payload, "program"),
            "active_sector_candidates": _find_active_refs(payload, "sector"),
            "response_sample": _sample_payload(payload),
        }


class VeggaSectorConsumptionSensor(VeggaSectorEntity, SensorEntity):
    """Last consumption and automatic baseline comparison for one sector."""

    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_device_class = SensorDeviceClass.VOLUME
    _attr_icon = "mdi:chart-bell-curve-cumulative"

    def __init__(self, coordinator, number: int, name: str) -> None:
        super().__init__(coordinator, number, name)
        self._number = number
        self._sector_name = name
        self._attr_name = "Consumo último riego"
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
        records = (self.coordinator.data or {}).get("history", [])
        yesterday = dt_util.now().date() - timedelta(days=1)
        yesterday_volume, yesterday_count = sector_volume_for_date(
            records, self._number, yesterday, dt_util.DEFAULT_TIME_ZONE
        )
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
            "expected_flow_m3h": analysis.expected_flow_m3h,
            "actual_flow_m3h": analysis.actual_flow_m3h,
            "vegga_flow_deviation_percent": analysis.vegga_flow_deviation_percent,
            "last_started_at": analysis.last_started_at,
            "last_ended_at": analysis.last_ended_at,
            "yesterday_volume_m3": yesterday_volume,
            "yesterday_irrigation_count": yesterday_count,
            "yesterday_date": yesterday.isoformat(),
        }




class _VeggaSectorAnalysisSensor(VeggaSectorEntity, SensorEntity):
    """Common base for one sector's historical analysis entities."""

    def __init__(self, coordinator, number: int, name: str) -> None:
        super().__init__(coordinator, number, name)
        self._number = number
        self._sector_name = name

    def _analysis(self):
        return analyse_sector(
            (self.coordinator.data or {}).get("history", []),
            self._number,
            self._sector_name,
        )

    @property
    def available(self) -> bool:
        return super().available and self._analysis().level != "unknown"


class VeggaSectorBaselineConsumptionSensor(_VeggaSectorAnalysisSensor):
    """Median of the previous usable irrigations for this sector."""

    _attr_name = "Consumo habitual"
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_device_class = SensorDeviceClass.VOLUME
    _attr_icon = "mdi:chart-timeline-variant"

    def __init__(self, coordinator, number: int, name: str) -> None:
        super().__init__(coordinator, number, name)
        self._attr_unique_id = f"{coordinator.api.device_id}_sector_{number}_baseline_consumption"

    @property
    def native_value(self) -> float | None:
        value = self._analysis().baseline_volume_m3
        return round(value, 3) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        analysis = self._analysis()
        return {
            "method": "Mediana de riegos anteriores",
            "sample_count": analysis.sample_count,
            "sector_number": analysis.sector_number,
        }


class VeggaSectorConsumptionDeviationSensor(_VeggaSectorAnalysisSensor):
    """Deviation of latest irrigation volume from the learned baseline."""

    _attr_name = "Desviación de consumo"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:percent-outline"

    def __init__(self, coordinator, number: int, name: str) -> None:
        super().__init__(coordinator, number, name)
        self._attr_unique_id = f"{coordinator.api.device_id}_sector_{number}_consumption_deviation"

    @property
    def native_value(self) -> float | None:
        value = self._analysis().deviation_percent
        return round(value, 2) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        analysis = self._analysis()
        return {
            "level": analysis.level,
            "last_volume_m3": analysis.last_volume_m3,
            "baseline_volume_m3": analysis.baseline_volume_m3,
            "interpretation": (
                "Consumo superior al habitual"
                if analysis.deviation_percent is not None and analysis.deviation_percent > 0
                else "Consumo inferior al habitual"
                if analysis.deviation_percent is not None and analysis.deviation_percent < 0
                else "Consumo dentro de lo habitual"
                if analysis.deviation_percent is not None
                else "Aprendiendo el consumo habitual"
            ),
        }


class VeggaSectorLastIrrigationSensor(_VeggaSectorAnalysisSensor):
    """Timestamp of the most recent irrigation recorded by VEGGA."""

    _attr_name = "Último riego"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, number: int, name: str) -> None:
        super().__init__(coordinator, number, name)
        self._attr_unique_id = f"{coordinator.api.device_id}_sector_{number}_last_irrigation"

    @property
    def native_value(self) -> datetime | None:
        analysis = self._analysis()
        return analysis.last_ended_at or analysis.last_started_at

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        analysis = self._analysis()
        return {
            "started_at": analysis.last_started_at,
            "ended_at": analysis.last_ended_at,
            "duration_minutes": analysis.last_duration_minutes,
            "volume_m3": analysis.last_volume_m3,
        }


class VeggaSectorLastDurationSensor(_VeggaSectorAnalysisSensor):
    """Duration of the latest irrigation."""

    _attr_name = "Duración último riego"
    _attr_native_unit_of_measurement = "min"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator, number: int, name: str) -> None:
        super().__init__(coordinator, number, name)
        self._attr_unique_id = f"{coordinator.api.device_id}_sector_{number}_last_duration"

    @property
    def native_value(self) -> float | None:
        value = self._analysis().last_duration_minutes
        return round(value, 1) if value is not None else None


class VeggaSectorExpectedFlowSensor(_VeggaSectorAnalysisSensor):
    """Expected flow reported by VEGGA for the latest irrigation."""

    _attr_name = "Caudal esperado"
    _attr_native_unit_of_measurement = "m³/h"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-check-outline"

    def __init__(self, coordinator, number: int, name: str) -> None:
        super().__init__(coordinator, number, name)
        self._attr_unique_id = f"{coordinator.api.device_id}_sector_{number}_expected_flow"

    @property
    def native_value(self) -> float | None:
        value = self._analysis().expected_flow_m3h
        return round(value, 3) if value is not None else None


class VeggaSectorActualFlowSensor(_VeggaSectorAnalysisSensor):
    """Actual flow reported by VEGGA for the latest irrigation."""

    _attr_name = "Caudal real"
    _attr_native_unit_of_measurement = "m³/h"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-sync"

    def __init__(self, coordinator, number: int, name: str) -> None:
        super().__init__(coordinator, number, name)
        self._attr_unique_id = f"{coordinator.api.device_id}_sector_{number}_actual_flow"

    @property
    def native_value(self) -> float | None:
        analysis = self._analysis()
        value = analysis.actual_flow_m3h
        if value is None:
            value = analysis.average_flow_m3h
        return round(value, 3) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        analysis = self._analysis()
        return {
            "source": "VEGGA" if analysis.actual_flow_m3h is not None else "Calculado por volumen y duración",
            "calculated_flow_m3h": analysis.average_flow_m3h,
        }


class VeggaSectorFlowDeviationSensor(_VeggaSectorAnalysisSensor):
    """Flow deviation reported by VEGGA for the latest irrigation."""

    _attr_name = "Desviación de caudal"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:swap-vertical-bold"

    def __init__(self, coordinator, number: int, name: str) -> None:
        super().__init__(coordinator, number, name)
        self._attr_unique_id = f"{coordinator.api.device_id}_sector_{number}_flow_deviation"

    @property
    def native_value(self) -> float | None:
        value = self._analysis().vegga_flow_deviation_percent
        return round(value, 2) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        analysis = self._analysis()
        return {
            "expected_flow_m3h": analysis.expected_flow_m3h,
            "actual_flow_m3h": analysis.actual_flow_m3h,
            "interpretation": (
                "Caudal superior al esperado"
                if analysis.vegga_flow_deviation_percent is not None and analysis.vegga_flow_deviation_percent > 0
                else "Caudal inferior al esperado"
                if analysis.vegga_flow_deviation_percent is not None and analysis.vegga_flow_deviation_percent < 0
                else "Caudal según lo esperado"
                if analysis.vegga_flow_deviation_percent is not None
                else "Sin dato de desviación"
            ),
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
