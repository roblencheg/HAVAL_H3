"""Switch platform for GWM RU remote controls."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import has_capability
from .const import DOMAIN
from .coordinator import GwmRuCoordinator
from .entity import GwmRuEntity, setup_vehicle_entities


@dataclass(frozen=True, kw_only=True)
class GwmRuSwitchDescription(SwitchEntityDescription):
    state_key: str
    capability_code: str
    service_on: str
    service_off: str


SWITCHES = (
    GwmRuSwitchDescription(
        key="steering_wheel_heater",
        name="Обогрев руля",
        icon="mdi:steering",
        state_key="steering_wheel_heater_on",
        capability_code="1-1-21",
        service_on="steering_wheel_heat_on",
        service_off="steering_wheel_heat_off",
    ),
    GwmRuSwitchDescription(
        key="rear_defroster",
        name="Обогрев заднего стекла",
        icon="mdi:car-defrost-rear",
        state_key="rear_defroster_on",
        capability_code="1-1-5",
        service_on="rear_defrost_on",
        service_off="rear_defrost_off",
    ),
    GwmRuSwitchDescription(
        key="windshield_heater",
        name="Обогрев лобового стекла",
        icon="mdi:car-defrost-front",
        state_key="windshield_heater_on",
        capability_code="1-1-22",
        service_on="windshield_heat_on",
        service_off="windshield_heat_off",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GwmRuCoordinator = hass.data[DOMAIN][entry.entry_id]

    def entities_for_vehicle(vehicle):
        return (
            GwmRuRemoteSwitch(coordinator, vehicle["vin"], description)
            for description in SWITCHES
            if has_capability(vehicle, description.capability_code)
        )

    setup_vehicle_entities(coordinator, async_add_entities, entities_for_vehicle)


class GwmRuRemoteSwitch(GwmRuEntity, SwitchEntity):
    """A capability-driven GWM remote control switch."""

    entity_description: GwmRuSwitchDescription

    def __init__(
        self,
        coordinator: GwmRuCoordinator,
        vin: str,
        description: GwmRuSwitchDescription,
    ) -> None:
        super().__init__(coordinator, vin)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entity_prefix(vin)}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        value = ((self.vehicle or {}).get("state") or {}).get(self.entity_description.state_key)
        return value if isinstance(value, bool) else None

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.hass.services.async_call(
            DOMAIN,
            self.entity_description.service_on,
            {"vin": self.vin},
            blocking=True,
        )

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.hass.services.async_call(
            DOMAIN,
            self.entity_description.service_off,
            {"vin": self.vin},
            blocking=True,
        )
