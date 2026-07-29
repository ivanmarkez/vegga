from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from statistics import median
from typing import Any

from .const import (
    ANOMALY_ALARM_PERCENT,
    ANOMALY_WARNING_PERCENT,
    BASELINE_SAMPLE_COUNT,
    MIN_BASELINE_SAMPLES,
)


@dataclass(frozen=True)
class SectorAnalysis:
    sector_number: int
    sector_name: str
    program_number: int | None
    program_name: str | None
    baseline_method: str
    baseline_sample_count: int
    sample_count: int
    last_volume_m3: float | None
    baseline_volume_m3: float | None
    deviation_percent: float | None
    last_duration_minutes: float | None
    average_flow_m3h: float | None
    expected_flow_m3h: float | None
    actual_flow_m3h: float | None
    vegga_flow_deviation_percent: float | None
    last_started_at: datetime | None
    last_ended_at: datetime | None
    level: str

    @property
    def anomalous(self) -> bool:
        return self.level in {"warning", "alarm"}


def _first(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lowered = {str(k).casefold(): v for k, v in item.items()}
    for key in keys:
        value = lowered.get(key.casefold())
        if value not in (None, ""):
            return value
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, dict):
        # VEGGA wraps measurements as {"value": 2.0, "unit": "CUBIC_METERS"}.
        for key in ("value", "actual", "expected", "deviation"):
            if key in value:
                parsed = _number(value[key])
                if parsed is not None:
                    return parsed
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"[-+]?\d+(?:[.,]\d+)?", value.replace(" ", ""))
        if match:
            try:
                return float(match.group(0).replace(",", "."))
            except ValueError:
                pass
    return None


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    for candidate in (text, text.replace(" ", "T")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _duration_minutes(value: Any) -> float | None:
    if isinstance(value, dict):
        number = _number(value.get("value"))
        unit = str(value.get("unit", "")).upper()
        if number is None:
            return None
        if unit in {"SECONDS", "SECOND"}:
            return number / 60.0
        if unit in {"HOURS", "HOUR"}:
            return number * 60.0
        return number
    if isinstance(value, (int, float)):
        number = float(value)
        # Most APIs expose seconds; small values are more plausibly minutes.
        return number / 60.0 if number > 300 else number
    if not isinstance(value, str):
        return None
    text = value.casefold().replace(" ", "")
    hours = re.search(r"(\d+(?:[.,]\d+)?)h", text)
    minutes = re.search(r"(\d+(?:[.,]\d+)?)min", text)
    seconds = re.search(r"(\d+(?:[.,]\d+)?)s", text)
    if hours or minutes or seconds:
        return (
            (_number(hours.group(1)) or 0) * 60
            + (_number(minutes.group(1)) or 0)
            + (_number(seconds.group(1)) or 0) / 60
        )
    if ":" in text:
        parts = text.split(":")
        try:
            if len(parts) == 3:
                h, m, s = map(float, parts)
                return h * 60 + m + s / 60
            if len(parts) == 2:
                m, s = map(float, parts)
                return m + s / 60
        except ValueError:
            return None
    return _number(text)


def sector_number(record: dict[str, Any]) -> int | None:
    value = _first(record, ("_ha_sector_number", "sector", "sectorId", "sector_id", "sectorNumber", "sector_number", "number"))
    number = _number(value)
    return int(number) if number is not None else None



def program_number(record: dict[str, Any]) -> int | None:
    """Extract the Agrónic program number associated with a history record."""
    value = _first(record, (
        "_ha_program_number", "program", "programId", "program_id",
        "programNumber", "program_number", "xProgramN", "xprogramn",
        "irrigationProgram", "irrigation_program", "programa",
    ))
    if isinstance(value, dict):
        value = _first(value, ("number", "id", "programNumber", "program_number", "value"))
    number = _number(value)
    return int(number) if number is not None and number > 0 else None


def program_name(record: dict[str, Any], number: int | None) -> str | None:
    value = _first(record, (
        "_ha_program_name", "programName", "program_name",
        "irrigationProgramName", "irrigation_program_name", "programaNombre",
    ))
    if value not in (None, ""):
        return str(value)
    return f"Programa {number}" if number is not None else None

def sector_name(record: dict[str, Any], fallback: str) -> str:
    value = _first(record, ("_ha_sector_name", "sectorName", "sector_name", "name", "nombre", "description"))
    return str(value) if value not in (None, "") else fallback


def volume_m3(record: dict[str, Any]) -> float | None:
    value = _first(record, (
        "volume", "volumen", "waterVolume", "water_volume", "irrigationVolume",
        "irrigation_volume", "totalVolume", "total_volume", "m3",
    ))
    number = _number(value)
    if number is None:
        return None
    # Explicit litre fields are converted; ordinary volume fields are assumed m³.
    keys = {str(k).casefold() for k in record}
    if keys & {"liters", "litres", "litros", "volume_liters", "volume_litres"}:
        return number / 1000.0
    return number


def duration_minutes(record: dict[str, Any]) -> float | None:
    value = _first(record, (
        "irrigationTime", "irrigation_time", "duration", "durationSeconds",
        "duration_seconds", "time", "tiempo", "wateringTime", "watering_time",
    ))
    return _duration_minutes(value)


def start_time(record: dict[str, Any]) -> datetime | None:
    return _datetime(_first(record, ("dateFrom", "date_from", "from", "start", "startDate", "start_date", "startedAt", "started_at", "date", "fecha")))


def end_time(record: dict[str, Any]) -> datetime | None:
    return _datetime(_first(record, ("dateTo", "date_to", "to", "end", "endDate", "end_date", "endedAt", "ended_at")))


def flow_values(record: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    flow = _first(record, ("flow", "caudal"))
    if not isinstance(flow, dict):
        return None, None, None
    return _number(flow.get("expected")), _number(flow.get("actual")), _number(flow.get("deviation"))



def sector_volume_for_date(
    records: list[dict[str, Any]],
    number: int,
    target_date: date,
    tzinfo,
) -> tuple[float | None, int]:
    """Return total irrigation volume and record count for one local calendar day."""
    total = 0.0
    count = 0
    for record in records:
        if sector_number(record) != number:
            continue
        stamp = start_time(record) or end_time(record)
        volume = volume_m3(record)
        if stamp is None or volume is None or volume <= 0:
            continue
        try:
            local_date = stamp.astimezone(tzinfo).date()
        except (ValueError, OSError):
            local_date = stamp.date()
        if local_date == target_date:
            total += volume
            count += 1
    return (round(total, 3), count) if count else (None, 0)

def analyse_sector(
    records: list[dict[str, Any]],
    number: int,
    name: str,
) -> SectorAnalysis:
    """Compare the latest irrigation with equivalent previous irrigations.

    Equivalent means the same sector and, whenever the history payload exposes
    it, the same Agrónic program. The baseline is the median of up to the last
    ten equivalent irrigations. If the latest record has no program metadata,
    the comparison falls back to the last ten irrigations of the sector.
    """
    matching = [record for record in records if sector_number(record) == number]
    matching.sort(key=lambda item: start_time(item) or end_time(item) or datetime.min.replace(tzinfo=timezone.utc))

    usable = [(record, volume_m3(record)) for record in matching]
    usable = [(record, volume) for record, volume in usable if volume is not None and volume > 0]
    if not usable:
        return SectorAnalysis(
            number, name, None, None, "Sin histórico", 0, 0, None, None, None,
            None, None, None, None, None, None, None, None, "unknown"
        )

    last_record, last_volume = usable[-1]
    last_program = program_number(last_record)
    last_program_name = program_name(last_record, last_program)

    previous_records = usable[:-1]
    baseline_method = "Últimos riegos del sector"
    equivalent = previous_records
    if last_program is not None:
        same_program = [
            (record, volume) for record, volume in previous_records
            if program_number(record) == last_program
        ]
        equivalent = same_program
        baseline_method = f"Mismo sector + programa {last_program}"

    baseline_values = [volume for _, volume in equivalent][-BASELINE_SAMPLE_COUNT:]
    baseline = median(baseline_values) if len(baseline_values) >= MIN_BASELINE_SAMPLES else None
    deviation = ((last_volume - baseline) / baseline * 100.0) if baseline and baseline > 0 else None

    level = "normal"
    if deviation is None:
        level = "learning"
    elif abs(deviation) >= ANOMALY_ALARM_PERCENT:
        level = "alarm"
    elif abs(deviation) >= ANOMALY_WARNING_PERCENT:
        level = "warning"

    duration = duration_minutes(last_record)
    calculated_flow = last_volume / (duration / 60.0) if duration and duration > 0 else None
    expected_flow, actual_flow, vegga_deviation = flow_values(last_record)
    return SectorAnalysis(
        number,
        sector_name(last_record, name),
        last_program,
        last_program_name,
        baseline_method,
        len(baseline_values),
        len(usable),
        last_volume,
        baseline,
        deviation,
        duration,
        calculated_flow,
        expected_flow,
        actual_flow,
        vegga_deviation,
        start_time(last_record),
        end_time(last_record),
        level,
    )

