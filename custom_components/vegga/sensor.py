from __future__ import annotations

from datetime import datetime, timedelta
import re
import unicodedata
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import VeggaEntity, VeggaSectorEntity
from .history import analyse_sector, sector_volume_for_date
from .runtime import active_sector_numbers


def _program_name(program: dict[str, Any], fallback: int) -> str:
    for key in ("name", "description", "nombre", "programName"):
        value = program.get(key)
        if value:
            return str(value)
    return f"Programa {fallback}"


def _is_active(item: dict[str, Any]) -> bool:
    if item.get("xStatus") is not None:
        try:
            return int(item["xStatus"]) not in {0, 3, 5, 6}
        except (TypeError, ValueError):
            pass
    for key in ("active", "isActive", "running", "isRunning", "executing", "inProgress", "irrigation", "irrigating"):
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


def _normalized_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"[-+]?\d+(?:[.,]\d+)?", value)
        if match:
            try:
                return float(match.group().replace(",", "."))
            except ValueError:
                pass
    return None


def _analog_format(data: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    formats = data.get("analog_formats", [])
    try:
        format_id = int(row.get("formatId"))
    except (TypeError, ValueError):
        return {}
    if 1 <= format_id <= len(formats) and isinstance(formats[format_id - 1], dict):
        return formats[format_id - 1]
    for item in formats:
        if not isinstance(item, dict):
            continue
        pk = item.get("pk")
        candidates = (item.get("id"), pk.get("id") if isinstance(pk, dict) else None)
        if format_id in candidates:
            return item
    return {}


def _analog_unit(fmt: dict[str, Any]) -> str | None:
    for key in ("units", "unit", "suffix", "symbol"):
        if fmt.get(key):
            return str(fmt[key]).strip()
    pattern = fmt.get("format")
    if isinstance(pattern, str):
        parts = pattern.strip().split()
        if len(parts) > 1:
            return parts[-1]
    return None


def _find_nested_value(value: Any, wanted_key: str) -> Any:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() == wanted_key.casefold():
                return child
        for child in value.values():
            found = _find_nested_value(child, wanted_key)
            if found not in (None, "", 0, "0"):
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_nested_value(child, wanted_key)
            if found not in (None, "", 0, "0"):
                return found
    return None


def _analog_row(data: dict[str, Any], kind: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    # This is the selection rule used by VEGGA for A-5500: checkCE/checkPH
    # contain the one-based analogue input assigned to fertilization control.
    config_keys = {
        "ph": ("checkPH", "securityPH"),
        "ec": ("checkCE", "securityCE"),
        "pressure": (),
    }[kind]
    configured_input = None
    for config_key in config_keys:
        configured_input = _find_nested_value(data.get("unit_status"), config_key)
        if configured_input in (None, "", 0, "0"):
            configured_input = _find_nested_value(data.get("fertilizer_config"), config_key)
        if configured_input not in (None, "", 0, "0"):
            break
    try:
        configured_input = int(configured_input)
    except (TypeError, ValueError):
        configured_input = 0

    analogs = [row for row in data.get("analogs", []) if isinstance(row, dict)]
    if configured_input > 0:
        for position, row in enumerate(analogs, start=1):
            pk = row.get("pk")
            candidates = (
                position,
                row.get("input"),
                row.get("id"),
                pk.get("id") if isinstance(pk, dict) else None,
            )
            for candidate in candidates:
                try:
                    if int(candidate) == configured_input:
                        return row, _analog_format(data, row)
                except (TypeError, ValueError):
                    continue

    for row in data.get("analogs", []):
        if not isinstance(row, dict) or row.get("input") == 0:
            continue
        fmt = _analog_format(data, row)
        label = " ".join(
            str(row.get(key, "")) for key in ("name", "description", "label", "sensorName")
        )
        haystack = f"{_normalized_text(label)} {_normalized_text(_analog_unit(fmt))}"
        if kind == "ph" and re.search(r"(^|[^a-z])ph([^a-z]|$)", haystack):
            return row, fmt
        if kind == "ec" and (
            "conductividad" in haystack
            or "conductivity" in haystack
            or re.search(r"(^|[^a-z])(ce|ec|ms)([^a-z]|$)", haystack)
        ):
            return row, fmt
        if kind == "pressure" and (
            "presion" in haystack
            or "pressure" in haystack
            or re.search(r"(^|[^a-z])(bar|bars)([^a-z]|$)", haystack)
        ):
            return row, fmt

    # Confirmed directly in VEGGA for Agrónic 17669 (A-5500 firmware 1.32):
    # analogue 1 is EC and analogue 2 is pH. The controller does not expose
    # checkPH/checkCE in this configuration, so use their visible positions.
    fallback_position = {"ec": 1, "ph": 2, "pressure": 3}[kind]
    if len(analogs) >= fallback_position:
        row = analogs[fallback_position - 1]
        return row, _analog_format(data, row)
    return None


def _analog_value(
    row: dict[str, Any],
    fmt: dict[str, Any],
    *,
    default_decimals: int = 0,
    force_decimals: int | None = None,
) -> float | None:
    for key in ("formattedValue", "reading"):
        value = _number(row.get(key))
        if value is not None:
            return value
    value = _number(row.get("xValue"))
    if value is None:
        value = _number(row.get("currentValue"))
    if value is None:
        value = _number(row.get("value"))
    if value is None:
        return None
    try:
        decimals = force_decimals if force_decimals is not None else int(
            fmt.get("decimals", default_decimals)
        )
    except (TypeError, ValueError):
        decimals = default_decimals
    return value / (10 ** decimals)


def _ph_regulation_value(data: dict[str, Any]) -> float | None:
    """Return the live pH value exposed by A-5500 regulation."""
    fertilizer = _find_nested_value(data.get("unit_status"), "fertilizer")
    if not isinstance(fertilizer, dict):
        fertilizer = _find_nested_value(data.get("fertilizer_config"), "fertilizer")
    if not isinstance(fertilizer, dict):
        return None
    regulations = fertilizer.get("pidRegulation")
    if not isinstance(regulations, list) or len(regulations) < 2:
        return None
    ph_regulation = regulations[1]
    if not isinstance(ph_regulation, dict):
        return None
    value = _number(ph_regulation.get("xValue"))
    if value is None:
        return None
    return value / 10 if abs(value) > 14 else value


def _meter_row(data: dict[str, Any]) -> dict[str, Any] | None:
    rows = [row for row in data.get("meters", []) if isinstance(row, dict)]
    configured = [row for row in rows if row.get("input") not in (None, 0, "0")]
    return (configured or rows or [None])[0]


class VeggaAnalogSensor(VeggaEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, kind: str) -> None:
        super().__init__(coordinator)
        self._kind = kind
        self._attr_name = {
            "ph": "pH",
            "ec": "Conductividad",
            "pressure": "Presión",
        }[kind]
        self._attr_icon = {
            "ph": "mdi:ph",
            "ec": "mdi:flash",
            "pressure": "mdi:gauge",
        }[kind]
        self._attr_unique_id = f"{coordinator.api.device_id}_{kind}"

    def _source(self):
        return _analog_row(self.coordinator.data or {}, self._kind)

    @property
    def native_value(self) -> float | None:
        source = self._source()
        if source:
            value = _analog_value(*source, default_decimals=1, force_decimals=1)
            if value is not None:
                return value
        return _ph_regulation_value(self.coordinator.data or {}) if self._kind == "ph" else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        source = self._source()
        unit = _analog_unit(source[1]) if source else None
        return unit or {"ph": "pH", "ec": "mS", "pressure": "bar"}[self._kind]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        source = self._source()
        config_keys = {
            "ph": ("checkPH", "securityPH"),
            "ec": ("checkCE", "securityCE"),
            "pressure": (),
        }[self._kind]
        configured_input = None
        configured_from = None
        for config_key in config_keys:
            configured_input = _find_nested_value(
                (self.coordinator.data or {}).get("unit_status"), config_key
            )
            if configured_input in (None, "", 0, "0"):
                configured_input = _find_nested_value(
                    (self.coordinator.data or {}).get("fertilizer_config"), config_key
                )
            if configured_input not in (None, "", 0, "0"):
                configured_from = config_key
                break
        return {
            "source": "VEGGA analogs",
            "configured_analog": configured_input,
            "configured_from": configured_from,
            "input": source[0].get("input") if source else None,
            "analog_id": (
                source[0].get("pk", {}).get("id")
                if source and isinstance(source[0].get("pk"), dict)
                else source[0].get("id") if source else None
            ),
            "format_id": source[0].get("formatId") if source else None,
            "raw_value": source[0].get("xValue") if source else None,
            "regulation_value": (
                _ph_regulation_value(self.coordinator.data or {})
                if self._kind == "ph"
                else None
            ),
            "analog_count": len((self.coordinator.data or {}).get("analogs", [])),
        }


class VeggaPressureSensor(VeggaAnalogSensor):
    """Pressure from the third analogue input of Agrónic 17669."""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "pressure")
        # Use a fresh, explicit registry id so Home Assistant cannot retain a
        # failed generic pressure entity from a previous platform load.
        self._attr_unique_id = f"{coordinator.api.device_id}_analog_pressure"

    @property
    def native_unit_of_measurement(self) -> str:
        return "bar"


class VeggaFlowMeterSensor(VeggaEntity, SensorEntity):
    _attr_name = "Caudalímetro"
    _attr_icon = "mdi:water-pump"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.api.device_id}_flow_meter"

    @property
    def native_value(self) -> float | None:
        row = _meter_row(self.coordinator.data or {})
        if not row:
            return None
        direct = _number(row.get("value"))
        if direct is not None:
            return direct
        raw = _number(row.get("xFlow"))
        return raw / 100 if raw is not None else None

    @property
    def native_unit_of_measurement(self) -> str:
        row = _meter_row(self.coordinator.data or {}) or {}
        units = {0: "m³/h", 1: "L/h", 2: "L/s"}
        try:
            return units.get(int(row.get("flowFormat")), "m³/h")
        except (TypeError, ValueError):
            return "m³/h"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        row = _meter_row(self.coordinator.data or {}) or {}
        return {
            "source": "VEGGA meters",
            "input": row.get("input"),
            "active": row.get("xActive", row.get("active")),
            "raw_flow": row.get("xFlow"),
        }


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

    # Remove obsolete entities that were created by earlier releases but are
    # no longer backed by a working data source. Merely ceasing to add them
    # leaves grey "No disponible" entries in Home Assistant's registry.
    registry = er.async_get(hass)
    obsolete_unique_ids = (
        f"{coordinator.api.device_id}_pressure",
        f"{coordinator.api.device_id}_history_anomaly_count",
    )
    for unique_id in obsolete_unique_ids:
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        if entity_id is not None:
            registry.async_remove(entity_id)

    entities: list[SensorEntity] = [
        VeggaProgramsSensor(coordinator),
        VeggaActiveProgramsSensor(coordinator),
        VeggaSectorsSensor(coordinator),
        VeggaActiveSectorsSensor(coordinator),
        VeggaLastCommandSensor(coordinator),
        VeggaLastUpdateSensor(coordinator),
        VeggaLastHistoryUpdateSensor(coordinator),
        VeggaHistoryDiagnosticSensor(coordinator),
        VeggaLiveStatusDiagnosticSensor(coordinator),
        VeggaAnalogSensor(coordinator, "ph"),
        VeggaAnalogSensor(coordinator, "ec"),
        VeggaPressureSensor(coordinator),
        VeggaFlowMeterSensor(coordinator),
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
        if not any(numbers):
            numbers = [
                index
                for index, program in enumerate(data.get("programs", []), start=1)
                if isinstance(program, dict) and _is_active(program)
            ]
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
        sectors = data.get("sectors", [])
        numbers = sorted(active_sector_numbers(runtime, sectors))
        if not numbers:
            refs = _find_active_refs(data.get("unit_status"), "sector")
            numbers = []
            for item in refs:
                try:
                    numbers.append(int(item.get("reference")))
                except (TypeError, ValueError):
                    pass
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
        runtime = (self.coordinator.data or {}).get("irrigating_sectors", [])
        return {
            "top_level_keys": list(payload.keys()) if isinstance(payload, dict) else [],
            "active_program_candidates": _find_active_refs(payload, "program"),
            "active_sector_candidates": _find_active_refs(payload, "sector"),
            "irrigating_sector_row_count": len(runtime) if isinstance(runtime, list) else 0,
            "irrigating_sector_sample": _sample_payload(runtime),
            "analog_sensor_count": len((self.coordinator.data or {}).get("analogs", [])),
            "analog_sensor_sample": _sample_payload((self.coordinator.data or {}).get("analogs", [])),
            "analog_format_sample": _sample_payload((self.coordinator.data or {}).get("analog_formats", [])),
            "fertilizer_config_sample": _sample_payload((self.coordinator.data or {}).get("fertilizer_config")),
            "meter_count": len((self.coordinator.data or {}).get("meters", [])),
            "meter_sample": _sample_payload((self.coordinator.data or {}).get("meters", [])),
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
            "program_number": analysis.program_number,
            "program_name": analysis.program_name,
            "baseline_method": analysis.baseline_method,
            "baseline_sample_count": analysis.baseline_sample_count,
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
    """Median of the last equivalent irrigations for this sector."""

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
            "method": analysis.baseline_method,
            "program_number": analysis.program_number,
            "program_name": analysis.program_name,
            "baseline_sample_count": analysis.baseline_sample_count,
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
            "program_number": analysis.program_number,
            "program_name": analysis.program_name,
            "baseline_method": analysis.baseline_method,
            "baseline_sample_count": analysis.baseline_sample_count,
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
