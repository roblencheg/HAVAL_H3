"""Diagnostics support for GWM RU research branch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

TO_REDACT = {
    "password",
    "security_pin",
    "securityPassword",
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
    "compoundCommandTemplateId",
    "shareId",
    "vehicleId",
    "unique_id",
    "seqNo",
    "hwCommandId",
}


async def _probe(
    client: Any,
    method: str,
    path: str,
    vin: str,
    *,
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one explicitly read-only research request."""
    try:
        payload = await client._request(
            method,
            path,
            params=params,
            body=body,
            vin_header=vin,
        )
        return {
            "ok": True,
            "method": method,
            "path": path,
            "params": params,
            "body": body,
            "code": payload.get("code"),
            "description": payload.get("description") or payload.get("message"),
            "data": payload.get("data"),
        }
    except Exception as err:
        return {
            "ok": False,
            "method": method,
            "path": path,
            "params": params,
            "body": body,
            "error": str(err),
        }


async def _research_vehicle(client: Any, vin: str, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    """Probe known GWM cloud discovery/status endpoints without sending commands."""
    vehicle_id = vehicle.get("vehicleId")
    ownership = str(vehicle.get("ownership") or 1)
    probes: list[dict[str, Any]] = []

    async def get(path: str, params: dict[str, str] | None = None) -> None:
        probes.append(await _probe(client, "GET", path, vin, params=params))

    async def post_query(path: str, body: dict[str, Any]) -> None:
        # Only endpoints known from public clients as query/status reads are POSTed.
        probes.append(await _probe(client, "POST", path, vin, body=body))

    # Existing Russian API discovery reads.
    await get("/app-api/api/v1.0/vehicle/vehicleBasicsInfo", {"vin": vin})
    await get("/app-api/api/v1.0/vehicle/findVehicleCapabilityItem", {"vin": vin, "userRole": ownership})
    await get("/app-api/api/v1.0/vehicle/getLastStatus", {"vin": vin, "seqNo": "", "modelId": ""})
    if vehicle_id is not None:
        await get("/app-api/api/v1.0/vehicle/getWeyVrcHistory", {"vin": vin, "vehicleId": str(vehicle_id)})

    # Newer v3 endpoints observed in current GWM clients. GET requests are discovery-only.
    await get("/app-api/api/v3.0/vehicle/getLastStatus", {"vin": vin})
    await get("/app-api/api/v3.0/vehicle/remote-ctrl/config", {"vin": vin})
    await get("/app-api/api/v3.0/vehicle/remote-ctrl/result", {"vin": vin})
    await get(f"/app-api/api/v3.0/vehicle/remote-ctrl/subscribe/{vin}")
    await get("/app-api/api/v3.0/vehicle/one-touch/mode", {"vin": vin})
    await get("/app-api/api/v3.0/vehicle/switch/status", {"vin": vin})
    await get("/app-api/api/v3.0/vehicle/charge/setting", {"vin": vin})

    # Public GWM implementations use these two as read/query POST endpoints.
    await post_query("/app-api/api/v3.0/vehicle/remote-ctrl/config/query", {"vin": vin})
    await post_query("/app-api/api/v3.0/vehicle/switch/status", {"vin": vin})

    # Probe a few likely discovery variants, still without any control command fields.
    if vehicle_id is not None:
        query_body = {"vin": vin, "vehicleId": vehicle_id}
        await post_query("/app-api/api/v3.0/vehicle/remote-ctrl/config/query", query_body)
        await post_query("/app-api/api/v3.0/vehicle/switch/status", query_body)

    return probes


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics plus read-only cloud research probes."""
    coordinator = hass.data["gwm_ru"][entry.entry_id]
    cloud_research: list[dict[str, Any]] = []

    for item in coordinator.vehicles:
        vin = item.get("vin")
        if not vin:
            continue
        vehicle = item.get("vehicle") or {}
        cloud_research.append(
            {
                "vin": str(vin),
                "probes": await _research_vehicle(coordinator.client, str(vin), vehicle),
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
        "cloud_research": cloud_research,
    }
    return async_redact_data(data, TO_REDACT)
