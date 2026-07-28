from __future__ import annotations

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
            now = datetime.now(timezone.utc)

            if self._history_due(now):
                try:
                    # The VEGGA web application calls this endpoint with
                    # sector=0 (all sectors) and pageNumber=1. The endpoint is
                    # 1-based; using page 0 or querying positional sector
                    # numbers can return an empty result.
                    history = await self.api.get_sector_history(
                        (now - timedelta(days=HISTORY_LOOKBACK_DAYS)).date(),
                        now.date(),
                        sector=0,
                        page_number=1,
                        page_size=HISTORY_PAGE_SIZE,
                    )

                    # Bind records to HA sectors by name. The returned sectorId
                    # is an internal history identifier and is not guaranteed
                    # to equal the sector position from /units/.../sectors.
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
                    for row in history:
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
                        normalized_history.append(item)

                    self._history = normalized_history
                    self.last_history_update = now
                except VeggaApiError as err:
                    self.api.history_debug = {
                        **self.api.history_debug,
                        "error": str(err),
                        "request_sector": 0,
                        "request_page_number": 1,
                    }
                    _LOGGER.warning("No se pudo actualizar el histórico VEGGA: %s", err)

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
