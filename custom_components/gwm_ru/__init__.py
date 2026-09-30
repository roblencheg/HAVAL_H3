"""The GWM RU integration."""

from __future__ import annotations

import copy
import logging
from pathlib import Path
import time
from uuid import uuid4

import voluptuous as vol
from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE
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
from .trips import TripHistory
from .trips_ws import register as register_trips

_LOGGER = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent / "frontend"
FRONTEND_VERSION = "1.1.3"
FRONTEND_BUNDLE_PATH = "/gwm-vehicle/gwm-vehicle-bundle.js"
FRONTEND_BUNDLE_URL = f"{FRONTEND_BUNDLE_PATH}?v={FRONTEND_VERSION}"
FRONTEND_ASSETS = (
    (FRONTEND_DIR / "gwm-vehicle-bundle.js", FRONTEND_BUNDLE_PATH),
    (FRONTEND_DIR / "gwm-vehicle-trips-card.js", "/gwm-vehicle/gwm-vehicle-trips-card.js"),
    (FRONTEND_DIR / "gwm-vehicle-card-editor.js", "/gwm-vehicle/gwm-vehicle-card-editor.js"),
    (FRONTEND_DIR / "gwm-vehicle-card.js", "/gwm-vehicle/gwm-vehicle-card.js"),
    (FRONTEND_DIR / "gwm-vehicle-remote-card.js", "/gwm-vehicle/gwm-vehicle-remote-card.js"),
    (FRONTEND_DIR / "gwm-vehicle-remote-horizontal-card.js", "/gwm-vehicle/gwm-vehicle-remote-horizontal-card.js"),
    (FRONTEND_DIR / "gwm-vehicle-remote-modern-card.js", "/gwm-vehicle/gwm-vehicle-remote-modern-card.js"),
    (FRONTEND_DIR / "gwm-vehicle-compat.js", "/gwm-vehicle/gwm-vehicle-compat.js"),
)
DATA_FRONTEND_REGISTERED = "_frontend_registered"

