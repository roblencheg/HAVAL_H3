"""Opt-in, per-vehicle protocol capture for controlled GWM telemetry experiments.

Based on the protocol-capture concept in IndeecDen/ha-gwm-jolion (MIT).
Copyright (c) 2026 IndeecDen. Copyright (c) 2026 roblencheg.
No credentials, VIN, position, IMSI, device identifiers or entire cloud responses
are written. Only explicitly allowlisted telemetry and configuration fields.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import ENDPOINT_VEHICLE_BASICS_INFO
from .coordinator import GwmRuCoordinator

MAX_RECORDS = 500
MAX_MARKER_LENGTH = 80
STATE_KEYS = frozenset({"engine_state", "engine_on", "engine_state_source", "climate_state", "lock_state", "tbox_status", "tbox_online"})
BASICS_KEYS = frozenset({"powerGear", "quickSettings"})
STATUS_KEYS = frozenset({"acquisitionTime", "updateTime", "serviceStatus", "command"})


def _safe_value(value: Any) -> str | int | float | bool | None:
    """Reject arbitrary cloud objects/long strings that could contain identifiers."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str) and len(value) <= 48 and all(ch.isalnum() or ch in " -_." for ch in value):
        return value
    return None


def _diff(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"key": key, "previous": before.get(key), "value": after.get(key)}
        for key in sorted(before.keys() | after.keys())
        if before.get(key) != after.get(key)
    ]


def _append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        handle.write("\n")


def _read_records(path: Path) -> dict[str, Any]:
    """Bounded export preserving the first baseline and latest records."""
    baseline = None
    recent: deque[dict[str, Any]] = deque(maxlen=MAX_RECORDS)
    count = 0
    if not path.is_file():
        return {"records": [], "total": 0, "truncated": False}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(record, dict) or record.get("schema") != 1:
                continue
            count += 1
            if baseline is None and record.get("type") == "refresh" and record.get("baseline"):
                baseline = record
            else:
                recent.append(record)
    records = ([baseline] if baseline is not None else []) + list(recent)
    return {"records": records, "total": count, "truncated": count > len(records)}


class GwmRuCaptureCoordinator(GwmRuCoordinator):
    """Existing coordinator plus explicitly enabled diagnostic capture."""

    def __init__(self, hass: HomeAssistant, client: Any, poll_interval: int, entry_id: str) -> None:
        super().__init__(hass, client, poll_interval, entry_id)
        self.capture_enabled = False
        self._capture_baselines: dict[str, dict[str, Any]] = {}
        self._capture_sequence: dict[str, int] = {}
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
        label = " ".join(str(label).split())
        if not label or len(label) > MAX_MARKER_LENGTH:
            raise HomeAssistantError("Метка должна содержать от 1 до 80 символов")
        # Markers are supplied by the user; do not allow a VIN in a marker.
        selected = self.resolve_vin(vin)
        if not selected or selected not in {v.get("vin") for v in self.vehicles}:
            raise HomeAssistantError("Автомобиль не найден")
        if any(vin_value and vin_value in label for vin_value in (v.get("vin") for v in self.vehicles)):
            raise HomeAssistantError("Не включайте VIN в метку")
        await self._capture_append(selected, {"schema": 1, "type": "marker", "time": datetime.now(timezone.utc).isoformat(), "label": label})

    async def _capture_append(self, vin: str, record: dict[str, Any]) -> None:
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
            str(item["code"]): _safe_value(item.get("value"))
            for item in raw_items
            if isinstance(item, dict) and str(item.get("code", "")).isdigit()
            and len(str(item.get("code"))) <= 12
        }
        state = {key: _safe_value(value) for key, value in (vehicle.get("state") or {}).items() if key in STATE_KEYS}
        meta = {key: _safe_value(value) for key, value in (diagnostics.get("status_top_level") or {}).items() if key in STATUS_KEYS}
        basics: dict[str, Any] = {}
        # Only a GET, and only while a user-initiated capture is running.
        try:
            payload = await self.client._request("GET", ENDPOINT_VEHICLE_BASICS_INFO, params={"vin": vin}, vin_header=vin)
            config = (payload.get("data") or {}).get("config") or {}
            if isinstance(config, dict):
                basics = {key: _safe_value(config.get(key)) for key in BASICS_KEYS if key in config}
        except Exception:
            pass
        current = {"signals": signals, "state": state, "status_meta": meta, "vehicle_basics": basics}
        previous = self._capture_baselines.get(vin)
        record = {
            "schema": 1,
            "type": "refresh",
            "time": datetime.now(timezone.utc).isoformat(),
            "baseline": previous is None,
            **current,
            "changes": {} if previous is None else {key: _diff(previous[key], current[key]) for key in current},
        }
        await self._capture_append(vin, record)
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
