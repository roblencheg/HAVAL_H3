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
    "refreshToken",
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
    "userId",
    "beanId",
    "templateId",
    "compoundCommandTemplateId",
    "shareId",
    "vehicleId",
    "unique_id",
    "seqNo",
    "hwCommandId",
}


def _safe_path(path: str, vin: str) -> str:
    """Redact identifiers embedded inside endpoint paths."""
    return path.replace(vin, "**REDACTED**")


async def _probe(
    client: Any,
    method: str,
    path: str,
    vin: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one explicitly read/query-only research request."""
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
            "path": _safe_path(path, vin),
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
            "path": _safe_path(path, vin),
            "params": params,
            "body": body,
            "error": str(err),
        }


async def _research_vehicle(client: Any, vin: str, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    """Probe known GWM cloud discovery/status endpoints without sending controls."""
    vehicle_id = vehicle.get("vehicleId")
    ownership = str(vehicle.get("ownership") or 1)
    model_code = vehicle.get("modelCode")
    vtype = vehicle.get("vtype")
    probes: list[dict[str, Any]] = []

    async def get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        result = await _probe(client, "GET", path, vin, params=params)
        probes.append(result)
        return result

    async def post_query(path: str, body: dict[str, Any]) -> dict[str, Any]:
        result = await _probe(client, "POST", path, vin, body=body)
        probes.append(result)
        return result

    # Russian v1 discovery/status reads.
    await get("/app-api/api/v1.0/vehicle/vehicleBasicsInfo", {"vin": vin})
    await get("/app-api/api/v1.0/vehicle/vehicleBasicsInfo", {"vin": vin, "flag": "true"})
    await get("/app-api/api/v1.0/vehicle/findVehicleCapabilityItem", {"vin": vin, "userRole": ownership})
    await get("/app-api/api/v1.0/vehicle/getLastStatus", {"vin": vin, "seqNo": "", "modelId": ""})

    # Remote-control history is a read query, but the backend requires POST.
    for history_type in ("1", "2", "3"):
        body: dict[str, Any] = {"vin": vin, "type": history_type, "pageNum": 1, "pageSize": 50}
        if vehicle_id is not None:
            body["vehicleId"] = vehicle_id
        await post_query("/app-api/api/v1.0/vehicle/getWeyVrcHistory", body)

    # Compound/one-button comfort templates. The RU backend requires GET here.
    template_list = await get(
        "/app-api/api/v1.0/vehicle/getCompoundCommandTemplateList",
        {"vin": vin, "userRole": ownership},
    )
    if not template_list.get("ok"):
        template_list = await get(
            "/app-api/api/v1.0/vehicle/getCompoundCommandTemplateList",
            {"vin": vin},
        )

    template_data = template_list.get("data")
    candidates: list[dict[str, Any]] = []
    if isinstance(template_data, list):
        candidates = [x for x in template_data if isinstance(x, dict)]
    elif isinstance(template_data, dict):
        for value in template_data.values():
            if isinstance(value, list):
                candidates.extend(x for x in value if isinstance(x, dict))

    # Query each discovered comfort template using all observed identifier names.
    for template in candidates[:10]:
        template_id = template.get("id") or template.get("templateId") or template.get("compoundCommandTemplateId")
        if template_id is None:
            continue
        for params in (
            {"id": str(template_id), "vin": vin},
            {"templateId": str(template_id), "vin": vin},
            {"compoundCommandTemplateId": str(template_id), "vin": vin},
        ):
            detail = await get("/app-api/api/v1.0/vehicle/getCompoundCommandTemplateInfo", params)
            if detail.get("ok") and detail.get("data") is not None:
                break

    # Newer v3 routes. On RU they currently respond SUCCESS/null, which is itself useful.
    await get("/app-api/api/v3.0/vehicle/getLastStatus", {"vin": vin})
    await get("/app-api/api/v3.0/vehicle/getLastStatus", {"vin": vin, "flag": "true"})
    await get("/app-api/api/v3.0/vehicle/remote-ctrl/config", {"vin": vin})
    await get("/app-api/api/v3.0/vehicle/remote-ctrl/result", {"vin": vin})
    await get(f"/app-api/api/v3.0/vehicle/remote-ctrl/subscribe/{vin}")
    await get("/app-api/api/v3.0/vehicle/one-touch/mode", {"vin": vin})
    await get("/app-api/api/v3.0/vehicle/switch/status", {"vin": vin})
    await get("/app-api/api/v3.0/vehicle/charge/setting", {"vin": vin})

    # Query/status POST routes, still no control payloads.
    base_body: dict[str, Any] = {"vin": vin}
    if vehicle_id is not None:
        base_body["vehicleId"] = vehicle_id
    await post_query("/app-api/api/v3.0/vehicle/remote-ctrl/config/query", dict(base_body))
    await post_query("/app-api/api/v3.0/vehicle/switch/status", dict(base_body))

    hinted = dict(base_body)
    if model_code:
        hinted["modelCode"] = model_code
    if vtype:
        hinted["vtype"] = vtype
    if hinted != base_body:
        await post_query("/app-api/api/v3.0/vehicle/remote-ctrl/config/query", hinted)
        await post_query("/app-api/api/v3.0/vehicle/switch/status", hinted)

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
