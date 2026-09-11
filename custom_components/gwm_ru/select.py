"""Select platform for GWM RU seat-heater levels."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import has_capability
from .const import DOMAIN
from .coordinator import GwmRuCoordinator
from .entity import GwmRuEntity, setup_vehicle_entities


@dataclass(frozen=True, kw_only=True)
class GwmRuSeatSelectDescription(SelectEntityDescription):
    state_key: str
    capability_code: str
    service: str


SEAT_OPTIONS = ["Выкл", "1", "2", "3"]

SEAT_SELECTS = (
    GwmRuSeatSelectDescription(
        key="driver_seat_heater_level",
        name="Обогрев водительского сиденья",
        icon="mdi:car-seat-heater",
        state_key="driver_seat_heater_state",
        capability_code="1-1-10-1-29",
        service="set_driver_seat_heat",
    ),
    GwmRuSeatSelectDescription(
        key="passenger_seat_heater_level",
        name="Обогрев пассажирского сиденья",
        icon="mdi:car-seat-heater",
        state_key="passenger_seat_heater_state",
        capability_code="1-1-10-1-17",
        service="set_passenger_seat_heat",
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
            GwmRuSeatHeaterSelect(coordinator, vehicle["vin"], description)
            for description in SEAT_SELECTS
            if has_capability(vehicle, description.capability_code)
        )

    setup_vehicle_entities(coordinator, async_add_entities, entities_for_vehicle)


class GwmRuSeatHeaterSelect(GwmRuEntity, SelectEntity):
    """Select the seat-heater level reported by the vehicle."""

    entity_description: GwmRuSeatSelectDescription
    _attr_options = SEAT_OPTIONS

    def __init__(
        self,
        coordinator: GwmRuCoordinator,
        vin: str,
        description: GwmRuSeatSelectDescription,
    ) -> None:
        super().__init__(coordinator, vin)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entity_prefix(vin)}_{description.key}"

    @property
    def current_option(self) -> str | None:
        value = ((self.vehicle or {}).get("state") or {}).get(self.entity_description.state_key)
        if value is None:
            return None
        try:
            level = int(value)
        except (TypeError, ValueError):
            return None
        return "Выкл" if level <= 0 else str(min(3, level))

    async def async_select_option(self, option: str) -> None:
        level = 0 if option == "Выкл" else int(option)
        await self.coordinator.hass.services.async_call(
            DOMAIN,
            self.entity_description.service,
            {"vin": self.vin, "level": level},
            blocking=True,
        )
