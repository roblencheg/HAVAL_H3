"""Data coordinator for GWM RU."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GwmRuApiClient, GwmRuApiError
from .card_settings import validate_settings
from .const import DOMAIN, ENDPOINT_REMOTE_HISTORY
from .preparation_profiles import change_profiles, initial_profiles, profile_settings, validate_profiles

_LOGGER = logging.getLogger(__name__)


class GwmRuCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinates GWM RU API polling."""

    def __init__(self, hass: HomeAssistant, client: GwmRuApiClient, poll_interval: int, entry_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self.client = client
        self.entry_id = entry_id
        self.enable_remote_controls = False
        self.command_cooldown = 5
        self.security_pin: str | None = None
        self._last_command_time = 0.0
        self._command_status: dict[str, str] = {}
        self._command_diagnostics: dict[str, dict[str, Any]] = {}
        self._confirmed_engine_state: dict[str, dict[str, Any]] = {}
        self.last_successful_update: datetime | None = None
        self.card_settings: dict[str, Any] = {}
        self.preparation_profiles: list[dict[str, Any]] = []
        self._card_settings_store = Store(hass, 1, f"{DOMAIN}_{entry_id}_card_settings")
        self._profiles_store = Store(hass, 1, f"{DOMAIN}_{entry_id}_preparation_profiles")
        self._card_settings_lock = asyncio.Lock()
        self._profiles_lock = asyncio.Lock()
        self._comfort_task: asyncio.Task | None = None
        self.trip_histories: dict[str, Any] = {}
        self._primary_vin: str | None = None
        self._listener_unsubscribers: list[Any] = []
        self._command_tasks: set[asyncio.Task] = set()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.client.async_update()
        except GwmRuApiError as err:
            raise UpdateFailed(str(err)) from err
        if self._primary_vin is None:
            self._primary_vin = data.get("vin")
        now = time.time()
        for vehicle in data.get("vehicles", []):
            vin = vehicle.get("vin")
            if not vin:
                continue

            await self._async_attach_remote_history(vehicle)

            if vin in self._command_status:
                vehicle["command_status"] = self._command_status[vin]
                vehicle.setdefault("state", {})["command_status"] = self._command_status[vin]
            if vin in self._command_diagnostics:
                vehicle.setdefault("diagnostics", {})["last_command"] = self._command_diagnostics[vin]
            state = vehicle.setdefault("state", {})
            confirmed = self._confirmed_engine_state.get(vin)
            if confirmed and state.get("engine_on") is None:
                is_on = bool(confirmed.get("is_on"))
                expires_at = confirmed.get("expires_at")
                source = str(confirmed.get("source") or "remote_command_result")
                if is_on and expires_at and now >= float(expires_at):
                    is_on = False
                    source = "remote_start_timeout"
                    self._confirmed_engine_state[vin] = {
                        "is_on": False,
                        "source": source,
                    }
                state["engine_on"] = is_on
                state["engine_state"] = 1 if is_on else 0
                state["engine_state_source"] = source
                state["vehicle_status"] = self._vehicle_status_from_state(state)
        primary_vin = data.get("vin")
        if primary_vin and primary_vin in self._command_status:
            data.setdefault("state", {})["command_status"] = self._command_status[primary_vin]
        if primary_vin:
            primary_vehicle = next((v for v in data.get("vehicles", []) if v.get("vin") == primary_vin), None)
            if primary_vehicle:
                data["state"] = primary_vehicle.get("state", data.get("state", {}))
        self.last_successful_update = datetime.now(timezone.utc)
        for vehicle in data.get("vehicles", []):
            vin = vehicle.get("vin")
            history = self.trip_histories.get(vin) if vin else None
            if history is None:
                continue
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
                _LOGGER.debug("Could not append local GWM trip point for %s", vin, exc_info=True)
        return data

    async def _async_attach_remote_history(self, vehicle: dict[str, Any]) -> None:
        """Attach recent remote-control history when the VIN supports it."""
        capabilities = vehicle.get("capabilities") or {}
        if not capabilities.get("remote_history"):
            return

        vin = vehicle.get("vin")
        if not vin:
            return
        car = vehicle.get("vehicle") or {}
        vehicle_id = car.get("vehicleId")
        body: dict[str, Any] = {
            "vin": str(vin),
            # 1 = all commands, including commands sent by the official app.
            "type": 1,
            "pageNum": 1,
            "pageSize": 20,
        }
        if vehicle_id is not None:
            body["vehicleId"] = vehicle_id

        try:
            payload = await self.client._request(
                "POST",
                ENDPOINT_REMOTE_HISTORY,
                body=body,
                vin_header=str(vin),
            )
            history_data = payload.get("data") or {}
            history_list = history_data.get("list") if isinstance(history_data, dict) else None
            vehicle["remote_history"] = history_list if isinstance(history_list, list) else []
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            vehicle["remote_history"] = []
            vehicle.setdefault("diagnostics", {})["remote_history_error"] = str(err)
            _LOGGER.debug("Could not fetch remote history for %s: %s", vin, err)

    @staticmethod
    def _vehicle_status_from_state(state: dict[str, Any]) -> str:
        if state.get("engine_on") is True:
            return "Запущена"
        openings = (
            state.get("door_fl_open"),
            state.get("door_fr_open"),
            state.get("door_rl_open"),
            state.get("door_rr_open"),
            state.get("trunk_open"),
        )
        if state.get("unlocked") is True or any(value is True for value in openings):
            return "Открыта"
        if state.get("locked") is True:
            return "На охране"
        return "Неизвестно"

    @property
    def vehicles(self) -> list[dict[str, Any]]:
        return list((self.data or {}).get("vehicles", []))

    def vehicle(self, vin: str) -> dict[str, Any] | None:
        return next((vehicle for vehicle in self.vehicles if vehicle.get("vin") == vin), None)

    def resolve_vin(self, requested_vin: str | None = None) -> str | None:
        if requested_vin:
            for vehicle in self.vehicles:
                if requested_vin in {vehicle.get("vin"), vehicle.get("display_vin")}:
                    return vehicle.get("vin")
            return None
        return (self.data or {}).get("vin")

    def entity_prefix(self, vin: str) -> str:
        """Keep legacy unique IDs for the primary vehicle, use VIN for additional vehicles."""
        return self.entry_id if vin == self._primary_vin else vin

    def set_command_status(self, vin: str, status: str) -> None:
        self._command_status[vin] = status
        if not self.data:
            return
        for vehicle in self.data.get("vehicles", []):
            if vehicle.get("vin") == vin:
                vehicle["command_status"] = status
                vehicle.setdefault("state", {})["command_status"] = status
        if self.data.get("vin") == vin:
            self.data.setdefault("state", {})["command_status"] = status
        self.async_update_listeners()

    def _set_command_diagnostics(self, vin: str, data: dict[str, Any]) -> None:
        self._command_diagnostics[vin] = data
        if not self.data:
            return
        for vehicle in self.data.get("vehicles", []):
            if vehicle.get("vin") == vin:
                vehicle.setdefault("diagnostics", {})["last_command"] = data
        self.async_update_listeners()

    def _apply_confirmed_command_state(self, vin: str, instructions: dict) -> None:
        """Apply state inferred from a command only after GWM reports success."""
        engine = instructions.get("0x03") if isinstance(instructions, dict) else None
        if not isinstance(engine, dict):
            return
        switch_order = str(engine.get("switchOrder", ""))
        if switch_order == "1":
            try:
                operation_minutes = max(1, int(engine.get("operationTime", 15)))
            except (TypeError, ValueError):
                operation_minutes = 15
            self._confirmed_engine_state[vin] = {
                "is_on": True,
                "expires_at": time.time() + operation_minutes * 60,
                "source": "remote_command_result",
            }
        elif switch_order == "2":
            self._confirmed_engine_state[vin] = {
                "is_on": False,
                "source": "remote_command_result",
            }

    async def async_execute_t5(
        self,
        vin: str,
        instructions: dict,
        expected_remote_type: str,
        security_pin: str | None = None,
    ) -> dict[str, Any]:
        task = asyncio.current_task()
        self._command_tasks.add(task)
        try:
            return await self._async_execute_t5(vin, instructions, expected_remote_type, security_pin)
        finally:
            self._command_tasks.discard(task)

    async def _async_execute_t5(
        self,
        vin: str,
        instructions: dict,
        expected_remote_type: str,
        security_pin: str | None = None,
    ) -> dict[str, Any]:
        pin = security_pin or self.security_pin
        if not self.enable_remote_controls or not pin:
            raise HomeAssistantError("Remote controls and security PIN are required")
        if self.vehicle(vin) is None:
            raise HomeAssistantError("Vehicle VIN not available")
        if self.command_in_progress and self._comfort_task is not asyncio.current_task():
            raise HomeAssistantError("Другая команда уже выполняется")
        try:
            self.check_command_cooldown()
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        self.set_command_status(vin, "Выполняется")
        self._set_command_diagnostics(
            vin,
            {
                "remote_type": expected_remote_type,
                "status": "Выполняется",
                "started_at": int(time.time()),
            },
        )
        try:
            result = await self.client.async_send_t5_command(
                vin,
                instructions,
                expected_remote_type,
                security_pin=pin,
            )
        except asyncio.CancelledError:
            self.set_command_status(vin, "Отменено")
            raise
        except Exception as err:
            self.set_command_status(vin, "Ошибка")
            self._set_command_diagnostics(
                vin,
                {
                    "remote_type": expected_remote_type,
                    "status": "Ошибка",
                    "error": str(err),
                    "finished_at": int(time.time()),
                },
            )
            raise
        self._apply_confirmed_command_state(vin, instructions)
        self.set_command_status(vin, "Успешно")
        self._set_command_diagnostics(
            vin,
            {
                "remote_type": expected_remote_type,
                "status": "Успешно",
                "result_code": result.get("resultCode"),
                "result_msg": result.get("resultMsg"),
                "returned_remote_type": result.get("remoteType"),
                "finished_at": int(time.time()),
            },
        )
        await self.async_request_refresh()
        return result

    @property
    def command_in_progress(self) -> bool:
        return self._comfort_task is not None or any(
            value == "Выполняется" for value in self._command_status.values()
        )

    async def async_load_card_settings(self) -> None:
        saved = await self._card_settings_store.async_load()
        try:
            self.card_settings = validate_settings(saved or {})
        except ValueError:
            _LOGGER.warning("Ignoring invalid saved GWM card settings")
            self.card_settings = {}

    async def async_save_card_settings(self, patch: dict[str, Any]) -> None:
        try:
            patch = validate_settings(patch)
        except ValueError as err:
            raise ValueError(str(err)) from err
        async with self._card_settings_lock:
            settings = {**self.card_settings, **patch}
            await self._card_settings_store.async_save(settings)
            self.card_settings = settings
            self.async_update_listeners()

    async def async_load_profiles(self) -> None:
        saved = await self._profiles_store.async_load()
        try:
            self.preparation_profiles = (
                validate_profiles(saved) if saved is not None else initial_profiles()
            )
        except ValueError:
            _LOGGER.warning("Ignoring invalid saved GWM preparation profiles")
            self.preparation_profiles = initial_profiles()
        if saved is None:
            await self._profiles_store.async_save(self.preparation_profiles)

    async def async_manage_profile(
        self,
        action: str,
        *,
        profile_id: str = "",
        name: str = "",
        settings: dict[str, Any] | None = None,
    ) -> None:
        async with self._profiles_lock:
            if action == "select":
                profile = next((p for p in self.preparation_profiles if p["id"] == profile_id), None)
                if profile_id and profile is None:
                    raise ValueError("Профиль не найден")
                patch = {**profile["settings"], "comfort_start": True} if profile else {}
                await self.async_save_card_settings({**patch, "selected_profile": profile_id})
                return
            profiles = change_profiles(
                self.preparation_profiles,
                action,
                profile_id=profile_id,
                name=name,
                settings=settings,
            )
            await self._profiles_store.async_save(profiles)
            self.preparation_profiles = profiles
            if action in ("create", "copy"):
                profile = profiles[-1]
                await self.async_save_card_settings(
                    {**profile["settings"], "selected_profile": profile["id"], "comfort_start": True}
                )
            elif action == "delete" and self.card_settings.get("selected_profile") == profile_id:
                await self.async_save_card_settings({"selected_profile": ""})
            self.async_update_listeners()

    async def async_set_seat_heating(
        self,
        vin: str,
        driver: int | None,
        passenger: int | None,
        operation_time: int = 5,
        security_pin: str | None = None,
    ) -> dict[str, Any] | None:
        if driver is None and passenger is None:
            return None
        operation_time = min(10, max(1, int(operation_time)))
        vehicle = self.vehicle(vin) or {}
        car = vehicle.get("vehicle") or {}
        driver_is_right = str(car.get("rudder") or "1") == "2"
        seat: dict[str, Any] = {
            "operationMode": "1",
            "switchOrder": "1",
            "operationTime": str(operation_time),
        }
        if driver is not None:
            level = min(3, max(0, int(driver)))
            seat["rightFront" if driver_is_right else "leftFront"] = str(level)
        if passenger is not None:
            level = min(3, max(0, int(passenger)))
            seat["leftFront" if driver_is_right else "rightFront"] = str(level)
        if all(value == 0 for value in (driver, passenger) if value is not None):
            seat["operationTime"] = "0"
        return await self.async_execute_t5(
            vin,
            {"0x0A": {"seat": seat}},
            "0x0A",
            security_pin or self.security_pin,
        )

    async def _async_comfort_pause(self) -> None:
        await asyncio.sleep(max(0, float(self.command_cooldown)) + 0.1)

    async def async_start_with_comfort(
        self,
        vin: str,
        *,
        temperature: int,
        climate_time: int,
        engine_time: int,
        driver: int | None,
        passenger: int | None,
        seat_time: int,
        climate_enabled: bool = True,
    ) -> None:
        if self.command_in_progress:
            raise ValueError("Другая команда уже выполняется")
        self._comfort_task = asyncio.current_task()
        self.async_update_listeners()
        try:
            await self.async_execute_t5(
                vin,
                {"0x03": {"operationTime": str(engine_time), "switchOrder": "1"}},
                "0x03",
                self.security_pin,
            )
            if climate_enabled:
                await self._async_comfort_pause()
                await self.async_execute_t5(
                    vin,
                    {"0x04": {"airConditioner": {
                        "switchOrder": "1",
                        "temperature": str(temperature),
                        "operationTime": str(climate_time),
                    }}},
                    "0x04",
                    self.security_pin,
                )
            if driver is not None or passenger is not None:
                await self._async_comfort_pause()
                await self.async_set_seat_heating(vin, driver, passenger, seat_time)
        finally:
            self._comfort_task = None
            self.async_update_listeners()

    async def async_start_selected_profile(self, vin: str, profile_id: str | None = None) -> None:
        selected = self.card_settings.get("selected_profile") if profile_id is None else profile_id
        profile = next((item for item in self.preparation_profiles if item["id"] == selected), None)
        if profile is None:
            raise ValueError("Выберите профиль подготовки")
        settings = profile_settings(profile["settings"])
        await self.async_start_with_comfort(
            vin,
            temperature=settings["temperature"],
            climate_time=settings["climate_time"],
            engine_time=settings["engine_time"],
            climate_enabled=settings["climate_enabled"],
            driver=settings["driver"] if settings["driver_enabled"] else 0,
            passenger=settings["passenger"] if settings["passenger_enabled"] else 0,
            seat_time=settings["seat_time"],
        )

    def check_command_cooldown(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_command_time
        if elapsed < self.command_cooldown:
            remaining = max(1, int(self.command_cooldown - elapsed + 0.999))
            raise ValueError(f"Command cooldown active. Wait {remaining} seconds.")
        self._last_command_time = now

    async def async_shutdown(self) -> None:
        """Release discovery listeners and cancel an unfinished preparation."""
        for unsubscribe in self._listener_unsubscribers:
            unsubscribe()
        self._listener_unsubscribers.clear()
        tasks = self._command_tasks | ({self._comfort_task} if self._comfort_task else set())
        tasks.discard(asyncio.current_task())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
