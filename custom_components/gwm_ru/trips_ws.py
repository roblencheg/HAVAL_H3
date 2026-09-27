"""Authenticated trip history access for bundled GWM dashboard cards."""
from __future__ import annotations

import asyncio
import logging

import voluptuous as vol
from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@callback
def register(hass) -> None:
    """Register the card websocket once per Home Assistant process."""
    if hass.data[DOMAIN].get("_trips_ws"):
        return
    websocket_api.async_register_command(hass, get_trips)
    hass.data[DOMAIN]["_trips_ws"] = True


@websocket_api.websocket_command({
    vol.Required("type"): "gwm_ru/trips",
    vol.Required("entity_id"): str,
    vol.Required("start"): str,
    vol.Required("end"): str,
    vol.Optional("odometer_entity"): str,
})
@websocket_api.async_response
async def get_trips(hass, connection, msg) -> None:
    entity_id = msg["entity_id"]
    if not connection.user.permissions.check_entity(entity_id, POLICY_READ):
        connection.send_error(msg["id"], "unauthorized", "Нет доступа к автомобилю")
        return

    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    parent = hass.data[DOMAIN].get(entry.config_entry_id) if entry else None
    if not entry or entry.platform != DOMAIN or not entity_id.startswith("device_tracker.") or parent is None:
        connection.send_error(msg["id"], "not_found", "Выберите местоположение автомобиля GWM")
        return

    vin = None
    for vehicle in parent.vehicles:
        candidate = vehicle.get("vin")
        if candidate and entry.unique_id == f"{parent.entity_prefix(candidate)}_location":
            vin = candidate
            break
    histories = getattr(parent, "trip_histories", {})
    trip_history = histories.get(vin) if vin else None
    if trip_history is None:
        connection.send_error(msg["id"], "not_found", "История поездок для автомобиля пока недоступна")
        return

    try:
        archive = None
        if "recorder" in getattr(hass.config, "components", set()):
            prefix = parent.entity_prefix(vin)
            odometer = msg.get("odometer_entity") or registry.async_get_entity_id(
                "sensor", DOMAIN, f"{prefix}_mileage_total"
            )
            if odometer:
                sensor = registry.async_get(odometer)
                if (
                    not sensor
                    or sensor.platform != DOMAIN
                    or sensor.config_entry_id != entry.config_entry_id
                    or not odometer.startswith("sensor.")
                    or not connection.user.permissions.check_entity(odometer, POLICY_READ)
                ):
                    connection.send_error(
                        msg["id"], "unauthorized",
                        "Нет доступа к выбранному датчику пробега этого автомобиля",
                    )
                    return
            from .trips_recorder import read_history
            try:
                async with asyncio.timeout(10):
                    archive = await read_history(
                        hass, entity_id, odometer, msg["start"], msg["end"]
                    )
            except ValueError:
                raise
            except Exception:
                _LOGGER.warning("Recorder history unavailable; using local GWM trip history")

        result = await trip_history.query(
            msg["start"], msg["end"], hass.config.time_zone, archive
        )
    except ValueError:
        connection.send_error(
            msg["id"], "invalid_dates",
            "Проверьте даты: максимальный период 366 дней",
        )
    except Exception:
        _LOGGER.exception("Unable to read local GWM trip history")
        connection.send_error(
            msg["id"], "history_unavailable",
            "История поездок временно недоступна",
        )
    else:
        connection.send_result(msg["id"], result)
