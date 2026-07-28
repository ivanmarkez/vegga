from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import VeggaCoordinator


class VeggaEntity(CoordinatorEntity[VeggaCoordinator]):
    """Base VEGGA entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VeggaCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def device_info(self):
        return {
            "identifiers": {("vegga", self.coordinator.api.device_id)},
            "name": f"Agrónic {self.coordinator.api.device_id}",
            "manufacturer": "Progrés",
            "model": "Agrónic A-5500",
        }
