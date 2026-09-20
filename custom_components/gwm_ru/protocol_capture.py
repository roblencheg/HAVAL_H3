"""Opt-in per-vehicle GWM telemetry capture; never sends vehicle commands.

Inspired by IndeecDen/ha-gwm-jolion (MIT).
Copyright (c) 2026 IndeecDen. Copyright (c) 2026 roblencheg.
The candidate field names are research references from moryoav/ha-gwm-ev
and chaosl1996/gwm_cn_ha; their meanings are not validated on RU H3.
Only allowlisted numeric/status fields are written; no raw cloud payloads.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import ENDPOINT_LAST_STATUS, ENDPOINT_VEHICLE_BASICS_INFO
from .coordinator import GwmRuCoordinator

MAX_RECORDS = 500
MAX_MARKER_LENGTH = 80
STATE_KEYS = frozenset({"engine_state", "engine_on", "engine_state_source", "climate_state", "lock_state", "tbox_status", "tbox_online"})
BASICS_KEYS = frozenset({"powerGear", "quickSettings"})
STATUS_KEYS = frozenset({"acquisitionTime", "updateTime", "serviceStatus", "command"})
STATE_SOURCES = frozenset({"remote_command_result", "remote_start_timeout", "telemetry"})
# Exact names from other regional GWM integrations: candidates, NOT verified H3 signals.
POWER_FIELD_NAMES = frozenset({"power", "ignitionstatus", "enginests", "drivingstatus", "hutswitchon", "gpsswitchon", "hcupowertrainsts", "tboxstatus"})
POWER_NODES = ("root", "vehicleStatusInfo", "statusInfo")


def _safe_numeric(value: Any) -> int | float | bool | str | None:
    """Keep bounded numeric telemetry only, never identifiers or arbitrary text."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if not isinstance(value, str) or len(value) > 14 or not value:
        return None
    if value.lstrip("-").replace(".", "", 1).isdigit():
        return value
    return None


def _diff(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"key": key, "previous": before.get(key), "value": after.get(key)}
        for key in sorted(before.keys() | after.keys())
        if before.get(key) != after.get(key)
    ]


def _power_fields(data: Any) -> dict[str, Any]:
    """Return ONLY named non-identifying candidates, case-insensitively.

    A missing field means it was absent, not that it was OFF. No guessed enums.
    """
    if not isinstance(data, dict):
        return {}
    nodes: list[tuple[str, dict[str, Any]]] = [("root", data)]
    for key, value in data.items():
        if isinstance(key, str) and key.casefold() in {"vehiclestatusinfo", "statusinfo"} and isinstance(value, dict):
            nodes.append(("vehicleStatusInfo" if key.casefold() == "vehiclestatusinfo" else "statusInfo", value))
    fields: dict[str, Any] = {}
    for prefix, node in nodes:
        for key, value in node.items():
            if not isinstance(key, str) or key.casefold() not in POWER_FIELD_NAMES:
                continue
            safe_value = _safe_numeric(value)
            if safe_value is not None:
                fields[f"{prefix}.{key.casefold()}"] = safe_value
    return fields


def _freshness(previous: dict[str, Any] | None, current: dict[str, Any]) -> str:
    """Cloud acquisition timestamp, not HTTP success, establishes a new sample."""
    if previous is None:
        return "baseline"
    earlier = previous["status_meta"].get("acquisitionTime")
    latest = current["status_meta"].get("acquisitionTime")
    if isinstance(earlier, (str, int)) and isinstance(latest, (str, int)):
        try:
            return "fresh" if int(latest) > int(earlier) else "cached_or_out_of_order"
        except ValueError:
            pass
    return "unknown"


def _append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        handle.write("\n")


def _read_records(path: Path) -> dict[str, Any]:
    """Export the newest capture session with its own first baseline."""
    baseline = None
    recent: deque[dict[str, Any]] = deque(maxlen=MAX_RECORDS)
    count = 0
    session_count = 0
    if not path.is_file():
        return {"records": [], "total": 0, "truncated": False}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(record, dict) or record.get("schema") not in {1, 2}:
                continue
            count += 1
            if record.get("type") == "refresh" and record.get("baseline"):
                baseline = record
                recent.clear()
                session_count = 1
            elif baseline is not None:
                recent.append(record)
                session_count += 1
    records = ([baseline] if baseline is not None else []) + list(recent)
    return {"records": records, "total": count, "session_total": session_count, "truncated": session_count > len(records)}


