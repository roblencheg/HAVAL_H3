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

    # beta migration: 30 s used to be the default and is unnecessarily long.
    # Preserve explicitly configured non-default values, but migrate the old
    # default to the new 5 s value automatically.
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

        instructions = copy.deepcopy(cmd["instructions"])
        if call.service == "rear_defrost_on":
            instructions["0x0B"]["defrost"]["operationTime"] = str(call.data.get("operation_time", 10))
        elif call.service == "steering_wheel_heat_on":
            instructions["0x19"]["operationTime"] = str(call.data.get("operation_time", 10))
        elif call.service == "engine_start":
            instructions["0x03"]["operationTime"] = str(call.data.get("operation_time", 15))

        security_pin = _get_security_pin(call)
        if not security_pin:
            raise HomeAssistantError("Security PIN is required. Add it in GWM RU integration settings or pass security_pin in service data.")

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
