from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VeggaApi, VeggaApiError, VeggaAuthError
from .const import (
    DOMAIN,
    HISTORY_LOOKBACK_DAYS,
    HISTORY_PAGE_SIZE,
    HISTORY_REFRESH_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


class VeggaCoordinator(DataUpdateCoordinator[dict[str, list[dict[str, Any]]]]):
    """Coordinator for VEGGA live data and cached sector history."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: VeggaApi, scan_interval: int) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=scan_interval),
            config_entry=entry,
        )
        self.api = api
        self.last_successful_update: datetime | None = None
        self.last_history_update: datetime | None = None
        self.last_command: str | None = None
        self.last_command_at: datetime | None = None
        self._history: list[dict[str, Any]] = []
        self._live_payload_logged = False

    @staticmethod
    def _normalize_name(value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(char for char in text if not unicodedata.combining(char))
        return re.sub(r"[^a-z0-9]+", "", text.casefold())

    @staticmethod
    def _sector_number(sector: dict[str, Any], fallback: int) -> int:
        """Return the controller sector number used by VEGGA history/manual APIs."""
        value = sector.get("_agronic_number")
        if isinstance(value, int) and value >= 1:
            return value
        return fallback

    def _history_due(self, now: datetime) -> bool:
        return (
            self.last_history_update is None
            or now - self.last_history_update >= timedelta(minutes=HISTORY_REFRESH_MINUTES)
        )

    async def _async_update_data(self) -> dict[str, list[dict[str, Any]]]:
        try:
            programs = await self.api.get_programs()
            sectors = await self.api.get_sectors()
            unit_status = await self.api.get_unit_status()
            now = datetime.now(timezone.utc)

            # Temporary diagnostic: write the complete live controller snapshot
            # once after each Home Assistant restart. Warning level makes it
            # visible without requiring debug logging for the integration.
            if not self._live_payload_logged:
                try:
                    live_json = json.dumps(
                        unit_status,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        default=str,
                    )
                except (TypeError, ValueError):
                    live_json = repr(unit_status)
                _LOGGER.warning(
                    "VEGGA DIAGNÓSTICO ESTADO COMPLETO dispositivo=%s\n%s",
                    self.api.device_id,
                    live_json,
                )
                self._live_payload_logged = True

            if self._history_due(now):
                try:
                    # Keep the exact request shape that is confirmed to work in
                    # v0.4.6, then request the following 1-based pages. VEGGA
                    # reports pageNumber=0 in the response for request page 1.
                    from_date = (now - timedelta(days=HISTORY_LOOKBACK_DAYS)).date()
                    to_date = now.date()
                    history: list[dict[str, Any]] = []
                    pages_fetched: list[int] = []
                    page_errors: list[str] = []
                    seen_pages: set[str] = set()
                    total_elements: int | None = None

                    for request_page in range(1, 101):
                        try:
                            page_rows = await self.api.get_sector_history(
                                from_date,
                                to_date,
                                sector=0,
                                page_number=request_page,
                                page_size=HISTORY_PAGE_SIZE,
                            )
                        except VeggaApiError as err:
                            if not history:
                                raise
                            page_errors.append(f"Página {request_page}: {err}")
                            break

                        page_debug = dict(self.api.history_debug)
                        response_sample = page_debug.get("response_sample")
                        if isinstance(response_sample, dict):
                            try:
                                total_elements = int(response_sample.get("totalElements"))
                            except (TypeError, ValueError):
                                pass

                        # Stop if the server repeats a page instead of advancing.
                        marker = json.dumps(page_rows, sort_keys=True, ensure_ascii=False, default=str)
                        if marker in seen_pages:
                            page_errors.append(f"Página {request_page}: VEGGA repitió una página anterior")
                            break
                        seen_pages.add(marker)

                        pages_fetched.append(request_page)
                        history.extend(page_rows)

                        if total_elements is not None and len(history) >= total_elements:
                            break
                        if len(page_rows) < HISTORY_PAGE_SIZE:
                            break

                    # Remove duplicate records across pages.
                    unique_history: list[dict[str, Any]] = []
                    seen_rows: set[str] = set()
                    for row in history:
                        marker = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
                        if marker not in seen_rows:
                            seen_rows.add(marker)
                            unique_history.append(row)

                    # Bind records to HA sectors by normalized name. sectorId in
                    # the history response is an internal identifier.
                    sector_names: dict[str, tuple[int, str]] = {}
                    for fallback, sector_data in enumerate(sectors, start=1):
                        number = self._sector_number(sector_data, fallback)
                        name = next(
                            (
                                str(sector_data.get(key))
                                for key in ("name", "description", "nombre", "sectorName", "sector_name", "label")
                                if sector_data.get(key) not in (None, "")
                            ),
                            f"Sector {number}",
                        )
                        sector_names[self._normalize_name(name)] = (number, name)

                    normalized_history: list[dict[str, Any]] = []
                    matched_names: set[str] = set()
                    unmatched_names: set[str] = set()
                    for row in unique_history:
                        item = dict(row)
                        history_name = next(
                            (
                                str(item.get(key))
                                for key in ("sectorName", "sector_name", "name", "nombre", "description")
                                if item.get(key) not in (None, "")
                            ),
                            "",
                        )
                        match = sector_names.get(self._normalize_name(history_name))
                        if match:
                            item["_ha_sector_number"] = match[0]
                            item["_ha_sector_name"] = match[1]
                            matched_names.add(history_name)
                        elif history_name:
                            unmatched_names.add(history_name)
                        normalized_history.append(item)

                    self._history = normalized_history
                    self.last_history_update = now
                    self.api.history_debug = {
                        **self.api.history_debug,
                        "pages_fetched": pages_fetched,
                        "records_downloaded": len(history),
                        "parsed_record_count": len(unique_history),
                        "total_elements_reported": total_elements,
                        "matched_sector_names": sorted(matched_names),
                        "unmatched_sector_names": sorted(unmatched_names),
                        "page_errors": page_errors,
                    }
                except VeggaApiError as err:
                    self.api.history_debug = {
                        **self.api.history_debug,
                        "error": str(err),
                        "request_sector": 0,
                        "request_page_number": 1,
                    }
                    _LOGGER.warning("No se pudo actualizar el histórico VEGGA: %s", err)

            self.last_successful_update = now
            return {"programs": programs, "sectors": sectors, "unit_status": unit_status, "history": self._history, "history_debug": dict(self.api.history_debug)}
        except VeggaAuthError as err:
            raise ConfigEntryAuthFailed from err
        except VeggaApiError as err:
            raise UpdateFailed(str(err)) from err

    def record_command(self, command: str) -> None:
        self.last_command = command
        self.last_command_at = datetime.now(timezone.utc)
        self.async_update_listeners()
