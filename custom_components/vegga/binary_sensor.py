from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import VeggaEntity, VeggaSectorEntity
from .history import analyse_sector


def _sector_number(item: dict[str, Any], fallback: int) -> int:
    value = item.get("_agronic_number")
    if isinstance(value, int) and value >= 1:
        return value
    return fallback


def _sector_name(item: dict[str, Any], fallback: int) -> str:
    for key in ("name", "description", "nombre", "sectorName", "sector_name", "label"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return f"Sector {fallback}"


def _is_active(item: dict[str, Any]) -> bool:
    for key in ("active", "isActive", "running", "isRunning", "enabled", "irrigating"):
        value = item.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "on", "active", "running", "irrigating"}
    status = item.get("status") or item.get("state")
    return isinstance(status, str) and status.strip().lower() in {"active", "running", "on", "irrigating"}




def _live_sector_numbers(payload: Any) -> set[int]:
    found: set[int] = set()
    def walk(value: Any, path: str = "root") -> None:
        if isinstance(value, list):
            for child in value:
                walk(child, path)
            return
        if not isinstance(value, dict):
            return
        normalized = {str(k).casefold().replace("-", "").replace("_", ""): v for k, v in value.items()}
        if _is_active(value) and "sector" in path.casefold():
            for key in ("sector", "sectornumber", "sectorid", "number", "id"):
                if key in normalized:
                    try:
                        found.add(int(normalized[key]))
                    except (TypeError, ValueError):
                        pass
                    break
        for key, child in value.items():
            walk(child, f"{path}.{key}")
    walk(payload)
    return found

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [VeggaCloudConnectionBinarySensor(coordinator)]

    for fallback, sector in enumerate((coordinator.data or {}).get("sectors", []), start=1):
        number = _sector_number(sector, fallback)
        name = _sector_name(sector, fallback)
        entities.extend([
            VeggaSectorBinarySensor(coordinator, number, name),
            VeggaSectorConsumptionAnomalyBinarySensor(coordinator, number, name),
        ])

    async_add_entities(entities)


class VeggaCloudConnectionBinarySensor(VeggaEntity, BinarySensorEntity):
    _attr_name = "Conexión VEGGA"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.api.device_id}_cloud_connection"

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


class VeggaSectorBinarySensor(VeggaSectorEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, coordinator, sector_number: int, sector_name: str) -> None:
        super().__init__(coordinator, sector_number, sector_name)
        self._number = sector_number
        self._attr_name = "Riego activo"
        self._attr_unique_id = f"{coordinator.api.device_id}_sector_{sector_number}_state"

    def _sector(self) -> dict[str, Any] | None:
        for fallback, sector in enumerate((self.coordinator.data or {}).get("sectors", []), start=1):
            if _sector_number(sector, fallback) == self._number:
                return sector
        return None

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data or {}
        live_numbers = _live_sector_numbers(data.get("unit_status"))
        if self._number in live_numbers or (self._number - 1) in live_numbers:
            return True
        sector = self._sector()
        return _is_active(sector) if sector else False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        sector = self._sector()
        return {"sector_number": self._number, "vegga_data": sector or {}}


class VeggaSectorConsumptionAnomalyBinarySensor(VeggaSectorEntity, BinarySensorEntity):
    """Flags a sector whose latest volume differs materially from its baseline."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:water-alert"

    def __init__(self, coordinator, sector_number: int, sector_name: str) -> None:
        super().__init__(coordinator, sector_number, sector_name)
        self._number = sector_number
        self._sector_name = sector_name
        self._attr_name = "Consumo anómalo"
        self._attr_unique_id = f"{coordinator.api.device_id}_sector_{sector_number}_consumption_anomaly"

    def _analysis(self):
        return analyse_sector((self.coordinator.data or {}).get("history", []), self._number, self._sector_name)

    @property
    def is_on(self) -> bool:
        return self._analysis().anomalous

    @property
    def available(self) -> bool:
        return super().available and self._analysis().level != "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        analysis = self._analysis()
        return {
            "sector_number": analysis.sector_number,
            "sector_name": analysis.sector_name,
            "level": analysis.level,
            "deviation_percent": analysis.deviation_percent,
            "last_volume_m3": analysis.last_volume_m3,
            "baseline_volume_m3": analysis.baseline_volume_m3,
            "sample_count": analysis.sample_count,
            "possible_cause": (
                "Posible fuga o caudal superior al habitual"
                if analysis.deviation_percent is not None and analysis.deviation_percent > 0
                else "Posible falta de presión, obstrucción o válvula parcialmente abierta"
                if analysis.deviation_percent is not None
                else "Aprendiendo el consumo habitual del sector"
            ),
        }
