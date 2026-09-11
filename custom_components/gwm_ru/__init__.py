"""The GWM RU integration."""

from __future__ import annotations

import copy
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GwmRuApiClient
from .commands import COMMANDS
from .const import (
    CONF_COMMAND_COOLDOWN,
    CONF_COUNTRY,
    CONF_COUNTRY_CODE,
    CONF_DEVICE_ID,
    CONF_ENABLE_REMOTE_CONTROLS,
    CONF_PHONE,
    CONF_POLL_INTERVAL,
    CONF_SECURITY_PIN,
    DEFAULT_COMMAND_COOLDOWN,
    DEFAULT_COUNTRY,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_ENABLE_REMOTE_CONTROLS,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    LEGACY_COMMAND_COOLDOWN,
    PLATFORMS,
)
from .coordinator import GwmRuCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GWM RU from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    data = dict(entry.data)
    options = dict(entry.options)
    device_id = data.get(CONF_DEVICE_ID) or uuid4().hex

    if options.get(CONF_COMMAND_COOLDOWN) == LEGACY_COMMAND_COOLDOWN:
        options[CONF_COMMAND_COOLDOWN] = DEFAULT_COMMAND_COOLDOWN
        hass.config_entries.async_update_entry(entry, options=options)

    client = GwmRuApiClient(
        async_get_clientsession(hass),
        phone=data[CONF_PHONE],
        password=data[CONF_PASSWORD],
        device_id=device_id,
        country=data.get(CONF_COUNTRY, DEFAULT_COUNTRY),
        country_code=data.get(CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE),
    )
    coordinator = GwmRuCoordinator(
        hass,
        client,
        int(options.get(CONF_POLL_INTERVAL, data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))),
        entry.entry_id,
    )
    coordinator.enable_remote_controls = options.get(CONF_ENABLE_REMOTE_CONTROLS, DEFAULT_ENABLE_REMOTE_CONTROLS)
    coordinator.command_cooldown = max(0, int(options.get(CONF_COMMAND_COOLDOWN, data.get(CONF_COMMAND_COOLDOWN, DEFAULT_COMMAND_COOLDOWN))))
    coordinator.security_pin = options.get(CONF_SECURITY_PIN) or data.get(CONF_SECURITY_PIN) or None

    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass, coordinator, entry)
    return True


def _register_services(hass: HomeAssistant, coordinator: GwmRuCoordinator, entry: ConfigEntry) -> None:
    def _get_security_pin(call: ServiceCall) -> str | None:
        return call.data.get(CONF_SECURITY_PIN) or entry.options.get(CONF_SECURITY_PIN) or entry.data.get(CONF_SECURITY_PIN) or None

    async def async_handle_command(call: ServiceCall) -> None:
        if not coordinator.enable_remote_controls:
            raise HomeAssistantError("Remote controls are disabled for this integration")
        cmd = COMMANDS.get(call.service)
        if cmd is None:
            raise HomeAssistantError(f"Unknown command: {call.service}")
        try:
            coordinator.check_command_cooldown()
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

        vin = coordinator.resolve_vin(call.data.get("vin"))
        if not vin:
            raise HomeAssistantError("Vehicle VIN not available")

        security_pin = _get_security_pin(call)
        if not security_pin:
            raise HomeAssistantError("Security PIN is required. Add it in GWM RU integration settings or pass security_pin in service data.")

        if cmd.get("dynamic") == "seat_heat":
            try:
                level = int(call.data.get("level", 0))
            except (TypeError, ValueError) as err:
                raise HomeAssistantError("Seat heat level must be an integer from 0 to 3") from err
            if level < 0 or level > 3:
                raise HomeAssistantError("Seat heat level must be between 0 and 3")
            try:
                operation_time = int(call.data.get("operation_time", 5))
            except (TypeError, ValueError) as err:
                raise HomeAssistantError("Seat heat operation_time must be an integer from 1 to 10") from err
            operation_time = min(10, max(1, operation_time))

            vehicle = coordinator.vehicle(vin) or {}
            car = vehicle.get("vehicle") or {}
            state = vehicle.get("state") or {}
            driver_level = int(state.get("driver_seat_heater_state") or 0)
            passenger_level = int(state.get("passenger_seat_heater_state") or 0)
            if cmd.get("seat") == "driver":
                driver_level = level
            else:
                passenger_level = level

            # Official APK: rudder == "2" means right-hand drive. T5 seat payload
            # is physical left/right, while HA entities are driver/passenger.
            driver_is_right = str(car.get("rudder") or "1") == "2"
            left_front = passenger_level if driver_is_right else driver_level
            right_front = driver_level if driver_is_right else passenger_level
            any_heat = left_front > 0 or right_front > 0
            instructions = {
                "0x0A": {
                    "seat": {
                        "operationMode": "1",  # APK/comfort template: heating
                        "switchOrder": "1" if any_heat else "2",
                        "operationTime": str(operation_time if any_heat else 0),
                        "leftFront": str(left_front),
                        "rightFront": str(right_front),
                        "leftBack": "0",
                        "rightBack": "0",
                        "leftThirdRow": "0",
                        "rightThirdRow": "0",
                    }
                }
            }
        else:
            instructions = copy.deepcopy(cmd["instructions"])
            if call.service == "rear_defrost_on":
                instructions["0x0B"]["defrost"]["operationTime"] = str(call.data.get("operation_time", 10))
            elif call.service == "steering_wheel_heat_on":
                instructions["0x19"]["operationTime"] = str(call.data.get("operation_time", 10))
            elif call.service == "windshield_heat_on":
                try:
                    operation_time = int(call.data.get("operation_time", 15))
                except (TypeError, ValueError) as err:
                    raise HomeAssistantError("Windshield heater operation_time must be an integer from 1 to 15") from err
                instructions["0x2A"]["operationTime"] = str(min(15, max(1, operation_time)))
            elif call.service == "engine_start":
                instructions["0x03"]["operationTime"] = str(call.data.get("operation_time", 15))

        await coordinator.async_execute_t5(vin, instructions, cmd["expected_remote_type"], str(security_pin))

    for command_key in COMMANDS:
        hass.services.async_register(DOMAIN, command_key, async_handle_command)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    for command_key in COMMANDS:
        if hass.services.has_service(DOMAIN, command_key):
            hass.services.async_remove(DOMAIN, command_key)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