async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve bundled cards and load them before Lovelace renders dashboards.

    Storage-mode Lovelace resources are awaited by the frontend before card
    configuration is rendered. This avoids a race where dynamically-added
    frontend modules arrive after Lovelace has already tried to instantiate
    the custom element.
    """
    if hass.data[DOMAIN].get(DATA_FRONTEND_REGISTERED):
        return

    missing = [path for path, _url in FRONTEND_ASSETS if not path.exists()]
    for path in missing:
        _LOGGER.warning("Bundled GWM dashboard asset not found: %s", path)
    if missing:
        return

    static_paths = [
        StaticPathConfig(static_url, str(path), False)
        for path, static_url in FRONTEND_ASSETS
    ]
    if (FRONTEND_DIR / "leaflet").exists():
        static_paths.append(
            StaticPathConfig("/gwm-vehicle/leaflet", str(FRONTEND_DIR / "leaflet"), True)
        )
    if (FRONTEND_DIR / "maplibre").exists():
        static_paths.append(
            StaticPathConfig("/gwm-vehicle/maplibre", str(FRONTEND_DIR / "maplibre"), True)
        )
    await hass.http.async_register_static_paths(static_paths)

    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is not None and lovelace_data.resource_mode == MODE_STORAGE:
        resources = lovelace_data.resources
        await resources.async_get_info()
        existing = next(
            (
                item
                for item in resources.async_items()
                if str(item.get("url") or "").split("?", 1)[0] == FRONTEND_BUNDLE_PATH
            ),
            None,
        )
        if existing is None:
            await resources.async_create_item(
                {"res_type": "module", "url": FRONTEND_BUNDLE_URL}
            )
            _LOGGER.debug("Created Lovelace resource %s", FRONTEND_BUNDLE_URL)
        elif existing.get("url") != FRONTEND_BUNDLE_URL or existing.get("type") != "module":
            await resources.async_update_item(
                existing["id"],
                {"res_type": "module", "url": FRONTEND_BUNDLE_URL},
            )
            _LOGGER.debug("Updated Lovelace resource %s", FRONTEND_BUNDLE_URL)
    else:
        # YAML resource mode cannot be modified through storage. Keep the
        # Home Assistant frontend-module mechanism as a compatibility fallback.
        frontend.add_extra_js_url(hass, FRONTEND_BUNDLE_URL)
        _LOGGER.debug(
            "Registered GWM dashboard bundle as frontend extra module (YAML fallback)"
        )

    hass.data[DOMAIN][DATA_FRONTEND_REGISTERED] = True
    _LOGGER.debug("Registered bundled GWM dashboard resource: %s", FRONTEND_BUNDLE_URL)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GWM RU from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    await _async_register_frontend(hass)

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
    coordinator.command_cooldown = max(
        0,
        int(options.get(
            CONF_COMMAND_COOLDOWN,
            data.get(CONF_COMMAND_COOLDOWN, DEFAULT_COMMAND_COOLDOWN),
        )),
    )
    coordinator.security_pin = options.get(CONF_SECURITY_PIN) or data.get(CONF_SECURITY_PIN) or None

    await coordinator.async_load_card_settings()
    await coordinator.async_load_profiles()
    await coordinator.async_config_entry_first_refresh()

    for index, vehicle in enumerate(coordinator.vehicles):
        vin = vehicle.get("vin")
        if not vin:
            continue
        history = TripHistory(hass, f"{entry.entry_id}_{index}", 90)
        coordinator.trip_histories[vin] = history
        location = vehicle.get("location") or {}
        state = vehicle.get("state") or {}
        try:
            await history.append(
                time.time(),
                {
                    "latitude": location.get("latitude"),
                    "longitude": location.get("longitude"),
                    "odometer": state.get("mileage_total"),
                },
            )
        except Exception:
            _LOGGER.debug("Could not save initial GWM trip point", exc_info=True)

    hass.data[DOMAIN][entry.entry_id] = coordinator
    register_trips(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass, coordinator, entry)
    return True


def _register_services(hass: HomeAssistant, coordinator: GwmRuCoordinator, entry: ConfigEntry) -> None:
    def _get_security_pin(call: ServiceCall) -> str | None:
        return (
            call.data.get(CONF_SECURITY_PIN)
            or entry.options.get(CONF_SECURITY_PIN)
            or entry.data.get(CONF_SECURITY_PIN)
            or None
        )

    def _resolve_vin(call: ServiceCall) -> str:
        vin = coordinator.resolve_vin(call.data.get("vin"))
        if not vin:
            raise HomeAssistantError("Vehicle VIN not available")
        return vin

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

            vehicle = coordinator.vehicle(vin) or {}
            car = vehicle.get("vehicle") or {}
            driver_is_right = str(car.get("rudder") or "1") == "2"
            if cmd.get("seat") == "driver":
                physical_key = "rightFront" if driver_is_right else "leftFront"
            else:
                physical_key = "leftFront" if driver_is_right else "rightFront"
            seat = {
                "operationMode": "1",
                "switchOrder": "1",
                "operationTime": str(operation_time),
                physical_key: str(level),
            }
            if level == 0:
                seat["operationTime"] = "0"
            instructions = {"0x0A": {"seat": seat}}
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
        try:
            await coordinator.async_save_card_settings(call.data["settings"])
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_handle_manage_profile(call: ServiceCall) -> None:
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
            hass.services.async_register(DOMAIN, command_key, async_handle_command)

    if not hass.services.has_service(DOMAIN, "set_seat_heating"):
        hass.services.async_register(
            DOMAIN,
            "set_seat_heating",
            async_handle_seat_heating,
            schema=vol.Schema({
                vol.Optional("entry_id"): str,
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
                vol.Required("action"): vol.In(["create", "update", "copy", "delete", "select"]),
                vol.Optional("profile_id"): str,
                vol.Optional("name"): str,
                vol.Optional("settings"): dict,
            }),
        )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
