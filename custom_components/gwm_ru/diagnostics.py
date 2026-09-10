"""Diagnostics support for GWM RU."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    ENDPOINT_COMPOUND_TEMPLATE_INFO,
    ENDPOINT_COMPOUND_TEMPLATE_LIST,
    ENDPOINT_REMOTE_HISTORY,
)

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
}


async def _probe_requests(
    client: Any,
    endpoint: str,
    vin: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Try harmless request variants and preserve useful diagnostics."""
    errors: list[dict[str, Any]] = []
    for attempt in attempts:
        method = str(attempt.get("method") or "GET").upper()
        params = attempt.get("params") or {}
        body = attempt.get("body")
        try:
            payload = await client._request(
                method,
                endpoint,
                params=params,
                body=body,
                vin_header=vin,
            )
            result: dict[str, Any] = {"ok": True, "method": method, "data": payload.get("data")}
            if params:
                result["params"] = params
            if body is not None:
                result["body"] = body
            return result
        except Exception as err:
            item: dict[str, Any] = {"method": method, "error": str(err)}
            if params:
                item["params"] = params
            if body is not None:
                item["body"] = body
            errors.append(item)
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

        history_bodies: list[dict[str, Any]] = [
            {"vin": str(vin), "pageNum": 1, "pageSize": 20},
            {"vin": str(vin), "pageNo": 1, "pageSize": 20},
            {"vin": str(vin), "current": 1, "size": 20},
            {"vin": str(vin), "userRole": int(ownership), "pageNum": 1, "pageSize": 20},
        ]
        if vehicle_id is not None:
            history_bodies.insert(
                0,
                {
                    "vin": str(vin),
                    "vehicleId": vehicle_id,
                    "pageNum": 1,
                    "pageSize": 20,
                },
            )
        history_attempts = [{"method": "POST", "body": body} for body in history_bodies]

        compound_attempts = [
            {"method": "GET", "params": {"vin": str(vin), "userRole": ownership}},
            {"method": "GET", "params": {"vin": str(vin)}},
        ]
        compound = await _probe_requests(
            coordinator.client,
            ENDPOINT_COMPOUND_TEMPLATE_LIST,
            str(vin),
            compound_attempts,
        )

        template_details: list[dict[str, Any]] = []
        if compound.get("ok") and isinstance(compound.get("data"), dict):
            templates = compound["data"].get("list") or []
            for template in templates[:5]:
                if not isinstance(template, dict) or template.get("id") is None:
                    continue
                template_id = template["id"]
                detail = await _probe_requests(
                    coordinator.client,
                    ENDPOINT_COMPOUND_TEMPLATE_INFO,
                    str(vin),
                    [
                        {"method": "GET", "params": {"id": str(template_id), "vin": str(vin)}},
                        {"method": "GET", "params": {"templateId": str(template_id), "vin": str(vin)}},
                        {"method": "GET", "params": {"compoundCommandTemplateId": str(template_id), "vin": str(vin)}},
                    ],
                )
                template_details.append({"template_name": template.get("templateName"), "detail": detail})

        read_only_probes.append(
            {
                "vin": str(vin),
                "remote_history": await _probe_requests(
                    coordinator.client,
                    ENDPOINT_REMOTE_HISTORY,
                    str(vin),
                    history_attempts,
                ),
                "compound_templates": compound,
                "compound_template_details": template_details,
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
