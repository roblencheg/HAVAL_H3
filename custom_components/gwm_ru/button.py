"""Button platform for GWM RU."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import supports_command
from .commands import COMMANDS
from .const import (
    CONF_ENABLE_REMOTE_CONTROLS,
    CONF_SECURITY_PIN,
    DEFAULT_ENABLE_REMOTE_CONTROLS,
    DOMAIN,
)
from .coordinator import GwmRuCoordinator
from .entity import GwmRuEntity, setup_vehicle_entities


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: GwmRuCoordinator = hass.data[DOMAIN][entry.entry_id]
    enable = entry.options.get(CONF_ENABLE_REMOTE_CONTROLS, DEFAULT_ENABLE_REMOTE_CONTROLS)
    has_pin = bool(entry.options.get(CONF_SECURITY_PIN) or entry.data.get(CONF_SECURITY_PIN))

    def entities_for_vehicle(vehicle):
        vin = vehicle["vin"]
        entities: list[ButtonEntity] = [GwmRuRefreshButton(coordinator, vin)]
        if enable and has_pin:
            entities.extend(
                GwmRuCommandButton(coordinator, vin, cmd)
                for cmd in COMMANDS.values()
                if supports_command(vehicle, cmd["key"])
            )
        return entities

    setup_vehicle_entities(coordinator, async_add_entities, entities_for_vehicle)


class GwmRuRefreshButton(GwmRuEntity, ButtonEntity):
    _attr_name = "Обновить датчики"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: GwmRuCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{coordinator.entity_prefix(vin)}_refresh"

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()


class GwmRuCommandButton(GwmRuEntity, ButtonEntity):
    def __init__(self, coordinator: GwmRuCoordinator, vin: str, command: dict) -> None:
        super().__init__(coordinator, vin)
        self._command = command
        self._attr_unique_id = f"{coordinator.entity_prefix(vin)}_cmd_{command['key']}"
        self._attr_name = command["name"]
        self._attr_icon = command["icon"]
        self._attr_entity_registry_enabled_default = True

    async def async_press(self) -> None:
        await self.coordinator.hass.services.async_call(
            DOMAIN,
            self._command["key"],
            {"vin": self.vin},
            blocking=True,
        )
