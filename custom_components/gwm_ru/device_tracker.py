"""Device tracker for GWM RU."""

from __future__ import annotations

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import has_capability
from .const import DOMAIN
from .coordinator import GwmRuCoordinator
from .entity import GwmRuEntity, setup_vehicle_entities


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: GwmRuCoordinator = hass.data[DOMAIN][entry.entry_id]

    def entities_for_vehicle(vehicle):
        if not has_capability(vehicle, "1-2-17"):
            return ()
        return (GwmRuLocationTracker(coordinator, vehicle["vin"]),)

    setup_vehicle_entities(coordinator, async_add_entities, entities_for_vehicle)


class GwmRuLocationTracker(GwmRuEntity, TrackerEntity):
    _attr_name = "Местоположение"
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: GwmRuCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{coordinator.entity_prefix(vin)}_location"

    @property
    def latitude(self) -> float | None:
        return ((self.vehicle or {}).get("location") or {}).get("latitude")

    @property
    def longitude(self) -> float | None:
        return ((self.vehicle or {}).get("location") or {}).get("longitude")

    @property
    def location_accuracy(self) -> int | None:
        return ((self.vehicle or {}).get("location") or {}).get("gps_accuracy")
