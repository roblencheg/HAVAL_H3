"""Diagnostics support for GWM RU."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import ENDPOINT_COMPOUND_TEMPLATE_LIST, ENDPOINT_REMOTE_HISTORY

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
    # Raw GWM STATUS id embeds the vehicle/device identifier. Capability node
    # numeric ids are not required for diagnostics; functionCode is canonical.
    "id",
}


async def _probe_endpoint(
    client: Any,
    endpoint: str,
    vin: str,
    variants: list[dict[str, str]],
) -> dict[str, Any]:
    """Try harmless GET parameter variants and preserve useful diagnostics."""
    errors: list[dict[str, Any]] = []
    for params in variants:
        try:
            payload = await client._request(
                "GET",
                endpoint,
                params=params,
                vin_header=vin,
            )
            return {
                "ok": True,
                "params": params,
                "data": payload.get("data"),
            }
        except Exception as err:
            errors.append({"params": params, "error": str(err)})
    return {"ok": False, "attempts": errors}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    coordinator = hass.data["gwm_ru"][entry.entry_id]

    read_only_probes: list[dict[str, Any]] = []
    for vehicle in coordinator.vehicles:
        vin = vehicle.get("vin")
        if not vin:
            continue
        car = vehicle.get("vehicle") or {}
        ownership = str(car.get("ownership") or 1)
        vehicle_id = car.get("vehicleId")

        history_variants = [
            {"vin": str(vin), "pageNum": "1", "pageSize": "20"},
            {"vin": str(vin)},
        ]
        if vehicle_id is not None:
            history_variants.insert(
                0,
                {
                    "vin": str(vin),
                    "vehicleId": str(vehicle_id),
                    "pageNum": "1",
                    "pageSize": "20",
                },
            )

        compound_variants = [
            {"vin": str(vin), "userRole": ownership},
            {"vin": str(vin)},
        ]

        read_only_probes.append(
            {
                "vin": str(vin),
                "remote_history": await _probe_endpoint(
                    coordinator.client,
                    ENDPOINT_REMOTE_HISTORY,
                    str(vin),
                    history_variants,
                ),
                "compound_templates": await _probe_endpoint(
                    coordinator.client,
                    ENDPOINT_COMPOUND_TEMPLATE_LIST,
                    str(vin),
                    compound_variants,
                ),
            }
        )

    data = {
        "entry": {
            "data": dict(entry.data),
            "options": dict(entry.options),
            "title": entry.title,
            "unique_id": entry.unique_id,
        },
        "coordinator": coordinator.data,
        "read_only_probes": read_only_probes,
    }
    return async_redact_data(data, TO_REDACT)
