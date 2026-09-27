"""Read existing entity history, including GPS attribute-only changes."""
from datetime import datetime, timezone
from functools import partial

from homeassistant.components.recorder import get_instance, history

from .trips import PARKING_BASELINE_SECONDS, number, period


def observations(states, tracker, odometer):
    gps, mileage = [], []
    for state in states.get(tracker, []):
        lat, lon = (number(state.attributes.get(key)) for key in ("latitude", "longitude"))
        if state.state in ("unknown", "unavailable") or lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180 or (lat == 0 and lon == 0):
            lat = lon = None
        gps.append((state.last_updated.timestamp(), lat, lon, None))
    for state in states.get(odometer, []):
        value = number(state.state)
        unit = state.attributes.get("unit_of_measurement", "km")
        if unit == "mi" and value is not None:
            value *= 1.609344
        elif unit not in ("km", "км"):
            value = None
        if value is not None and value < 0: value = None
        mileage.append((state.last_updated.timestamp(), None, None, value))
    return gps, mileage


async def read_history(hass, tracker, odometer, start, end):
    low, high = period(start, end, hass.config.time_zone)
    states = await get_instance(hass).async_add_executor_job(partial(
        history.get_significant_states, hass,
        datetime.fromtimestamp(low - PARKING_BASELINE_SECONDS, timezone.utc), datetime.fromtimestamp(high, timezone.utc),
        [tracker] + ([odometer] if odometer else []),
        include_start_time_state=True, significant_changes_only=False,
        minimal_response=False, no_attributes=False,
    ))
    return observations(states, tracker, odometer)
