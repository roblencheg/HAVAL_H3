"""Data coordinator for GWM RU."""

from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import GwmRuApiClient
from .const import DOMAIN

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
        self.command_cooldown = 30
        self.security_pin: str | None = None
        self._last_command_time = 0.0
        self._command_status: dict[str, str] = {}
        self._command_diagnostics: dict[str, dict[str, Any]] = {}
        self._optimistic_engine: dict[str, dict[str, Any]] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        data = await self.client.async_update()
        now = time.time()
        for vehicle in data.get("vehicles", []):
            vin = vehicle.get("vin")
            if not vin:
                continue
            if vin in self._command_status:
                vehicle["command_status"] = self._command_status[vin]
                vehicle.setdefault("state", {})["command_status"] = self._command_status[vin]
            if vin in self._command_diagnostics:
                vehicle.setdefault("diagnostics", {})["last_command"] = self._command_diagnostics[vin]
            state = vehicle.setdefault("state", {})
            optimistic = self._optimistic_engine.get(vin)
            if optimistic and state.get("engine_on") is None:
                is_on = bool(optimistic.get("is_on"))
                expires_at = optimistic.get("expires_at")
                if is_on and expires_at and now >= float(expires_at):
                    is_on = False
                    self._optimistic_engine[vin] = {"is_on": False, "source": "remote_start_timeout"}
                state["engine_on"] = is_on
                state["engine_state"] = 1 if is_on else 0
                state["engine_state_source"] = "optimistic"
                state["vehicle_status"] = self._vehicle_status_from_state(state)
        primary_vin = data.get("vin")
        if primary_vin and primary_vin in self._command_status:
            data.setdefault("state", {})["command_status"] = self._command_status[primary_vin]
        if primary_vin:
            primary_vehicle = next((v for v in data.get("vehicles", []) if v.get("vin") == primary_vin), None)
            if primary_vehicle:
                data["state"] = primary_vehicle.get("state", data.get("state", {}))
        return data

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
        return (self.data or {}).get("vin")

    def entity_prefix(self, vin: str) -> str:
        """Keep legacy unique IDs for the primary vehicle, use VIN for additional vehicles."""
        return self.entry_id if vin == (self.data or {}).get("vin") else vin

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

    def _apply_optimistic_command_state(self, vin: str, instructions: dict) -> None:
        engine = instructions.get("0x03") if isinstance(instructions, dict) else None
        if not isinstance(engine, dict):
            return
        switch_order = str(engine.get("switchOrder", ""))
        if switch_order == "1":
            try:
                operation_minutes = max(1, int(engine.get("operationTime", 15)))
            except (TypeError, ValueError):
                operation_minutes = 15
            self._optimistic_engine[vin] = {
                "is_on": True,
                "expires_at": time.time() + operation_minutes * 60,
                "source": "remote_start",
            }
        elif switch_order == "2":
            self._optimistic_engine[vin] = {
                "is_on": False,
                "source": "remote_stop",
            }

    async def async_execute_t5(
        self,
        vin: str,
        instructions: dict,
        expected_remote_type: str,
        security_pin: str | None = None,
    ) -> dict[str, Any]:
        pin = security_pin or self.security_pin
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
        self._apply_optimistic_command_state(vin, instructions)
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

    def check_command_cooldown(self) -> None:
        now = time.time()
        elapsed = now - self._last_command_time
        if elapsed < self.command_cooldown:
            remaining = int(self.command_cooldown - elapsed)
            raise ValueError(f"Command cooldown active. Wait {remaining} seconds.")
        self._last_command_time = now
