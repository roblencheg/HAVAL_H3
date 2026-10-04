"""Shared services resolved against the current account and vehicle."""
from __future__ import annotations

import copy
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

from .commands import COMMANDS
from .const import CONF_SECURITY_PIN, DOMAIN
from .coordinator import GwmRuCoordinator


def resolve_coordinator(hass: HomeAssistant, data: dict) -> GwmRuCoordinator:
    coordinators = [item for item in hass.data.get(DOMAIN, {}).values()
                    if isinstance(item, GwmRuCoordinator)]
    entry_id = data.get("entry_id")
    if entry_id:
        coordinators = [item for item in coordinators if item.entry_id == entry_id]
    vin = data.get("vin")
    if vin:
        coordinators = [item for item in coordinators if item.resolve_vin(vin)]
    device_id = data.get("device_id")
    if device_id:
        device = dr.async_get(hass).async_get(device_id)
        if device is None:
            raise HomeAssistantError("Vehicle device not found")
        coordinators = [item for item in coordinators
                        if any((DOMAIN, item.entity_prefix(v["vin"])) in device.identifiers
                               for v in item.vehicles)]
    if len(coordinators) != 1:
        raise HomeAssistantError("Specify a loaded GWM entry_id, device_id or unambiguous VIN")
    return coordinators[0]


