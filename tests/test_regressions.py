"""Offline regression tests with HA boundaries stubbed; no car commands are sent."""
from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch


def module(name, **attributes):
    result = ModuleType(name)
    result.__dict__.update(attributes)
    sys.modules[name] = result
    return result


class HomeAssistantError(Exception):
    pass


class ConfigEntryAuthFailed(HomeAssistantError):
    pass


class UpdateFailed(HomeAssistantError):
    pass


class CoordinatorBoundary:
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, *args, **kwargs):
        self.hass = hass
        self.data = None
        self.async_update_listeners = Mock()
        self.async_request_refresh = AsyncMock()


# Import production modules without executing integration setup. Only the HA
# service registry/coordinator/storage boundaries are replaced, not GWM logic.
root = Path(__file__).resolve().parents[1]
module("homeassistant")
module("homeassistant.core", HomeAssistant=object, ServiceCall=object)
module("homeassistant.exceptions", HomeAssistantError=HomeAssistantError,
       ConfigEntryAuthFailed=ConfigEntryAuthFailed)
module("homeassistant.helpers")
module("homeassistant.helpers.storage", Store=lambda *args: SimpleNamespace(
    async_load=AsyncMock(return_value=None), async_save=AsyncMock()))
module("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=CoordinatorBoundary,
       UpdateFailed=UpdateFailed)
device_registry = module("homeassistant.helpers.device_registry", async_get=lambda hass: hass.devices)
package = module("custom_components.gwm_ru")
package.__path__ = [str(root / "custom_components/gwm_ru")]
api = importlib.import_module("custom_components.gwm_ru.api")
coordinator_module = importlib.import_module("custom_components.gwm_ru.coordinator")
services = importlib.import_module("custom_components.gwm_ru.services")
trips = importlib.import_module("custom_components.gwm_ru.trips")


def coordinator(entry_id="first", vin="VIN-A"):
    client = SimpleNamespace(async_send_t5_command=AsyncMock(return_value={"resultCode": "0"}))
    result = coordinator_module.GwmRuCoordinator(SimpleNamespace(), client, 300, entry_id)
    result.data = {"vin": vin, "vehicles": [{"vin": vin, "display_vin": "display-" + vin,
                                            "state": {}, "vehicle": {}}]}
    result._primary_vin = vin
    result.security_pin = "test-pin"
    result.enable_remote_controls = True
    result.command_cooldown = 0
    return result


class ServiceRegistry:
    def __init__(self):
        self.handlers = {}
        self.schemas = {}

    def has_service(self, domain, name):
        return name in self.handlers

    def async_register(self, domain, name, handler, schema=None):
        self.handlers[name] = handler
        self.schemas[name] = schema

    async def call(self, name, **data):
        if self.schemas[name]:
            data = self.schemas[name](data)
        await self.handlers[name](SimpleNamespace(service=name, data=data))


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.first, self.second = coordinator(), coordinator("second", "VIN-B")
        self.hass = SimpleNamespace(data={"gwm_ru": {"first": self.first, "second": self.second,
                                                     "_frontend_registered": True}},
                                    services=ServiceRegistry(), devices=SimpleNamespace(async_get=Mock()))
        services.register_services(self.hass)

    async def test_second_account_command(self):
        await self.hass.services.call("engine_start", entry_id="second")
        self.first.client.async_send_t5_command.assert_not_awaited()
        self.assertEqual(self.second.client.async_send_t5_command.call_args.args[0], "VIN-B")

    async def test_handler_uses_reloaded_account(self):
        replacement = coordinator("first", "VIN-C")
        self.hass.data["gwm_ru"]["first"] = replacement
        await self.hass.services.call("lock_vehicle", entry_id="first")
        self.first.client.async_send_t5_command.assert_not_awaited()
        self.assertEqual(replacement.client.async_send_t5_command.call_args.args[0], "VIN-C")

    async def test_unknown_vin_never_targets_primary(self):
        with self.assertRaises(HomeAssistantError):
            await self.hass.services.call("engine_start", vin="missing")
        self.assertIsNone(self.first.resolve_vin("missing"))
        self.first.client.async_send_t5_command.assert_not_awaited()

    async def test_ambiguous_account_is_rejected(self):
        with self.assertRaises(HomeAssistantError):
            await self.hass.services.call("engine_start")

    async def test_device_targets_second_vehicle_in_same_account(self):
        self.first.data["vehicles"].append({"vin": "VIN-C", "vehicle": {}, "state": {}})
        self.hass.devices.async_get.return_value = SimpleNamespace(identifiers={("gwm_ru", "VIN-C")})
        await self.hass.services.call("engine_start", entry_id="first", device_id="device-C")
        self.assertEqual(self.first.client.async_send_t5_command.call_args.args[0], "VIN-C")

    async def test_mismatched_device_and_vin_rejected(self):
        self.first.data["vehicles"].append({"vin": "VIN-C", "vehicle": {}, "state": {}})
        self.hass.devices.async_get.return_value = SimpleNamespace(identifiers={("gwm_ru", "VIN-C")})
        with self.assertRaises(HomeAssistantError):
            await self.hass.services.call("engine_start", entry_id="first", device_id="device-C", vin="VIN-A")

    async def test_settings_saved_to_selected_account(self):
        await self.hass.services.call("save_card_settings", entry_id="second", settings={"engine_time": 10})
        self.assertEqual(self.second.card_settings["engine_time"], 10)
        self.assertEqual(self.first.card_settings, {})

    async def test_seat_off_affects_only_requested_seat(self):
        await self.hass.services.call("set_driver_seat_heat", entry_id="first", level=0)
        seat = self.first.client.async_send_t5_command.call_args.args[1]["0x0A"]["seat"]
        self.assertEqual(seat["operationTime"], "0")
        self.assertEqual(seat["leftFront"], "0")
        self.assertNotIn("rightFront", seat)

    async def test_right_hand_drive_seat_mapping(self):
        self.first.data["vehicles"][0]["vehicle"]["rudder"] = "2"
        await self.hass.services.call("set_driver_seat_heat", entry_id="first", level=3)
        seat = self.first.client.async_send_t5_command.call_args.args[1]["0x0A"]["seat"]
        self.assertEqual(seat["rightFront"], "3")
        self.assertNotIn("leftFront", seat)


class CommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_controls_cannot_bypass_service(self):
        item = coordinator()
        item.enable_remote_controls = False
        with self.assertRaises(HomeAssistantError):
            await item.async_execute_t5("VIN-A", {}, "0x04")
        item.client.async_send_t5_command.assert_not_awaited()

    async def test_cooldown_also_applies_to_direct_climate_commands(self):
        item = coordinator()
        item.command_cooldown = 5
        await item.async_execute_t5("VIN-A", {}, "0x04")
        with self.assertRaisesRegex(HomeAssistantError, "cooldown"):
            await item.async_execute_t5("VIN-A", {}, "0x04")
        self.assertEqual(item.client.async_send_t5_command.await_count, 1)

    async def test_concurrent_command_is_rejected(self):
        item = coordinator()
        started, finish = asyncio.Event(), asyncio.Event()
        async def send(*args, **kwargs):
            started.set()
            await finish.wait()
            return {"resultCode": "0"}
        item.client.async_send_t5_command.side_effect = send
        task = asyncio.create_task(item.async_execute_t5("VIN-A", {}, "0x04"))
        await started.wait()
        with self.assertRaisesRegex(HomeAssistantError, "уже выполняется"):
            await item.async_execute_t5("VIN-A", {}, "0x03")
        finish.set()
        await task

    async def test_comfort_sequence_can_run_its_own_commands(self):
        item = coordinator()
        item._async_comfort_pause = AsyncMock()
        await item.async_start_with_comfort("VIN-A", temperature=22, climate_time=15,
                                          engine_time=15, driver=3, passenger=None, seat_time=5)
        self.assertEqual(item.client.async_send_t5_command.await_count, 3)
        self.assertFalse(item.command_in_progress)

    async def test_shutdown_cancels_commands_and_releases_listeners(self):
        item = coordinator()
        started = asyncio.Event()
        async def send(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()
        item.client.async_send_t5_command.side_effect = send
        unsubscribe = Mock()
        item._listener_unsubscribers.append(unsubscribe)
        task = asyncio.create_task(item.async_execute_t5("VIN-A", {}, "0x03"))
        await started.wait()
        await item.async_shutdown()
        self.assertTrue(task.cancelled())
        self.assertFalse(item.command_in_progress)
        self.assertEqual(item._command_tasks, set())
        unsubscribe.assert_called_once()

    async def test_primary_identity_survives_partial_refresh(self):
        item = coordinator()
        item.data = {"vin": "VIN-B", "vehicles": [{"vin": "VIN-B"}]}
        self.assertEqual(item.entity_prefix("VIN-A"), "first")
        self.assertEqual(item.entity_prefix("VIN-B"), "VIN-B")

    async def test_poll_error_becomes_update_failed(self):
        item = coordinator()
        item.client.async_update = AsyncMock(side_effect=api.GwmRuApiError("offline"))
        with self.assertRaises(UpdateFailed):
            await item._async_update_data()


class ApiTests(unittest.IsolatedAsyncioTestCase):
    def client(self, session=None):
        return api.GwmRuApiClient(session, "79999999999", "test-password", "test-device", "RU", "+7")

    async def test_primary_not_reassigned_after_partial_failure(self):
        item = self.client()
        item._access_token = "test"
        item._get_vehicles = AsyncMock(return_value=[{"vin": "VIN-A"}, {"vin": "VIN-B"}])
        async def snapshot(car):
            if car["vin"] == "VIN-A":
                raise api.GwmRuApiError("offline")
            return {"vin": "VIN-B", "vehicle": {}, "vehicle_name": "B", "state": {}, "location": {}}
        item._build_vehicle_snapshot = snapshot
        result = await item.async_update()
        self.assertEqual(result["vin"], "VIN-A")
        self.assertEqual([v["vin"] for v in result["vehicles"]], ["VIN-B"])

    async def test_auth_failure_is_not_hidden_as_partial_failure(self):
        item = self.client()
        item._access_token = "test"
        item._get_vehicles = AsyncMock(return_value=[{"vin": "VIN-A"}])
        item._build_vehicle_snapshot = AsyncMock(side_effect=ConfigEntryAuthFailed("expired"))
        with self.assertRaises(ConfigEntryAuthFailed):
            await item.async_update()

    async def test_tbox_failure_keeps_odometer(self):
        item = self.client()
        item._get_last_status = AsyncMock(return_value={"items": [{"code": "2103010", "value": "12345"}]})
        item._find_status = AsyncMock(side_effect=api.GwmRuApiError("offline"))
        item._get_vehicle_capabilities = AsyncMock(return_value=[])
        result = await item._build_vehicle_snapshot({"vin": "VIN-A", "imsi": "test", "vehicleId": 1})
        self.assertEqual(result["state"]["mileage_total"], 12345)

    async def test_capabilities_cached_per_vin_and_role(self):
        item = self.client()
        item._request = AsyncMock(return_value={"data": []})
        await item._get_vehicle_capabilities("VIN-A", 1)
        await item._get_vehicle_capabilities("VIN-A", 1)
        await item._get_vehicle_capabilities("VIN-B", 1)
        await item._get_vehicle_capabilities("VIN-A", 2)
        self.assertEqual(item._request.await_count, 3)

    async def test_terminal_command_failure_returns_immediately(self):
        item = self.client()
        item._request = AsyncMock(return_value={"data": [None, {"remoteType": "0x03", "resultCode": 42, "resultMsg": "rejected"}]})
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            with self.assertRaisesRegex(HomeAssistantError, "rejected"):
                await item.async_poll_t5_result("VIN-A", "test-seq", "0x03")
        self.assertEqual(item._request.await_count, 1)

    async def test_pending_then_success_and_other_command_ignored(self):
        item = self.client()
        item._request = AsyncMock(side_effect=[
            {"data": [{"remoteType": "0x03", "resultCode": "1000"}]},
            {"data": [{"remoteType": "0x05", "resultCode": "0"}, {"remoteType": "0x03", "resultCode": "6"}]},
        ])
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            result = await item.async_poll_t5_result("VIN-A", "test-seq", "0x03")
        self.assertEqual(result["resultCode"], "6")

    async def test_transport_timeout_wrapped(self):
        session = SimpleNamespace(request=Mock(side_effect=TimeoutError()))
        with self.assertRaises(api.GwmRuApiError):
            await self.client(session)._request("GET", "/test")

    async def test_non_object_json_rejected(self):
        response = SimpleNamespace(text=AsyncMock(return_value="[]"), raise_for_status=Mock())
        class RequestContext:
            async def __aenter__(self):
                return response
            async def __aexit__(self, *args):
                return False
        session = SimpleNamespace(request=Mock(return_value=RequestContext()))
        with self.assertRaisesRegex(api.GwmRuApiError, "structure"):
            await self.client(session)._request("GET", "/test")


class TripStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_connection_closed_after_query_error(self):
        with tempfile.TemporaryDirectory() as directory:
            hass = SimpleNamespace(config=SimpleNamespace(path=lambda *parts: str(Path(directory, *parts))))
            history = trips.TripHistory(hass, "test")
            db = Mock()
            db.__enter__ = Mock(return_value=db)
            db.__exit__ = Mock(return_value=False)
            db.execute.side_effect = RuntimeError("read failed")
            with patch.object(history, "_connect", return_value=db):
                with self.assertRaises(RuntimeError):
                    history._query("2026-10-01", "2026-10-01", "UTC")
            db.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
