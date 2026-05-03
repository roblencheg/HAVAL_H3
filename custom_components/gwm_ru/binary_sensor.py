"""Binary sensors for GWM RU."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GwmRuCoordinator
from .entity import GwmRuEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up GWM RU binary sensors."""
    coordinator: GwmRuCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GwmRuTboxOnlineBinarySensor(coordinator)])


class GwmRuTboxOnlineBinarySensor(GwmRuEntity, BinarySensorEntity):
    """TBOX online binary sensor."""

    _attr_name = "TBOX онлайн"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: GwmRuCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_tbox_online"

    @property
    def is_on(self) -> bool | None:
        value = (self.coordinator.data.get("state") or {}).get("tbox_online")
        return bool(value) if value is not None else None