def register_services(hass: HomeAssistant) -> None:
    def resolve(call: ServiceCall) -> GwmRuCoordinator:
        return resolve_coordinator(hass, call.data)

    def _get_security_pin(call: ServiceCall) -> str | None:
        return call.data.get(CONF_SECURITY_PIN) or resolve(call).security_pin

    def _resolve_vin(call: ServiceCall) -> str:
        coordinator = resolve(call)
        requested = call.data.get("vin")
        device_id = call.data.get("device_id")
        if device_id:
            device = dr.async_get(hass).async_get(device_id)
            requested = next((v["vin"] for v in coordinator.vehicles
                              if (DOMAIN, coordinator.entity_prefix(v["vin"])) in device.identifiers), None)
            if not requested or (call.data.get("vin") and coordinator.resolve_vin(call.data["vin"]) != requested):
                raise HomeAssistantError("Vehicle target does not match VIN")
        vin = coordinator.resolve_vin(requested)
        if not vin or coordinator.vehicle(vin) is None:
            raise HomeAssistantError("Vehicle VIN not available")
        return vin

    async def async_handle_command(call: ServiceCall) -> None:
        coordinator = resolve(call)
        if not coordinator.enable_remote_controls:
            raise HomeAssistantError("Remote controls are disabled for this integration")
        cmd = COMMANDS.get(call.service)
        if cmd is None:
            raise HomeAssistantError(f"Unknown command: {call.service}")
        vin = _resolve_vin(call)
        security_pin = _get_security_pin(call)
        if not security_pin:
            raise HomeAssistantError(
                "Security PIN is required. Add it in GWM RU integration settings or pass security_pin in service data."
            )

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

            return await coordinator.async_set_seat_heating(
                vin,
                level if cmd.get("seat") == "driver" else None,
                level if cmd.get("seat") == "passenger" else None,
                operation_time,
                str(security_pin),
            )
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
                    raise HomeAssistantError(
                        "Windshield heater operation_time must be an integer from 1 to 15"
                    ) from err
                instructions["0x2A"]["operationTime"] = str(min(15, max(1, operation_time)))
            elif call.service == "engine_start":
                instructions["0x03"]["operationTime"] = str(call.data.get("operation_time", 15))

        await coordinator.async_execute_t5(
            vin,
            instructions,
            cmd["expected_remote_type"],
            str(security_pin),
        )

    async def async_handle_seat_heating(call: ServiceCall) -> None:
        coordinator = resolve(call)
        if not coordinator.enable_remote_controls or not coordinator.security_pin:
            raise HomeAssistantError("Remote controls and security PIN are required")
        try:
            await coordinator.async_set_seat_heating(
                _resolve_vin(call),
                call.data.get("driver"),
                call.data.get("passenger"),
                call.data.get("operation_time", 5),
            )
        except (TypeError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err

    async def async_handle_comfort_start(call: ServiceCall) -> None:
        coordinator = resolve(call)
        if not coordinator.enable_remote_controls or not coordinator.security_pin:
            raise HomeAssistantError("Remote controls and security PIN are required")
        try:
            await coordinator.async_start_with_comfort(
                _resolve_vin(call),
                temperature=call.data["temperature"],
                climate_time=call.data.get("climate_time", 15),
                engine_time=call.data.get("engine_time", 15),
                driver=call.data.get("driver"),
                passenger=call.data.get("passenger"),
                seat_time=call.data.get("seat_time", 5),
                climate_enabled=call.data.get("climate_enabled", True),
            )
        except (TypeError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err

    async def async_handle_save_card_settings(call: ServiceCall) -> None:
        coordinator = resolve(call)
        try:
            await coordinator.async_save_card_settings(call.data["settings"])
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_handle_manage_profile(call: ServiceCall) -> None:
        coordinator = resolve(call)
        try:
            await coordinator.async_manage_profile(
                call.data["action"],
                profile_id=call.data.get("profile_id", ""),
                name=call.data.get("name", ""),
                settings=call.data.get("settings"),
            )
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    for command_key in COMMANDS:
        if not hass.services.has_service(DOMAIN, command_key):
            max_time = 10 if COMMANDS[command_key].get("dynamic") == "seat_heat" else 15 if command_key == "windshield_heat_on" else 30
            hass.services.async_register(
                DOMAIN, command_key, async_handle_command,
                schema=vol.Schema({
                    vol.Optional("entry_id"): str,
                    vol.Optional("device_id"): str,
                    vol.Optional("vin"): str,
                    vol.Optional(CONF_SECURITY_PIN): str,
                    vol.Optional("level"): vol.All(int, vol.Range(min=0, max=3)),
                    vol.Optional("operation_time"): vol.All(int, vol.Range(min=1, max=max_time)),
                }),
            )

    if not hass.services.has_service(DOMAIN, "set_seat_heating"):
        hass.services.async_register(
            DOMAIN,
            "set_seat_heating",
            async_handle_seat_heating,
            schema=vol.Schema({
                vol.Optional("entry_id"): str,
                vol.Optional("device_id"): str,
                vol.Optional("vin"): str,
                vol.Optional("driver"): vol.All(int, vol.Range(min=0, max=3)),
                vol.Optional("passenger"): vol.All(int, vol.Range(min=0, max=3)),
                vol.Optional("operation_time", default=5): vol.All(int, vol.Range(min=1, max=10)),
            }),
        )
    if not hass.services.has_service(DOMAIN, "start_with_comfort"):
        hass.services.async_register(
            DOMAIN,
            "start_with_comfort",
            async_handle_comfort_start,
            schema=vol.Schema({
                vol.Optional("entry_id"): str,
                vol.Optional("device_id"): str,
                vol.Optional("vin"): str,
                vol.Required("temperature"): vol.All(int, vol.Range(min=16, max=32)),
                vol.Optional("climate_enabled", default=True): bool,
                vol.Optional("climate_time", default=15): vol.All(int, vol.Range(min=5, max=30)),
                vol.Optional("engine_time", default=15): vol.All(int, vol.Range(min=5, max=30)),
                vol.Optional("seat_time", default=5): vol.All(int, vol.Range(min=1, max=10)),
                vol.Optional("driver"): vol.All(int, vol.Range(min=0, max=3)),
                vol.Optional("passenger"): vol.All(int, vol.Range(min=0, max=3)),
            }),
        )
    if not hass.services.has_service(DOMAIN, "save_card_settings"):
        hass.services.async_register(
            DOMAIN,
            "save_card_settings",
            async_handle_save_card_settings,
            schema=vol.Schema({
                vol.Optional("entry_id"): str,
                vol.Optional("device_id"): str,
                vol.Required("settings"): dict,
            }),
        )
    if not hass.services.has_service(DOMAIN, "manage_preparation_profile"):
        hass.services.async_register(
            DOMAIN,
            "manage_preparation_profile",
            async_handle_manage_profile,
            schema=vol.Schema({
                vol.Optional("entry_id"): str,
                vol.Optional("device_id"): str,
                vol.Required("action"): vol.In(["create", "update", "copy", "delete", "select"]),
                vol.Optional("profile_id"): str,
                vol.Optional("name"): str,
                vol.Optional("settings"): dict,
            }),
        )
