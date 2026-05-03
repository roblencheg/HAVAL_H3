"""Base entities for GWM RU."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GwmRuCoordinator


class GwmRuEntity(CoordinatorEntity[GwmRuCoordinator]):
    """Base GWM RU entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GwmRuCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data
        vehicle_name = data.get("vehicle_name", "GWM vehicle") if data else "GWM vehicle"
        state = data.get("state", {}) if data else {}
        model_str = state.get("model") or state.get("brand") or "GWM"
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry_id)},
            name=vehicle_name,
            manufacturer="GWM",
            model=str(model_str),
        )
