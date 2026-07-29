from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import VeggaSectorEntity

OPTIONS = ["Automático", "Marcha manual", "Paro manual"]


def _sector_name(sector: dict[str, Any], fallback: int) -> str:
    for key in ("name", "description", "nombre", "sectorName", "sector_name", "label"):
        value = sector.get(key)
        if value not in (None, ""):
            return str(value)
    return f"Sector {fallback}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SelectEntity] = []
    for fallback, sector in enumerate((coordinator.data or {}).get("sectors", []), start=1):
        number = sector.get("_agronic_number")
        if not isinstance(number, int):
            number = fallback
        entities.append(VeggaSectorModeSelect(coordinator, number, _sector_name(sector, fallback)))
    async_add_entities(entities)


class VeggaSectorModeSelect(VeggaSectorEntity, SelectEntity):
    _attr_options = OPTIONS
    _attr_icon = "mdi:state-machine"

    def __init__(self, coordinator, sector_number: int, sector_name: str) -> None:
        super().__init__(coordinator, sector_number, sector_name)
        self._attr_name = "Modo de funcionamiento"
        self._attr_unique_id = f"{coordinator.api.device_id}_sector_{sector_number}_mode"

    @property
    def current_option(self) -> str:
        return self.coordinator.sector_mode(self._sector_number)

    async def async_select_option(self, option: str) -> None:
        """Apply the selected sector mode to the Agrónic controller."""
        if option not in OPTIONS:
            raise ValueError(f"Modo de sector no válido: {option}")

        if option == "Marcha manual":
            await self.coordinator.api.start_sector(self._sector_number)
        elif option == "Paro manual":
            await self.coordinator.api.stop_sector(self._sector_number)
        else:
            await self.coordinator.api.automatic_sector(self._sector_number)

        self.coordinator.record_sector_mode(self._sector_number, option)
        self.coordinator.record_command(
            f"Sector {self._sector_device_name}: cambio a {option}"
        )
        await self.coordinator.async_request_refresh()
