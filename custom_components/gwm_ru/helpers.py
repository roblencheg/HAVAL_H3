"""Helper functions for the GWM RU integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import ITEM_MAP, KPA_TO_ATM, Conversion

_LOGGER = logging.getLogger(__name__)

STATUS_ITEM_MAP: dict[str, str] = {
    "2208001": "lock_state",
    "2206001": "trunk_state",
    "2206002": "door_fl_state",
    "2206003": "door_rl_state",
    "2206004": "door_fr_state",
    "2206005": "door_rr_state",
    "2202001": "climate_state",
    "2210001": "window_fl_state",
    "2210002": "window_fr_state",
    "2210003": "window_rl_state",
    "2210004": "window_rr_state",
    "2210005": "sunroof_state",
    "2210032": "rear_defroster_state",
    "2220001": "driver_seat_heater_state",
    "2220002": "passenger_seat_heater_state",
    "2060016": "steering_wheel_heater_state",
    "2078020": "cabin_clean_state",
    "2310001": "gps_switch_state",
}


def normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if len(digits) == 11 and digits[0] in {"7", "8"}:
        digits = digits[1:]
    if len(digits) != 10:
        raise ConfigEntryAuthFailed("Phone must contain 10 Russian local digits")
    return digits


def value_to_number(value: Any) -> Any:
    try:
        if isinstance(value, str) and "." in value:
            return float(value)
        return int(value)
    except (TypeError, ValueError):
        return value


def _state_equals(value: Any, expected: str) -> bool | None:
    if value is None:
        return None
    return str(value) == expected


def _window_open(value: Any) -> bool | None:
    if value is None:
        return None
    return str(value) in {"2", "3"}


def _sunroof_open(value: Any) -> bool | None:
    if value is None:
        return None
    # GWM status mapping uses 3 for fully closed; other reported positions are
    # treated as not closed until model-specific semantics prove otherwise.
    return str(value) != "3"


def _build_vehicle_status(state: dict[str, Any]) -> str:
    if state.get("engine_on") is True:
        return "Запущена"
    openings = [
        state.get("door_fl_open"),
        state.get("door_fr_open"),
        state.get("door_rl_open"),
        state.get("door_rr_open"),
        state.get("trunk_open"),
    ]
    if state.get("unlocked") is True or any(value is True for value in openings):
        return "Открыта"
    if state.get("locked") is True:
        return "На охране"
    return "Неизвестно"


def build_state(status: dict[str, Any], tbox: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {
        "service_status": status.get("serviceStatus"),
        "oil_qty": status.get("oilQty"),
    }
    for item in status.get("items") or []:
        code = str(item.get("code"))
        raw_value = item.get("value")
        value = value_to_number(raw_value)

        if code in ITEM_MAP:
            defn = ITEM_MAP[code]
            val = value
            if defn.convert == Conversion.PRESSURE and isinstance(val, (int, float)):
                val = round(val / KPA_TO_ATM, 1)
            state[defn.key] = val
        elif code not in STATUS_ITEM_MAP:
            _LOGGER.debug("Unknown vehicle item code: %s = %s", code, raw_value)

        if code in STATUS_ITEM_MAP:
            state[STATUS_ITEM_MAP[code]] = value

    state["locked"] = _state_equals(state.get("lock_state"), "0")
    state["unlocked"] = _state_equals(state.get("lock_state"), "1")
    state["trunk_open"] = _state_equals(state.get("trunk_state"), "1")
    state["door_fl_open"] = _state_equals(state.get("door_fl_state"), "1")
    state["door_fr_open"] = _state_equals(state.get("door_fr_state"), "1")
    state["door_rl_open"] = _state_equals(state.get("door_rl_state"), "1")
    state["door_rr_open"] = _state_equals(state.get("door_rr_state"), "1")
    state["climate_on"] = _state_equals(state.get("climate_state"), "1")
    state["window_fl_open"] = _window_open(state.get("window_fl_state"))
    state["window_fr_open"] = _window_open(state.get("window_fr_state"))
    state["window_rl_open"] = _window_open(state.get("window_rl_state"))
    state["window_rr_open"] = _window_open(state.get("window_rr_state"))
    state["sunroof_open"] = _sunroof_open(state.get("sunroof_state"))
    state["rear_defroster_on"] = _state_equals(state.get("rear_defroster_state"), "1")
    state["driver_seat_heater_on"] = _state_equals(state.get("driver_seat_heater_state"), "1")
    state["passenger_seat_heater_on"] = _state_equals(state.get("passenger_seat_heater_state"), "1")
    state["steering_wheel_heater_on"] = _state_equals(state.get("steering_wheel_heater_state"), "1")
    state["cabin_clean_on"] = _state_equals(state.get("cabin_clean_state"), "1")
    state["gps_enabled"] = _state_equals(state.get("gps_switch_state"), "1")

    engine_state = status.get("hyEngSts")
    state["engine_state"] = value_to_number(engine_state) if engine_state is not None else None
    state["engine_on"] = _state_equals(state.get("engine_state"), "1")
    state["vehicle_status"] = _build_vehicle_status(state)

    tbox_status = tbox.get("status") if isinstance(tbox, dict) else None
    state["tbox_status"] = tbox_status
    state["tbox_online"] = str(tbox_status) == "1"
    return state


def redact_vehicle(vehicle: dict[str, Any]) -> dict[str, Any]:
    hidden = {"vin", "showedVin", "engineNo", "simIccid", "imsi"}
    return {key: ("***REDACTED***" if key in hidden else value) for key, value in vehicle.items()}
