"""The GWM RU integration."""

from __future__ import annotations

import logging
from pathlib import Path
import time
from uuid import uuid4

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GwmRuApiClient
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
from .services import register_services
from .trips import TripHistory
from .trips_ws import register as register_trips

_LOGGER = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent / "frontend"
FRONTEND_VERSION = "1.1.7"
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
    register_services(hass)
    return True




async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator is not None:
            await coordinator.async_shutdown()
    return unload_ok
