"""Diagnostics support for GWM RU."""

from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

TO_REDACT = {
    "password",
    "security_pin",
    "accessToken",
    "token",
    "vin",
    "showedVin",
    "imsi",
    "simIccid",
    "engineNo",
    "device_id",
    "deviceId",
    "phone",
    "display_vin",
    "latitude",
    "longitude",
    "id",
    "templateId",
    "shareId",
    "vehicleId",
    "unique_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict:
    """Return privacy-safe diagnostics without additional research API calls."""
    coordinator = hass.data["gwm_ru"][entry.entry_id]
    data = {
        "entry": {
            "data": dict(entry.data),
            "options": dict(entry.options),
            "title": entry.title,
            "unique_id": entry.unique_id,
        },
        "coordinator": coordinator.data,
    }
    return async_redact_data(data, TO_REDACT)
