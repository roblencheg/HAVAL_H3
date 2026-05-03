"""Device tracker for GWM RU."""

from __future__ import annotations

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GwmRuCoordinator
from .entity import GwmRuEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up GWM RU device tracker."""
    coordinator: GwmRuCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GwmRuLocationTracker(coordinator)])


class GwmRuLocationTracker(GwmRuEntity, TrackerEntity):
    """GPS location tracker."""

    _attr_name = "Местоположение"
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: GwmRuCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_location"

    @property
    def latitude(self) -> float | None:
        return (self.coordinator.data.get("location") or {}).get("latitude")

    @property
    def longitude(self) -> float | None:
        return (self.coordinator.data.get("location") or {}).get("longitude")

    @property
    def location_accuracy(self) -> int | None:
        return (self.coordinator.data.get("location") or {}).get("gps_accuracy")
