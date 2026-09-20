"""Offline capture tests using Home Assistant stubs, no cloud requests."""

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "capture_test_package"
package = types.ModuleType(PACKAGE)
package.__path__ = []
sys.modules[PACKAGE] = package
ha = types.ModuleType("homeassistant")
ha.__path__ = []
ha_core = types.ModuleType("homeassistant.core")
ha_core.HomeAssistant = type("HomeAssistant", (), {})
ha_exceptions = types.ModuleType("homeassistant.exceptions")
ha_exceptions.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
sys.modules.update({"homeassistant": ha, "homeassistant.core": ha_core, "homeassistant.exceptions": ha_exceptions})
const = types.ModuleType(f"{PACKAGE}.const")
const.ENDPOINT_VEHICLE_BASICS_INFO = "/read-only/vehicleBasicsInfo"
const.ENDPOINT_LAST_STATUS = "/read-only/getLastStatus"
sys.modules[const.__name__] = const
coordinator_module = types.ModuleType(f"{PACKAGE}.coordinator")


class StubCoordinator:
    def __init__(self, hass, client, poll_interval, entry_id):
        self.hass, self.client, self.entry_id = hass, client, entry_id
        self.data = None

    async def _async_update_data(self):
        return {"vehicles": [{
            "vin": "TESTVIN1234567890",
            "state": {"engine_on": False, "engine_state": "0", "engine_state_source": "malicious-user-id-12345678901234567890"},
            "diagnostics": {
                "status_items": [{"code": "2016001", "value": "0"}, {"code": "2099999", "value": "TESTVIN1234567890"}],
                "status_top_level": {"command": "STATUS", "deviceId": "private", "acquisitionTime": 1789905071000},
            },
        }]}

    @property
    def vehicles(self):
        return (self.data or {}).get("vehicles", [])

    def resolve_vin(self, vin=None):
        return vin or "TESTVIN1234567890"


coordinator_module.GwmRuCoordinator = StubCoordinator
sys.modules[coordinator_module.__name__] = coordinator_module
spec = importlib.util.spec_from_file_location(f"{PACKAGE}.protocol_capture", ROOT / "custom_components/gwm_ru/protocol_capture.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class FakeHass:
    def __init__(self, root):
        self.config = types.SimpleNamespace(path=lambda name: str(root / name))

    async def async_add_executor_job(self, func, *args):
        return func(*args)


class FakeClient:
    def __init__(self):
        self.calls = []

    async def _request(self, method, path, **kwargs):
        self.calls.append((method, path))
        if method != "GET" or path not in {const.ENDPOINT_LAST_STATUS, const.ENDPOINT_VEHICLE_BASICS_INFO}:
            raise AssertionError("Capture must never send vehicle control commands")
        if path == const.ENDPOINT_VEHICLE_BASICS_INFO:
            return {"data": {"config": {"powerGear": "10", "quickSettings": "1,2,4,6", "vin": "PRIVATE"}}}
        return {"data": {
            "vehicleStatusInfo": {"Power": "1", "engineSts": "0", "ignitionStatus": "2", "VIN": "TESTVIN1234567890"},
            "hutSwitchOn": "1", "token": "PRIVATE",
        }}


class CaptureTests(unittest.TestCase):
    def test_safe_values_and_diff(self):
        self.assertEqual(module._safe_numeric("252.54"), "252.54")
        self.assertIsNone(module._safe_numeric("TESTVIN1234567890"))
        self.assertEqual(module._diff({"2016001": "0"}, {"2016001": "2"}),
                         [{"key": "2016001", "previous": "0", "value": "2"}])

    def test_power_candidates_are_allowlisted(self):
        actual = module._power_fields({"vehicleStatusInfo": {"Power": "1", "IGNITIONSTATUS": "2", "vin": "PRIVATE", "batteryKey": "12345"}, "hutSwitchOn": "0", "accessToken": "123"})
        self.assertEqual(actual, {"root.hutswitchon": "0", "vehicleStatusInfo.power": "1", "vehicleStatusInfo.ignitionstatus": "2"})
        self.assertEqual(module._power_fields({"vehicleStatusInfo": {"power": "VIN12345678901234"}}), {})
        self.assertEqual(module._power_fields({"vehicleStatusInfo": {"power": "0"}}), {"vehicleStatusInfo.power": "0"})

    def test_freshness_disallows_cached_diff(self):
        snapshot = lambda stamp: {"status_meta": {"acquisitionTime": stamp}}
        self.assertEqual(module._freshness(None, snapshot(1)), "baseline")
        self.assertEqual(module._freshness(snapshot(10), snapshot(10)), "cached_or_out_of_order")
        self.assertEqual(module._freshness(snapshot(10), snapshot(9)), "cached_or_out_of_order")
        self.assertEqual(module._freshness(snapshot(10), snapshot(11)), "fresh")
        self.assertEqual(module._freshness(snapshot(None), snapshot(11)), "unknown")

    def test_capture_opt_in_redacts_and_supports_markers(self):
        async def scenario(root):
            client = FakeClient()
            capture = module.GwmRuCaptureCoordinator(FakeHass(root), client, 300, "test_entry")
            self.assertFalse(capture.capture_enabled)
            await capture._async_update_data()
            self.assertEqual(list((root / ".storage").glob("*.jsonl")), [])
            self.assertEqual(client.calls, [])
            capture.capture_start()
            capture.data = await capture._async_update_data()
            await capture.capture_marker("IGN_ON")
            capture.data = await capture._async_update_data()
            capture.capture_stop()
            records = (await capture.async_capture_diagnostics())["vehicles"][0]["records"]
            self.assertEqual([item["type"] for item in records], ["refresh", "marker", "refresh"])
            self.assertTrue(records[0]["baseline"])
            self.assertEqual(records[0]["freshness"], "baseline")
            self.assertEqual(records[2]["freshness"], "cached_or_out_of_order")
            self.assertEqual(records[2]["changes"], {})
            self.assertEqual(records[0]["vehicle_basics"]["powerGear"], "10")
            self.assertEqual(records[0]["power_fields"]["vehicleStatusInfo.power"], "1")
            self.assertEqual(records[0]["power_fields"]["root.hutswitchon"], "1")
            self.assertIsNone(records[0]["signals"]["2099999"])
            self.assertEqual(set(client.calls), {("GET", const.ENDPOINT_LAST_STATUS), ("GET", const.ENDPOINT_VEHICLE_BASICS_INFO)})
            text = json.dumps(records)
            for secret in ("TESTVIN1234567890", "malicious-user-id", "PRIVATE", "accessToken"):
                self.assertNotIn(secret, text)
            await capture._async_update_data()
            exported = (await capture.async_capture_diagnostics())["vehicles"][0]
            self.assertEqual(exported["session_total"], 3)
        with tempfile.TemporaryDirectory() as root:
            asyncio.run(scenario(Path(root)))


if __name__ == "__main__":
    unittest.main()
