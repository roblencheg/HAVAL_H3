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

from .const import DOMAIN
from .coordinator import GwmRuCoordinator
from .entity import GwmRuEntity


@dataclass(frozen=True, kw_only=True)
class GwmRuBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor description."""

    state_key: str


BINARY_SENSORS: tuple[GwmRuBinarySensorDescription, ...] = (
    GwmRuBinarySensorDescription(
        key="tbox_online",
        state_key="tbox_online",
        name="TBOX онлайн",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    GwmRuBinarySensorDescription(
        key="engine_on",
        state_key="engine_on",
        name="Двигатель запущен",
        icon="mdi:engine",
    ),
    GwmRuBinarySensorDescription(
        key="locked",
        state_key="locked",
        name="Автомобиль закрыт",
        device_class=BinarySensorDeviceClass.LOCK,
        icon="mdi:car-door-lock",
    ),
    GwmRuBinarySensorDescription(
        key="trunk_open",
        state_key="trunk_open",
        name="Багажник открыт",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    GwmRuBinarySensorDescription(
        key="door_fl_open",
        state_key="door_fl_open",
        name="Передняя левая дверь открыта",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    GwmRuBinarySensorDescription(
        key="door_fr_open",
        state_key="door_fr_open",
        name="Передняя правая дверь открыта",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    GwmRuBinarySensorDescription(
        key="door_rl_open",
        state_key="door_rl_open",
        name="Задняя левая дверь открыта",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    GwmRuBinarySensorDescription(
        key="door_rr_open",
        state_key="door_rr_open",
        name="Задняя правая дверь открыта",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    GwmRuBinarySensorDescription(
        key="climate_on",
        state_key="climate_on",
        name="Климат включён",
        icon="mdi:air-conditioner",
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up GWM RU binary sensors."""
    coordinator: GwmRuCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        GwmRuBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
    )


class GwmRuBinarySensor(GwmRuEntity, BinarySensorEntity):
    """GWM RU binary sensor."""

    entity_description: GwmRuBinarySensorDescription

    def __init__(self, coordinator: GwmRuCoordinator, description: GwmRuBinarySensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        value = (self.coordinator.data.get("state") or {}).get(
            self.entity_description.state_key
        )
        return bool(value) if value is not None else None
