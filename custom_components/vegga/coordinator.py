from __future__ import annotations

import logging
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
            now = datetime.now(timezone.utc)

            if self._history_due(now):
                all_history: list[dict[str, Any]] = []
                diagnostics: list[dict[str, Any]] = []
                from_date = (now - timedelta(days=HISTORY_LOOKBACK_DAYS)).date()
                to_date = now.date()

                # VEGGA history expects the controller sector number (1..N),
                # pageNumber=0 and the normal web page size (20). sector=0
                # produces HTTP 500 on this controller.
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
                    try:
                        rows = await self.api.get_sector_history(
                            from_date,
                            to_date,
                            sector=number,
                            page_number=0,
                            page_size=20,
                        )
                    except VeggaApiError as err:
                        diagnostics.append({"sector": number, "name": name, "error": str(err)})
                        continue

                    for row in rows:
                        item = dict(row)
                        item["_ha_sector_number"] = number
                        item["_ha_sector_name"] = name
                        all_history.append(item)
                    diagnostics.append({"sector": number, "name": name, "records": len(rows)})

                self._history = all_history
                self.last_history_update = now
                self.api.history_debug = {
                    "mode": "per_sector_page_0",
                    "page_size": 20,
                    "sectors_checked": len(sectors),
                    "records": len(all_history),
                    "sector_results": diagnostics[:50],
                }

            self.last_successful_update = now
            return {"programs": programs, "sectors": sectors, "history": self._history, "history_debug": dict(self.api.history_debug)}
        except VeggaAuthError as err:
            raise ConfigEntryAuthFailed from err
        except VeggaApiError as err:
            raise UpdateFailed(str(err)) from err

    def record_command(self, command: str) -> None:
        self.last_command = command
        self.last_command_at = datetime.now(timezone.utc)
        self.async_update_listeners()
