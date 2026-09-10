"""Sensors for GWM RU."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import supports_state
from .const import DOMAIN, ITEM_MAP, EXTRA_SENSORS
from .coordinator import GwmRuCoordinator
from .entity import GwmRuEntity, setup_vehicle_entities


@dataclass(frozen=True, kw_only=True)
class GwmRuSensorDescription(SensorEntityDescription):
    state_key: str


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: GwmRuCoordinator = hass.data[DOMAIN][entry.entry_id]
    descriptions = tuple(
        GwmRuSensorDescription(
            key=defn.key,
            state_key=defn.key,
            name=defn.name,
            native_unit_of_measurement=defn.unit,
            icon=defn.icon,
            device_class=defn.device_class,
        )
        for defn in list(ITEM_MAP.values()) + list(EXTRA_SENSORS.values())
    )

    def entities_for_vehicle(vehicle):
        return (
            GwmRuSensor(coordinator, vehicle["vin"], description)
            for description in descriptions
            if supports_state(vehicle, description.state_key)
        )

    setup_vehicle_entities(coordinator, async_add_entities, entities_for_vehicle)


class GwmRuSensor(GwmRuEntity, SensorEntity):
    entity_description: GwmRuSensorDescription

    def __init__(self, coordinator: GwmRuCoordinator, vin: str, description: GwmRuSensorDescription) -> None:
        super().__init__(coordinator, vin)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entity_prefix(vin)}_{description.key}"

    @property
    def native_value(self) -> Any:
        return ((self.vehicle or {}).get("state") or {}).get(self.entity_description.state_key)
