"""Sensors for GWM RU."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ITEM_MAP, EXTRA_SENSORS
from .coordinator import GwmRuCoordinator
from .entity import GwmRuEntity


@dataclass(frozen=True, kw_only=True)
class GwmRuSensorDescription(SensorEntityDescription):
    """Sensor description."""

    state_key: str


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up GWM RU sensors."""
    coordinator: GwmRuCoordinator = hass.data[DOMAIN][entry.entry_id]
    descriptions: list[GwmRuSensorDescription] = []

    for defn in list(ITEM_MAP.values()) + list(EXTRA_SENSORS.values()):
        descriptions.append(
            GwmRuSensorDescription(
                key=defn.key,
                state_key=defn.key,
                name=defn.name,
                native_unit_of_measurement=defn.unit,
                icon=defn.icon,
                device_class=defn.device_class,
            )
        )

    async_add_entities(GwmRuSensor(coordinator, description) for description in descriptions)


class GwmRuSensor(GwmRuEntity, SensorEntity):
    """A GWM RU sensor."""

    entity_description: GwmRuSensorDescription

    def __init__(self, coordinator: GwmRuCoordinator, description: GwmRuSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        return (self.coordinator.data.get("state") or {}).get(self.entity_description.state_key)
