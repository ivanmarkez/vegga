from __future__ import annotations

import re
import unicodedata
from typing import Any


ACTIVE_TEXT = {
    "1",
    "true",
    "on",
    "active",
    "running",
    "executing",
    "in_progress",
    "watering",
    "activo",
    "ejecutando",
    "regando",
    "irrigating",
}


def is_active(item: dict[str, Any]) -> bool:
    """Return whether a VEGGA runtime row explicitly reports irrigation."""
    for key in (
        "active",
        "isActive",
        "running",
        "isRunning",
        "executing",
        "inProgress",
        "irrigation",
        "irrigating",
    ):
        value = item.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().casefold() in ACTIVE_TEXT

    status = item.get("status") or item.get("state")
    if isinstance(status, str) and status.strip().casefold() in ACTIVE_TEXT:
        return True

    program = item.get("xProgramN")
    try:
        return int(program) > 0
    except (TypeError, ValueError):
        return False


def sector_number(item: dict[str, Any], fallback: int | None = None) -> int | None:
    """Extract a one-based controller sector number without fuzzy ±1 matching."""
    pk = item.get("pk")
    values = (
        item.get("_agronic_number"),
        item.get("sector"),
        item.get("sectorNumber"),
        item.get("sector_number"),
        item.get("number"),
        pk.get("id") if isinstance(pk, dict) else None,
    )
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number >= 1:
            return number
    return fallback


def _normalized_name(item: dict[str, Any]) -> str:
    value = next(
        (
            item.get(key)
            for key in (
                "name",
                "description",
                "nombre",
                "sectorName",
                "sector_name",
                "label",
            )
            if item.get(key) not in (None, "")
        ),
        "",
    )
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _database_ids(item: dict[str, Any]) -> set[str]:
    pk = item.get("pk")
    values = (
        item.get("id"),
        item.get("sectorId"),
        item.get("sector_id"),
        pk.get("id") if isinstance(pk, dict) else None,
    )
    return {
        str(value).strip()
        for value in values
        if value not in (None, "")
    }


def _explicit_controller_number(item: dict[str, Any]) -> int | None:
    for key in (
        "_agronic_number",
        "sector",
        "sectorNumber",
        "sector_number",
        "number",
    ):
        try:
            number = int(item.get(key))
        except (TypeError, ValueError):
            continue
        if number >= 1:
            return number
    return None


def active_sector_numbers(
    runtime_rows: list[dict[str, Any]],
    configured_sectors: list[dict[str, Any]],
) -> set[int]:
    """Map VEGGA live rows to one-based controller sector numbers.

    Runtime rows may contain database IDs that are unrelated to the visible
    Agrónic sector number. Resolve those IDs against the configured sector list
    instead of treating them as controller numbers.
    """
    sector_count = len(configured_sectors)
    id_to_number: dict[str, int] = {}
    name_to_number: dict[str, int] = {}
    for position, sector in enumerate(configured_sectors, start=1):
        controller_number = _explicit_controller_number(sector) or position
        for database_id in _database_ids(sector):
            id_to_number[database_id] = controller_number
        name = _normalized_name(sector)
        if name:
            name_to_number[name] = controller_number

    dict_rows = [row for row in runtime_rows if isinstance(row, dict)]
    active_rows = [
        row
        for row in dict_rows
        if is_active(row)
    ]
    # VEGGA's irrigation=true endpoint is filtered on some firmware versions
    # and omits an explicit state flag. In that format every returned row is
    # active.
    if dict_rows and not active_rows:
        active_rows = dict_rows

    result: set[int] = set()
    same_shape = len(dict_rows) == sector_count
    for position, row in enumerate(dict_rows, start=1):
        if row not in active_rows:
            continue

        matched = next(
            (
                id_to_number[database_id]
                for database_id in _database_ids(row)
                if database_id in id_to_number
            ),
            None,
        )
        if matched is None:
            explicit = _explicit_controller_number(row)
            if explicit is not None and 1 <= explicit <= sector_count:
                matched = explicit
        if matched is None:
            name = _normalized_name(row)
            matched = name_to_number.get(name) if name else None
        if matched is None and same_shape:
            matched = position

        if matched is not None:
            result.add(matched)

    return result


def sector_is_irrigating(
    runtime_rows: list[dict[str, Any]],
    configured_sectors: list[dict[str, Any]],
    target_sector: int,
) -> bool:
    return target_sector in active_sector_numbers(runtime_rows, configured_sectors)
