from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VeggaApi, VeggaApiError, VeggaAuthError
from .const import DOMAIN


class VeggaCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Coordinator for VEGGA program data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: VeggaApi,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=scan_interval),
            config_entry=entry,
        )
        self.api = api
        self.last_successful_update: datetime | None = None
        self.last_command: str | None = None
        self.last_command_at: datetime | None = None

    async def _async_update_data(self) -> list[dict[str, Any]]:
        try:
            programs = await self.api.get_programs()
            self.last_successful_update = datetime.now(timezone.utc)
            return programs
        except VeggaAuthError as err:
            raise ConfigEntryAuthFailed from err
        except VeggaApiError as err:
            raise UpdateFailed(str(err)) from err

    def record_command(self, command: str) -> None:
        """Store the last manual command sent through Home Assistant."""
        self.last_command = command
        self.last_command_at = datetime.now(timezone.utc)
        self.async_update_listeners()
