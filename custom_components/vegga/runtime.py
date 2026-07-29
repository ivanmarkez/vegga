from __future__ import annotations

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


def sector_is_irrigating(
    rows: list[dict[str, Any]],
    target_sector: int,
) -> bool:
    """Return the explicit live irrigation state for one sector."""
    for position, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            continue
        if sector_number(item, position) == target_sector:
            return is_active(item)
    return False
