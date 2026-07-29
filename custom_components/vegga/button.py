from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import VeggaEntity, VeggaSectorEntity


def _number(item: dict[str, Any], fallback: int, keys: tuple[str, ...]) -> int:
    for key in keys:
        value = item.get(key)
        if isinstance(value, int):
            return value if value >= 1 else value + 1
        if isinstance(value, str) and value.strip().isdigit():
            number = int(value.strip())
            return number if number >= 1 else number + 1
    return fallback


def _name(item: dict[str, Any], fallback: str, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return fallback


def _remove_legacy_sector_buttons(
    hass: HomeAssistant,
    device_id: str,
    sector_numbers: list[int],
) -> None:
    """Remove obsolete sector buttons from the entity registry.

    Sector operation is now handled exclusively by the three-state select
    (Automatic / Manual start / Manual stop). This also clears entities left
    behind by versions prior to 0.4.20.
    """
    registry = er.async_get(hass)
    operations = ("start", "stop", "manual_start", "manual_stop", "automatic")

    for sector_number in sector_numbers:
        for operation in operations:
            unique_id = f"{device_id}_sector_{sector_number}_{operation}"
            entity_id = registry.async_get_entity_id("button", DOMAIN, unique_id)
            if entity_id is not None:
                registry.async_remove(entity_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    entities: list[ButtonEntity] = []

    # Every sector mode change requires a deliberate second action.
    for fallback, sector in enumerate(data.get("sectors", []), start=1):
        number = sector.get("_agronic_number")
        if not isinstance(number, int):
            number = fallback
        name = _name(
            sector,
            f"Sector {fallback}",
            ("name", "description", "nombre", "sectorName", "sector_name", "label"),
        )
        entities.append(VeggaConfirmSectorModeButton(coordinator, number, name))

    # Program start/stop controls remain available.
    for fallback, program in enumerate(data.get("programs", []), start=1):
        number = _number(program, fallback, ("number", "program", "programNumber", "id"))
        name = _name(program, f"Programa {fallback}", ("name", "description", "nombre", "programName"))
        entities.extend(
            (
                VeggaProgramButton(coordinator, number, name, True),
                VeggaProgramButton(coordinator, number, name, False),
            )
        )

    sector_numbers: list[int] = []
    for fallback, sector in enumerate(data.get("sectors", []), start=1):
        number = sector.get("_agronic_number")
        sector_numbers.append(number if isinstance(number, int) else fallback)

    _remove_legacy_sector_buttons(
        hass,
        str(coordinator.api.device_id),
        sector_numbers,
    )

    async_add_entities(entities)


class VeggaProgramButton(VeggaEntity, ButtonEntity):
    def __init__(self, coordinator, program_number: int, program_name: str, start: bool) -> None:
        super().__init__(coordinator)
        self._number, self._item_name, self._start = program_number, program_name, start
        operation = "start" if start else "stop"
        self._attr_name = f"{'Iniciar' if start else 'Parar'} programa {program_name}"
        self._attr_unique_id = f"{coordinator.api.device_id}_program_{program_number}_{operation}"
        self._attr_icon = "mdi:play" if start else "mdi:stop"

    async def async_press(self) -> None:
        if self._start:
            await self.coordinator.api.start_program(self._number)
        else:
            await self.coordinator.api.stop_program(self._number)
        self.coordinator.record_command(
            f"{'Iniciar' if self._start else 'Parar'} programa {self._item_name}"
        )
        await self.coordinator.async_request_refresh()


class VeggaConfirmSectorModeButton(VeggaSectorEntity, ButtonEntity):
    """Explicitly confirm a previously staged sector mode change."""

    _attr_icon = "mdi:shield-check"

    def __init__(self, coordinator, sector_number: int, sector_name: str) -> None:
        super().__init__(coordinator, sector_number, sector_name)
        self._attr_name = "Confirmar cambio de modo"
        self._attr_unique_id = (
            f"{coordinator.api.device_id}_sector_{sector_number}_confirm_mode"
        )

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.pending_sector_mode(self._sector_number) is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        return {
            "modo_actual": self.coordinator.sector_mode(self._sector_number),
            "cambio_pendiente": self.coordinator.pending_sector_mode(self._sector_number),
        }

    async def async_press(self) -> None:
        option = self.coordinator.pending_sector_mode(self._sector_number)
        if option is None:
            return

        if option == "Marcha manual":
            await self.coordinator.api.start_sector(self._sector_number)
        elif option == "Paro manual":
            await self.coordinator.api.stop_sector(self._sector_number)
        elif option == "Automático":
            await self.coordinator.api.automatic_sector(self._sector_number)
        else:
            raise ValueError(f"Modo de sector no válido: {option}")

        self.coordinator.record_sector_mode(self._sector_number, option)
        self.coordinator.clear_pending_sector_mode(self._sector_number)
        self.coordinator.record_command(
            f"Sector {self._sector_device_name}: cambio confirmado a {option}"
        )
        await self.coordinator.async_request_refresh()
