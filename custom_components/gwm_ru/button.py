"""Button platform for GWM RU."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .commands import COMMANDS
from .const import (
    CONF_ENABLE_REMOTE_CONTROLS,
    CONF_SECURITY_PIN,
    DEFAULT_ENABLE_REMOTE_CONTROLS,
    DOMAIN,
)
from .coordinator import GwmRuCoordinator
from .entity import GwmRuEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up GWM RU button."""
    coordinator: GwmRuCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = [GwmRuRefreshButton(coordinator)]

    enable = entry.options.get(CONF_ENABLE_REMOTE_CONTROLS, DEFAULT_ENABLE_REMOTE_CONTROLS)
    has_pin = bool(
        entry.options.get(CONF_SECURITY_PIN) or entry.data.get(CONF_SECURITY_PIN)
    )
    if enable and has_pin:
        entities.extend(
            GwmRuCommandButton(coordinator, cmd)
            for cmd in COMMANDS.values()
        )

    async_add_entities(entities)


class GwmRuRefreshButton(GwmRuEntity, ButtonEntity):
    """Button to refresh all GWM RU sensors."""

    _attr_name = "Обновить датчики"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: GwmRuCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_refresh"

    async def async_press(self) -> None:
        """Trigger coordinator refresh."""
        await self.coordinator.async_request_refresh()


class GwmRuCommandButton(GwmRuEntity, ButtonEntity):
    """Button to send a remote command to the vehicle."""

    def __init__(self, coordinator: GwmRuCoordinator, command: dict) -> None:
        super().__init__(coordinator)
        self._command = command
        self._attr_unique_id = f"{coordinator.entry_id}_cmd_{command['key']}"
        self._attr_name = command["name"]
        self._attr_icon = command["icon"]

    async def async_press(self) -> None:
        """Execute the command via service."""
        await self.coordinator.hass.services.async_call(
            DOMAIN, self._command["key"], {}, blocking=True
        )
