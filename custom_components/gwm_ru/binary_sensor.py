"""Binary sensors for GWM RU."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import supports_state
from .const import DOMAIN
from .coordinator import GwmRuCoordinator
from .entity import GwmRuEntity, setup_vehicle_entities


@dataclass(frozen=True, kw_only=True)
class GwmRuBinarySensorDescription(BinarySensorEntityDescription):
    state_key: str


BINARY_SENSORS: tuple[GwmRuBinarySensorDescription, ...] = (
    GwmRuBinarySensorDescription(key="tbox_online", state_key="tbox_online", name="TBOX онлайн", device_class=BinarySensorDeviceClass.CONNECTIVITY),
    GwmRuBinarySensorDescription(key="engine_on", state_key="engine_on", name="Двигатель запущен", icon="mdi:engine"),
    # BinarySensorDeviceClass.LOCK uses ON = unlocked/open and OFF = locked/closed.
    # Keep the legacy key/unique_id, but expose the semantic "unlocked" value.
    GwmRuBinarySensorDescription(key="locked", state_key="unlocked", name="Автомобиль", device_class=BinarySensorDeviceClass.LOCK, icon="mdi:car-door-lock"),
    GwmRuBinarySensorDescription(key="trunk_open", state_key="trunk_open", name="Багажник открыт", device_class=BinarySensorDeviceClass.DOOR),
    GwmRuBinarySensorDescription(key="door_fl_open", state_key="door_fl_open", name="Передняя левая дверь открыта", device_class=BinarySensorDeviceClass.DOOR),
    GwmRuBinarySensorDescription(key="door_fr_open", state_key="door_fr_open", name="Передняя правая дверь открыта", device_class=BinarySensorDeviceClass.DOOR),
    GwmRuBinarySensorDescription(key="door_rl_open", state_key="door_rl_open", name="Задняя левая дверь открыта", device_class=BinarySensorDeviceClass.DOOR),
    GwmRuBinarySensorDescription(key="door_rr_open", state_key="door_rr_open", name="Задняя правая дверь открыта", device_class=BinarySensorDeviceClass.DOOR),
    GwmRuBinarySensorDescription(key="climate_on", state_key="climate_on", name="Климат включён", icon="mdi:air-conditioner"),
    GwmRuBinarySensorDescription(key="window_fl_open", state_key="window_fl_open", name="Переднее левое окно открыто", device_class=BinarySensorDeviceClass.WINDOW),
    GwmRuBinarySensorDescription(key="window_fr_open", state_key="window_fr_open", name="Переднее правое окно открыто", device_class=BinarySensorDeviceClass.WINDOW),
    GwmRuBinarySensorDescription(key="window_rl_open", state_key="window_rl_open", name="Заднее левое окно открыто", device_class=BinarySensorDeviceClass.WINDOW),
    GwmRuBinarySensorDescription(key="window_rr_open", state_key="window_rr_open", name="Заднее правое окно открыто", device_class=BinarySensorDeviceClass.WINDOW),
    GwmRuBinarySensorDescription(key="rear_defroster_on", state_key="rear_defroster_on", name="Обогрев заднего стекла", icon="mdi:car-defrost-rear"),
    GwmRuBinarySensorDescription(key="steering_wheel_heater_on", state_key="steering_wheel_heater_on", name="Обогрев руля", icon="mdi:steering"),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: GwmRuCoordinator = hass.data[DOMAIN][entry.entry_id]

    def entities_for_vehicle(vehicle):
        return (
            GwmRuBinarySensor(coordinator, vehicle["vin"], description)
            for description in BINARY_SENSORS
            if supports_state(vehicle, description.state_key)
        )

    setup_vehicle_entities(coordinator, async_add_entities, entities_for_vehicle)


class GwmRuBinarySensor(GwmRuEntity, BinarySensorEntity):
    entity_description: GwmRuBinarySensorDescription

    def __init__(self, coordinator: GwmRuCoordinator, vin: str, description: GwmRuBinarySensorDescription) -> None:
        super().__init__(coordinator, vin)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entity_prefix(vin)}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        value = ((self.vehicle or {}).get("state") or {}).get(self.entity_description.state_key)
        return bool(value) if value is not None else None
