"""Helper functions for the GWM RU integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import ITEM_MAP, KPA_TO_ATM, Conversion

_LOGGER = logging.getLogger(__name__)


def normalize_phone(raw: str) -> str:
    """Normalize Russian phone to 10 digits without +7."""
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


def build_state(status: dict[str, Any], tbox: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {
        "service_status": status.get("serviceStatus"),
        "oil_qty": status.get("oilQty"),
    }
    for item in status.get("items") or []:
        code = str(item.get("code"))
        if code in ITEM_MAP:
            defn = ITEM_MAP[code]
            val = value_to_number(item.get("value"))
            if defn.convert == Conversion.PRESSURE and isinstance(val, (int, float)):
                val = round(val / KPA_TO_ATM, 1)
            state[defn.key] = val
        else:
            _LOGGER.debug("Unknown vehicle item code: %s = %s", code, item.get("value"))
    tbox_status = tbox.get("status") if isinstance(tbox, dict) else None
    state["tbox_status"] = tbox_status
    state["tbox_online"] = str(tbox_status) == "1"
    vehicle_basics = tbox.get("vehicleBasicsInfo") if isinstance(tbox, dict) else None
    if vehicle_basics:
        _LOGGER.debug("vehicleBasicsInfo: %s", vehicle_basics)
    _LOGGER.debug("TBOX data keys: %s", list(tbox.keys()) if isinstance(tbox, dict) else "none")
    return state


def redact_vehicle(vehicle: dict[str, Any]) -> dict[str, Any]:
    hidden = {"vin", "showedVin", "engineNo", "simIccid", "imsi"}
    return {key: ("***REDACTED***" if key in hidden else value) for key, value in vehicle.items()}
