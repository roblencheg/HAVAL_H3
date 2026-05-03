"""Data coordinator for GWM RU."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import GwmRuApiClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class GwmRuCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinates GWM RU API polling."""

    def __init__(self, hass: HomeAssistant, client: GwmRuApiClient, poll_interval: int, entry_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self.client = client
        self.entry_id = entry_id
        self.enable_remote_controls = False
        self.command_cooldown = 30
        self._last_command_time = 0.0

    async def _async_update_data(self) -> dict[str, Any]:
        return await self.client.async_update()