class GwmRuCaptureCoordinator(GwmRuCoordinator):
    """Existing coordinator plus explicitly enabled diagnostic capture."""

    def __init__(self, hass: HomeAssistant, client: Any, poll_interval: int, entry_id: str) -> None:
        super().__init__(hass, client, poll_interval, entry_id)
        self.capture_enabled = False
        self._capture_baselines: dict[str, dict[str, Any]] = {}
        self._capture_sequence: dict[str, int] = {}
        self._capture_lock = asyncio.Lock()
        self.capture_last_error: str | None = None

    def _capture_path(self, vin: str) -> Path:
        suffix = sha256(vin.encode("utf-8")).hexdigest()[:20]
        return Path(self.hass.config.path(".storage")) / f"gwm_ru_capture_{self.entry_id}_{suffix}.jsonl"

    def capture_start(self) -> None:
        """Enable only by explicit user service call; begin a fresh baseline."""
        self.capture_enabled = True
        self._capture_baselines.clear()
        self._capture_sequence.clear()
        self.capture_last_error = None

    def capture_stop(self) -> None:
        self.capture_enabled = False

    async def capture_marker(self, label: str, vin: str | None = None) -> None:
        if not self.capture_enabled:
            raise HomeAssistantError("Сначала включите запись протокола")
        label = " ".join(label.split())
        if not label or len(label) > MAX_MARKER_LENGTH:
            raise HomeAssistantError("Метка должна содержать от 1 до 80 символов")
        selected = self.resolve_vin(vin)
        if not selected or selected not in {v.get("vin") for v in self.vehicles}:
            raise HomeAssistantError("Автомобиль не найден")
        if any(value and value in label for value in (v.get("vin") for v in self.vehicles)):
            raise HomeAssistantError("Не включайте VIN в метку")
        await self._capture_append(selected, {"schema": 2, "type": "marker", "time": datetime.now(timezone.utc).isoformat(), "label": label})

    async def _capture_append(self, vin: str, record: dict[str, Any]) -> None:
        async with self._capture_lock:
            sequence = self._capture_sequence.get(vin, 0) + 1
            record["seq"] = sequence
            await self.hass.async_add_executor_job(_append_record, self._capture_path(vin), record)
            self._capture_sequence[vin] = sequence

    async def _async_update_data(self) -> dict[str, Any]:
        data = await super()._async_update_data()
        if not self.capture_enabled:
            return data
        for vehicle in data.get("vehicles", []):
            try:
                await self._capture_vehicle(vehicle)
            except Exception as err:  # Research must never disrupt standard telemetry.
                self.capture_last_error = type(err).__name__
        return data

    async def _capture_vehicle(self, vehicle: dict[str, Any]) -> None:
        vin = vehicle.get("vin")
        if not isinstance(vin, str) or not vin:
            return
        diagnostics = vehicle.get("diagnostics") or {}
        raw_items = diagnostics.get("status_items") or []
        signals = {
            str(item["code"]): _safe_numeric(item.get("value"))
            for item in raw_items
            if isinstance(item, dict) and str(item.get("code", "")).isdigit()
            and len(str(item.get("code"))) <= 12
        }
        raw_state = vehicle.get("state") or {}
        state = {key: _safe_numeric(value) for key, value in raw_state.items() if key in STATE_KEYS and key != "engine_state_source"}
        if raw_state.get("engine_state_source") in STATE_SOURCES:
            state["engine_state_source"] = raw_state["engine_state_source"]
        raw_meta = diagnostics.get("status_top_level") or {}
        meta = {key: _safe_numeric(value) for key, value in raw_meta.items() if key in STATUS_KEYS and key != "command"}
        if raw_meta.get("command") == "STATUS":
            meta["command"] = "STATUS"
        basics: dict[str, Any] = {}
        # Read-only GETs only while the user explicitly records. Never store responses.
        try:
            payload = await self.client._request("GET", ENDPOINT_VEHICLE_BASICS_INFO, params={"vin": vin}, vin_header=vin)
            config = (payload.get("data") or {}).get("config") or {}
            if isinstance(config, dict):
                for key in BASICS_KEYS:
                    value = config.get(key)
                    if key == "quickSettings" and isinstance(value, str) and len(value) <= 30 and all(char in "0123456789," for char in value):
                        basics[key] = value
                    elif key == "powerGear" and key in config:
                        basics[key] = _safe_numeric(value)
        except Exception:
            pass
        power_fields: dict[str, Any] = {}
        power_probe = "unavailable"
        try:
            response = await self.client._request(
                "GET", ENDPOINT_LAST_STATUS,
                params={"vin": vin, "seqNo": "", "modelId": ""}, vin_header=vin,
            )
            power_fields = _power_fields(response.get("data"))
            power_probe = "ok"
        except Exception:
            power_probe = "request_failed"
        current = {
            "signals": signals, "state": state, "status_meta": meta,
            "vehicle_basics": basics, "power_fields": power_fields,
        }
        previous = self._capture_baselines.get(vin)
        freshness = _freshness(previous, current)
        compare = previous is not None and freshness == "fresh"
        record = {
            "schema": 2,
            "type": "refresh",
            "time": datetime.now(timezone.utc).isoformat(),
            "baseline": previous is None,
            "freshness": freshness,
            "power_probe": power_probe,
            **current,
            "changes": {key: _diff(previous[key], current[key]) for key in current} if compare else {},
        }
        await self._capture_append(vin, record)
        if previous is None or freshness == "fresh":
            self._capture_baselines[vin] = current

    async def async_capture_diagnostics(self) -> dict[str, Any]:
        """Read only known-vehicle files; never expose VIN or file paths."""
        result: dict[str, Any] = {"enabled": self.capture_enabled, "last_error": self.capture_last_error, "vehicles": []}
        for vehicle in self.vehicles:
            vin = vehicle.get("vin")
            if not isinstance(vin, str) or not vin:
                continue
            try:
                record = await self.hass.async_add_executor_job(_read_records, self._capture_path(vin))
            except OSError:
                record = {"records": [], "total": 0, "truncated": False, "read_error": "io_error"}
            result["vehicles"].append(record)
        return result
