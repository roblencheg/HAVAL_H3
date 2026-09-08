"""Base entities for GWM RU."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GwmRuCoordinator


class GwmRuEntity(CoordinatorEntity[GwmRuCoordinator]):
    """Base GWM RU entity bound to one vehicle."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GwmRuCoordinator, vin: str) -> None:
        super().__init__(coordinator)
        self.vin = vin

    @property
    def vehicle(self) -> dict | None:
        return self.coordinator.vehicle(self.vin)

    @property
    def available(self) -> bool:
        return super().available and self.vehicle is not None

    @property
    def device_info(self) -> DeviceInfo:
        vehicle = self.vehicle or {}
        state = vehicle.get("state") or {}
        model_str = state.get("model") or state.get("brand") or "GWM"
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entity_prefix(self.vin))},
            name=vehicle.get("vehicle_name") or "GWM vehicle",
            manufacturer="GWM",
            model=str(model_str),
            serial_number=vehicle.get("display_vin") or None,
        )


def setup_vehicle_entities(
    coordinator: GwmRuCoordinator,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[dict], Iterable[GwmRuEntity]],
) -> None:
    """Add entities for current and newly discovered vehicles."""
    known_vins: set[str] = set()

    def add_new_vehicle_entities() -> None:
        entities: list[GwmRuEntity] = []
        for vehicle in coordinator.vehicles:
            vin = vehicle.get("vin")
            if not vin or vin in known_vins:
                continue
            known_vins.add(vin)
            entities.extend(factory(vehicle))
        if entities:
            async_add_entities(entities)

    add_new_vehicle_entities()
    coordinator.async_add_listener(add_new_vehicle_entities)
