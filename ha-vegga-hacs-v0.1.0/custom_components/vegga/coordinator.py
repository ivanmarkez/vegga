from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

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

    async def _async_update_data(self) -> list[dict[str, Any]]:
        try:
            return await self.api.get_programs()
        except VeggaAuthError as err:
            raise ConfigEntryAuthFailed from err
        except VeggaApiError as err:
            raise UpdateFailed(str(err)) from err
