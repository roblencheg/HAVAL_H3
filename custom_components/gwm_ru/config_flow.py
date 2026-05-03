"""Config flow for GWM RU."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

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
    DEFAULT_COUNTRY,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_COMMAND_COOLDOWN,
    DEFAULT_ENABLE_REMOTE_CONTROLS,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .helpers import normalize_phone

CLEAR_SECURITY_PIN = "clear_security_pin"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PHONE): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): int,
        vol.Optional(CONF_SECURITY_PIN): selector.TextSelector(
            selector.TextSelectorConfig(type="password"),
        ),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate user credentials."""
    phone = normalize_phone(data[CONF_PHONE])
    device_id = uuid4().hex
    client = GwmRuApiClient(
        async_get_clientsession(hass),
        phone=phone,
        password=data[CONF_PASSWORD],
        device_id=device_id,
        country=DEFAULT_COUNTRY,
        country_code=DEFAULT_COUNTRY_CODE,
    )
    await client.async_login()
    return {"title": f"GWM RU {phone[-4:]}", "phone": phone, "device_id": device_id}


class GwmRuConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GWM RU."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except ConfigEntryAuthFailed:
                errors["base"] = "invalid_auth"
            except HomeAssistantError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["phone"])
                self._abort_if_unique_id_configured()
                options = {
                    CONF_POLL_INTERVAL: user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                }
                security_pin = user_input.get(CONF_SECURITY_PIN)
                if security_pin:
                    options[CONF_SECURITY_PIN] = security_pin
                return self.async_create_entry(
                    title=info["title"],
                    data={
                        CONF_PHONE: info["phone"],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_COUNTRY: DEFAULT_COUNTRY,
                        CONF_COUNTRY_CODE: DEFAULT_COUNTRY_CODE,
                        CONF_DEVICE_ID: info["device_id"],
                    },
                    options=options,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None):
        """Reauthenticate on token expiry."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                data = dict(entry.data)
                data[CONF_PASSWORD] = user_input[CONF_PASSWORD]
                info = await validate_input(self.hass, data)
                self.hass.config_entries.async_update_entry(entry, data=data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            except ConfigEntryAuthFailed:
                errors["base"] = "invalid_auth"
            except HomeAssistantError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PHONE, default=entry.data.get(CONF_PHONE, "")): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return GwmRuOptionsFlowHandler()


class GwmRuOptionsFlowHandler(config_entries.OptionsFlowWithReload):
    """Handle options for GWM RU."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage options."""
        if user_input is not None:
            options = dict(self.config_entry.options)
            options[CONF_POLL_INTERVAL] = user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            options[CONF_ENABLE_REMOTE_CONTROLS] = user_input.get(
                CONF_ENABLE_REMOTE_CONTROLS,
                DEFAULT_ENABLE_REMOTE_CONTROLS,
            )
            options[CONF_COMMAND_COOLDOWN] = user_input.get(
                CONF_COMMAND_COOLDOWN,
                DEFAULT_COMMAND_COOLDOWN,
            )

            new_pin = user_input.get(CONF_SECURITY_PIN)
            if new_pin:
                options[CONF_SECURITY_PIN] = new_pin

            if user_input.get(CLEAR_SECURITY_PIN):
                options.pop(CONF_SECURITY_PIN, None)

            return self.async_create_entry(title="", data=options)

        poll_interval = self.config_entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        enable_remote = self.config_entry.options.get(
            CONF_ENABLE_REMOTE_CONTROLS, DEFAULT_ENABLE_REMOTE_CONTROLS
        )
        command_cooldown = self.config_entry.options.get(
            CONF_COMMAND_COOLDOWN, DEFAULT_COMMAND_COOLDOWN
        )
        has_pin = bool(self.config_entry.options.get(CONF_SECURITY_PIN))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_POLL_INTERVAL, default=poll_interval): int,
                    vol.Optional(CONF_ENABLE_REMOTE_CONTROLS, default=enable_remote): bool,
                    vol.Optional(CONF_COMMAND_COOLDOWN, default=command_cooldown): int,
                    vol.Optional(CONF_SECURITY_PIN): selector.TextSelector(
                        selector.TextSelectorConfig(type="password"),
                    ),
                    vol.Optional(CLEAR_SECURITY_PIN, default=False): bool,
                }
            ),
            data_descriptions={
                CONF_SECURITY_PIN: "PIN-код из личного кабинета GWM, 6 цифр",
                CONF_ENABLE_REMOTE_CONTROLS: "Вы самостоятельно отвечаете за безопасность и контроль доступа к Home Assistant",
            },
            description_placeholders={
                "pin_status": "сохранён" if has_pin else "не задан",
            },
        )
