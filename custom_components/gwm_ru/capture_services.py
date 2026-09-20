"""Opt-in Home Assistant services for privacy-limited GWM protocol capture."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .protocol_capture import GwmRuCaptureCoordinator

CAPTURE_SERVICES = (
    "protocol_capture_start",
    "protocol_capture_stop",
    "protocol_capture_marker",
    "protocol_capture_refresh",
)


def register_capture_services(hass: HomeAssistant) -> None:
    """Register once for all config entries, including multi-vehicle accounts."""

    def resolve(call: ServiceCall) -> GwmRuCaptureCoordinator:
        entries = hass.data.get(DOMAIN, {})
        entry_id = call.data.get("entry_id")
        if entry_id:
            result = entries.get(entry_id)
        elif len(entries) == 1:
            result = next(iter(entries.values()))
        else:
            raise HomeAssistantError("Укажите entry_id для выбора аккаунта GWM RU")
        if not isinstance(result, GwmRuCaptureCoordinator):
            raise HomeAssistantError("Аккаунт GWM RU не найден")
        return result

    async def handle(call: ServiceCall) -> None:
        coordinator = resolve(call)
        if call.service == "protocol_capture_start":
            coordinator.capture_start()
            await coordinator.async_request_refresh()
        elif call.service == "protocol_capture_stop":
            coordinator.capture_stop()
        elif call.service == "protocol_capture_marker":
            label = call.data.get("label")
            if not isinstance(label, str):
                raise HomeAssistantError("Укажите текстовую метку label")
            await coordinator.capture_marker(label, call.data.get("vin"))
        elif call.service == "protocol_capture_refresh":
            if not coordinator.capture_enabled:
                raise HomeAssistantError("Сначала включите запись протокола")
            await coordinator.async_request_refresh()
        else:
            raise HomeAssistantError("Неизвестная команда записи протокола")

    for name in CAPTURE_SERVICES:
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handle)


def unregister_capture_services(hass: HomeAssistant) -> None:
    """Keep services while another GWM RU entry is still loaded."""
    if hass.data.get(DOMAIN):
        return
    for name in CAPTURE_SERVICES:
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)
