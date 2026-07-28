from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import VeggaCoordinator


class VeggaEntity(CoordinatorEntity[VeggaCoordinator]):
    """Base entity attached to the main Agrónic controller device."""

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


class VeggaSectorEntity(VeggaEntity):
    """Base entity attached to an individual irrigation-sector device."""

    def __init__(
        self,
        coordinator: VeggaCoordinator,
        sector_number: int,
        sector_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._sector_number = sector_number
        self._sector_device_name = sector_name

    @property
    def device_info(self):
        device_id = self.coordinator.api.device_id
        return {
            "identifiers": {("vegga", f"{device_id}_sector_{self._sector_number}")},
            "name": f"Sector {self._sector_device_name}",
            "manufacturer": "Progrés",
            "model": "Sector de riego Agrónic A-5500",
            "via_device": ("vegga", device_id),
        }
