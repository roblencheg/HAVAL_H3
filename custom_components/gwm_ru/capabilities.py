"""Capability parsing and feature registry for GWM RU vehicles.

The Russian GWM app exposes a per-VIN capability tree.  This module keeps
model-specific assumptions out of the entity platforms: entities are created
from what the cloud says the concrete vehicle supports.
"""

from __future__ import annotations

from typing import Any

# Remote command -> capability functionCode.
COMMAND_CAPABILITIES: dict[str, str] = {
    "engine_start": "1-1-1-1",
    "engine_stop": "1-1-1-2",
    "unlock_vehicle": "1-1-2-1",
    "lock_vehicle": "1-1-2-2",
    "flash_lights": "1-1-3-1",
    "horn": "1-1-3-2",
    "flash_and_horn": "1-1-3-3",
    "open_trunk": "1-1-4-1",
    "close_trunk": "1-1-4-2",
    "rear_defrost_on": "1-1-5-1",
    "rear_defrost_off": "1-1-5-2",
    "close_windows": "1-1-6-2",
    "close_sunroof": "1-1-7-2",
    "steering_wheel_heat_on": "1-1-21-1",
    "steering_wheel_heat_off": "1-1-21-2",
    # open_sunroof/open_sunshade/close_sunshade intentionally have no known
    # capability code yet. They remain hidden when a capability tree is
    # available rather than being offered speculatively on every model.
}

# State/entity key -> capability functionCode. Parent codes are sufficient for
# grouped state such as four doors/windows.
STATE_CAPABILITIES: dict[str, str] = {
    "mileage_total": "1-2-4",
    "range_km": "1-2-5-1",
    "fuel_liters": "1-2-6-2",
    "tire_fl_pressure": "1-2-7-1",
    "tire_fr_pressure": "1-2-7-2",
    "tire_rl_pressure": "1-2-7-3",
    "tire_rr_pressure": "1-2-7-4",
    "tire_fl_temp": "1-2-9-1",
    "tire_fr_temp": "1-2-9-2",
    "tire_rl_temp": "1-2-9-3",
    "tire_rr_temp": "1-2-9-4",
    "engine_state": "1-2-12",
    "engine_on": "1-2-12",
    "climate_state": "1-2-13",
    "climate_on": "1-2-13",
    "lock_state": "1-2-19",
    "locked": "1-2-19",
    "unlocked": "1-2-19",
    "trunk_state": "1-2-20",
    "trunk_open": "1-2-20",
    "door_fl_open": "1-2-1-1",
    "door_fr_open": "1-2-1-2",
    "door_rl_open": "1-2-1-3",
    "door_rr_open": "1-2-1-4",
    "window_fl_open": "1-2-2-1",
    "window_fr_open": "1-2-2-2",
    "window_rl_open": "1-2-2-3",
    "window_rr_open": "1-2-2-4",
    "rear_defroster_state": "1-2-16",
    "rear_defroster_on": "1-2-16",
    "steering_wheel_heater_state": "1-2-25",
    "steering_wheel_heater_on": "1-2-25",
}

# High-level normalized feature name -> one or more capability codes.
FEATURE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "engine": ("1-1-1", "1-2-12"),
    "engine_schedule": ("1-1-1-3",),
    "lock": ("1-1-2", "1-2-19"),
    "find_vehicle": ("1-1-3",),
    "trunk": ("1-1-4", "1-2-20"),
    "rear_defroster": ("1-1-5", "1-2-16"),
    "windows": ("1-1-6", "1-2-2"),
    "sunroof": ("1-1-7", "1-2-11"),
    "climate": ("1-1-9", "1-2-13"),
    "climate_temperature": ("1-1-9-1-1",),
    "climate_duration": ("1-1-9-1-2",),
    "front_defrost": ("1-1-9-1-6", "1-2-34"),
    "climate_schedule": ("1-1-9-3",),
    "seats": ("1-1-10", "1-2-15"),
    "driver_seat_heat": ("1-1-10-1-29", "1-2-15-1"),
    "passenger_seat_heat": ("1-1-10-1-17", "1-2-15-2"),
    "cabin_clean": ("1-1-12", "1-2-24"),
    "gps": ("1-1-15", "1-2-37"),
    "fota": ("1-1-19",),
    "steering_wheel_heater": ("1-1-21", "1-2-25"),
    "windshield_heater": ("1-1-22", "1-2-26"),
    "remote_history": ("1-1-25",),
    "one_button_comfort": ("1-1-28",),
    "location": ("1-2-17",),
    "trip_history": ("1-15",),
}

KNOWN_CODES: set[str] = {
    code
    for mapping in (COMMAND_CAPABILITIES, STATE_CAPABILITIES)
    for code in mapping.values()
}
KNOWN_CODES.update(code for codes in FEATURE_CAPABILITIES.values() for code in codes)


def flatten_capability_tree(raw: Any) -> tuple[set[str], list[dict[str, Any]]]:
    """Return all function codes and compact unknown nodes from API data."""
    codes: set[str] = set()
    unknown: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        code = node.get("functionCode")
        if code:
            code = str(code)
            codes.add(code)
            if code not in KNOWN_CODES:
                unknown.append(
                    {
                        "functionCode": code,
                        "functionName": node.get("functionName"),
                        "id": node.get("id"),
                    }
                )
        walk(node.get("children"))

    tree = raw.get("treeVO") if isinstance(raw, dict) else raw
    walk(tree)
    return codes, unknown


def build_vehicle_capabilities(raw: Any) -> dict[str, Any]:
    """Build normalized, model-agnostic capability information."""
    codes, unknown = flatten_capability_tree(raw)
    features = {
        name: any(code in codes for code in feature_codes)
        for name, feature_codes in FEATURE_CAPABILITIES.items()
    }
    features["remote_commands"] = any(code.startswith("1-1-") for code in codes)
    return {
        **features,
        "codes": sorted(codes),
        "unknown": unknown,
        "source": "gwm_cloud" if codes else "unavailable",
    }


def capability_codes(vehicle: dict[str, Any] | None) -> set[str]:
    """Get the raw capability code set for a vehicle snapshot."""
    if not vehicle:
        return set()
    capabilities = vehicle.get("capabilities") or {}
    return {str(code) for code in capabilities.get("codes") or []}


def has_capability(vehicle: dict[str, Any] | None, code: str) -> bool:
    """Check an exact capability code.

    If the cloud capability request failed, return True as a compatibility
    fallback so existing users do not lose all entities because of a transient
    endpoint problem.
    """
    if not vehicle:
        return False
    capabilities = vehicle.get("capabilities") or {}
    if capabilities.get("source") != "gwm_cloud":
        return True
    return code in capability_codes(vehicle)


def supports_command(vehicle: dict[str, Any] | None, command_key: str) -> bool:
    """Return whether a known remote command is explicitly supported."""
    if not vehicle:
        return False
    capabilities = vehicle.get("capabilities") or {}
    if capabilities.get("source") != "gwm_cloud":
        return True
    code = COMMAND_CAPABILITIES.get(command_key)
    return bool(code and has_capability(vehicle, code))


def supports_state(vehicle: dict[str, Any] | None, state_key: str) -> bool:
    """Return whether a state-backed entity is supported by the vehicle."""
    code = STATE_CAPABILITIES.get(state_key)
    return True if code is None else has_capability(vehicle, code)
