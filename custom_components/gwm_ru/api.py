"""API client for the unofficial GWM RU cloud."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import socket
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlencode, urlparse

from aiohttp import ClientError, ClientSession
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError

from .capabilities import build_vehicle_capabilities
from .const import APP_ID, APP_KEY, APP_SEC, APP_VERSION, AUTH_PREFIX, BASE_URL, BRAND, COUNTRY, ENDPOINT_CHECK_SECURITY_PASSWORD, ENDPOINT_FIND_STATUS, ENDPOINT_LAST_STATUS, ENDPOINT_LOGIN, ENDPOINT_T5_CTRL_RESULT, ENDPOINT_T5_SEND_CMD, ENDPOINT_VEHICLE_CAPABILITIES, ENDPOINT_VEHICLES, ENTERPRISE_ID, LANGUAGE, REGION_CODE, SYSTEM_TYPE, TERMINAL
from .helpers import build_state, calculate_fuel_percent, normalize_phone, redact_vehicle

_LOGGER = logging.getLogger(__name__)

# Known cloud auth codes. Russian backends also return localized expiry text with
# codes outside this set; `_is_auth_error` matches those by description.
_AUTH_ERROR_CODES = frozenset({
    "401",
    "401000",
    "401001",
    "401002",
    "308001",
    "308002",
    "308003",
    "308004",
})
_AUTH_DESCRIPTION_MARKERS = (
    "токен входа",
    "срок действия токена",
    "token expired",
    "access token",
    "login expired",
    "unauthorized",
    "令牌已过期",
    "登录已过期",
    "登录令牌",
)


def _is_auth_error(code: str, description: str) -> bool:
    """Return True when the cloud response means the access token is unusable."""
    if code in _AUTH_ERROR_CODES:
        return True
    # GWM uses 401xxx / 308xxx families for session problems across regions.
    if code.startswith(("401", "308")):
        return True
    lowered = description.casefold()
    return any(marker in lowered for marker in _AUTH_DESCRIPTION_MARKERS)


class GwmRuApiError(HomeAssistantError):
    """Raised when the GWM RU API returns an error."""


class GwmRuApiClient:
    """Small async client for the unofficial GWM RU API."""

    def __init__(self, session: ClientSession, phone: str, password: str, device_id: str, country: str, country_code: str) -> None:
        self._session = session
        self._phone = normalize_phone(phone)
        self._password = password
        self._device_id = device_id
        self._country = country
        self._country_code = country_code
        self._access_token: str | None = None
        self._login_lock = asyncio.Lock()
        self._primary_vin: str | None = None
        self._capability_cache: dict[tuple[str, int], tuple[float, Any]] = {}
        self._local_ip = local_ip()

    async def async_login(self) -> None:
        async with self._login_lock:
            if self._access_token:
                return
            await self._async_login_unlocked()

    async def _async_login_unlocked(self) -> None:
        """Perform login. Caller must hold `_login_lock`."""
        body = {"account": self._phone, "password": self._password, "agreement": [1, 2, 18, 19], "smsCode": None, "msgType": None, "model": "Home Assistant", "type": 1, "deviceId": self._device_id, "appType": 0, "pushToken": "", "country": self._country, "countryCode": self._country_code, "isEncrypt": False}
        payload = await self._request("POST", ENDPOINT_LOGIN, body=body, with_token=False)
        data = payload.get("data") or {}
        token = data.get("accessToken")
        if not token:
            raise ConfigEntryAuthFailed("GWM RU login did not return accessToken")
        self._access_token = str(token)

    async def _async_relogin_after_auth_error(self, stale_token: str | None) -> None:
        """Replace an expired token once; skip if another coroutine already did."""
        async with self._login_lock:
            if self._access_token and self._access_token != stale_token:
                return
            self._access_token = None
            await self._async_login_unlocked()

    async def async_update(self) -> dict[str, Any]:
        """Fetch all vehicles and keep first-vehicle fields for backward compatibility."""
        await self._ensure_login()
        cars = await self._get_vehicles()
        if not cars:
            raise GwmRuApiError("No vehicles returned by GWM RU account")
        if self._primary_vin is None:
            self._primary_vin = str(cars[0].get("vin") or "") or None
        vehicles: list[dict[str, Any]] = []
        for car in cars:
            try:
                vehicles.append(await self._build_vehicle_snapshot(car))
            except ConfigEntryAuthFailed:
                raise
            except Exception as err:
                _LOGGER.warning("Failed to refresh one GWM vehicle: %s", err)
        if not vehicles:
            raise GwmRuApiError("No GWM vehicles could be refreshed")
        primary = next((v for v in vehicles if v["vin"] == self._primary_vin), None)
        if primary is None:
            # Keep legacy entity IDs assigned to their original vehicle even
            # when only another vehicle could be refreshed this time.
            primary = {"vin": self._primary_vin, "vehicle": {},
                       "vehicle_name": "GWM vehicle", "state": {}, "location": {}}
        return {"vin": primary["vin"], "vehicle": primary["vehicle"], "vehicle_name": primary["vehicle_name"], "state": primary["state"], "location": primary["location"], "vehicles": vehicles}

    async def _build_vehicle_snapshot(self, car: dict[str, Any]) -> dict[str, Any]:
        vin = car.get("vin")
        imsi = car.get("imsi")
        vehicle_id = car.get("vehicleId")
        if not vin:
            raise GwmRuApiError("Vehicle does not contain VIN")

        status = await self._get_last_status(str(vin))
        tbox: dict[str, Any] = {}
        if imsi and vehicle_id:
            try:
                tbox = await self._find_status(str(imsi), str(vehicle_id), str(vin))
            except ConfigEntryAuthFailed:
                raise
            except GwmRuApiError:
                _LOGGER.debug("TBOX status unavailable; retaining vehicle telemetry")

        state = build_state(status, tbox)
        location = {"latitude": status.get("latitude"), "longitude": status.get("longitude"), "gps_accuracy": 50}
        car_data = redact_vehicle(car)
        model_name = car_data.get("modelName") or ""
        name_parts = model_name.split(maxsplit=1)
        state["brand"] = car_data.get("brandName") or (name_parts[0] if name_parts else None)
        state["model"] = model_name or car_data.get("model")
        state["color"] = car_data.get("color")
        tank_capacity = car_data.get("tankCapacity")
        try:
            tank_capacity_number = float(tank_capacity) if tank_capacity is not None else None
            if tank_capacity_number is not None and tank_capacity_number.is_integer():
                tank_capacity_number = int(tank_capacity_number)
        except (TypeError, ValueError):
            tank_capacity_number = None
        state["tank_capacity_l"] = tank_capacity_number
        fuel_percent = calculate_fuel_percent(state.get("fuel_liters"), tank_capacity_number)
        if fuel_percent is not None:
            state["fuel_percent"] = fuel_percent

        capability_raw: Any = None
        capability_error: str | None = None
        try:
            user_role = int(car.get("ownership") or 1)
            capability_raw = await self._get_vehicle_capabilities(str(vin), user_role)
            capabilities = build_vehicle_capabilities(capability_raw)
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            capability_error = str(err)
            # Compatibility fallback only. Entity platforms treat a non-cloud
            # capability source permissively so a transient capability API
            # failure cannot make an existing installation lose its entities.
            capabilities = {
                "remote_commands": True,
                "engine": state.get("engine_state") is not None,
                "climate": state.get("climate_state") is not None or state.get("ambient_temperature") is not None,
                "lock": state.get("lock_state") is not None,
                "trunk": state.get("trunk_state") is not None,
                "windows": any(state.get(key) is not None for key in ("window_fl_state", "window_fr_state", "window_rl_state", "window_rr_state")),
                "rear_defroster": state.get("rear_defroster_state") is not None,
                "steering_wheel_heater": state.get("steering_wheel_heater_state") is not None,
                "codes": [],
                "unknown": [],
                "source": "telemetry_fallback",
            }

        diagnostic_status = {
            key: value
            for key, value in status.items()
            if key not in {"items", "latitude", "longitude", "vin"}
            and (value is None or isinstance(value, (str, int, float, bool)))
        }
        diagnostic_items = [
            {"code": str(item.get("code")), "value": item.get("value")}
            for item in (status.get("items") or [])
            if isinstance(item, dict)
        ]
        diagnostics = {
            "status_top_level": diagnostic_status,
            "status_items": diagnostic_items,
            "tbox_status": tbox.get("status") if isinstance(tbox, dict) else None,
            "capability_source": capabilities.get("source"),
            "capability_codes": capabilities.get("codes", []),
            "unknown_capabilities": capabilities.get("unknown", []),
        }
        if capability_raw is not None:
            diagnostics["vehicle_capability_raw"] = capability_raw
        if capability_error:
            diagnostics["vehicle_capability_error"] = capability_error

        return {
            "vin": str(vin),
            "display_vin": car.get("showedVin") or "",
            "vehicle": car_data,
            "vehicle_name": car.get("vehicleName") or car.get("modelName") or "GWM vehicle",
            "state": state,
            "location": location,
            "capabilities": capabilities,
            "diagnostics": diagnostics,
        }

    async def async_check_security_password(self, security_pin: str, check_type: int = 3) -> str:
        await self._ensure_login()
        pin_md5 = hashlib.md5(security_pin.encode("utf-8")).hexdigest()
        await self._request("POST", ENDPOINT_CHECK_SECURITY_PASSWORD, body={"type": str(check_type), "securityPassword": pin_md5})
        return pin_md5

    async def async_send_t5_command(self, vin: str, instructions: dict, expected_remote_type: str, security_pin: str | None = None) -> dict[str, Any]:
        await self._ensure_login()
        security_password = await self.async_check_security_password(security_pin, 3) if security_pin else None
        seq_no = _make_t5_seq_no()
        body = {"vin": vin, "seqNo": seq_no, "remoteType": "0", "instructions": instructions, "securityPassword": security_password, "type": 3, "compoundCommandTemplateId": None}
        send_payload = await self._request("POST", ENDPOINT_T5_SEND_CMD, body=body, vin_header=vin)
        data = send_payload.get("data") or {}
        if isinstance(data, dict):
            seq_no = data.get("seqNo") or seq_no
        await asyncio.sleep(2)
        return await self.async_poll_t5_result(vin, seq_no, expected_remote_type)

    async def async_poll_t5_result(self, vin: str, seq_no: str, expected_remote_type: str, timeout: int = 300, interval: int = 1) -> dict[str, Any]:
        success_codes = {"0", "6"}
        pending_codes = {"1000", "2000"}
        deadline = time.monotonic() + timeout
        last_error_code: str | None = None
        last_error_msg: str | None = None
        while time.monotonic() < deadline:
            await asyncio.sleep(interval)
            try:
                payload = await self._request("GET", ENDPOINT_T5_CTRL_RESULT, params={"seqNo": seq_no, "vin": vin}, vin_header=vin)
            except GwmRuApiError:
                continue
            data = payload.get("data")
            if not isinstance(data, list):
                continue
            matched = [bean for bean in data if isinstance(bean, dict)
                       and str(bean.get("remoteType") or "") == expected_remote_type]
            if not matched:
                continue
            for bean in matched:
                if str(bean.get("resultCode", "")) in success_codes:
                    return bean
            if any(str(bean.get("resultCode", "")) in pending_codes for bean in matched):
                continue
            for bean in matched:
                last_error_code = str(bean.get("resultCode", ""))
                last_error_msg = str(bean.get("resultMsg") or "")
            if last_error_code:
                raise HomeAssistantError(
                    f"Command failed: {last_error_msg}" if last_error_msg else f"Error code {last_error_code}"
                )
        if last_error_code:
            raise HomeAssistantError(f"Command failed: {last_error_msg}" if last_error_msg else f"Error code {last_error_code}")
        raise HomeAssistantError(f"Command timed out after {timeout} seconds")

    async def _ensure_login(self) -> None:
        if not self._access_token:
            await self.async_login()

    async def _get_vehicles(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", ENDPOINT_VEHICLES)
        data = payload.get("data") or []
        return data if isinstance(data, list) else []

    async def _get_last_status(self, vin: str) -> dict[str, Any]:
        payload = await self._request("GET", ENDPOINT_LAST_STATUS, params={"vin": vin, "seqNo": "", "modelId": ""}, vin_header=vin)
        data = payload.get("data") or {}
        return data if isinstance(data, dict) else {}

    async def _find_status(self, imsi: str, vehicle_id: str, vin: str) -> dict[str, Any]:
        payload = await self._request("GET", ENDPOINT_FIND_STATUS, params={"imsi": imsi, "vehicleId": vehicle_id}, vin_header=vin)
        data = payload.get("data") or {}
        return data if isinstance(data, dict) else {}

    async def _get_vehicle_capabilities(self, vin: str, user_role: int) -> Any:
        key = (vin, user_role)
        cached = self._capability_cache.get(key)
        if cached and time.monotonic() - cached[0] < 3600:
            return cached[1]
        payload = await self._request(
            "GET",
            ENDPOINT_VEHICLE_CAPABILITIES,
            params={"vin": vin, "userRole": str(user_role)},
            vin_header=vin,
        )
        data = payload.get("data")
        if data is not None:
            self._capability_cache[key] = (time.monotonic(), data)
        return data

    async def _request(self, method: str, path: str, *, params: dict[str, str] | None = None, body: dict[str, Any] | None = None, with_token: bool = True, vin_header: str | None = None, retry_auth: bool = True) -> dict[str, Any]:
        params = params or {}
        body_json = json.dumps(body, ensure_ascii=False, separators=(",", ":")) if body is not None else ""
        query = urlencode(params, doseq=False)
        url = BASE_URL + path + ("?" + query if query else "")
        headers = self._headers(method, path, url, body_json, with_token, vin_header)
        try:
            async with self._session.request(method, url, headers=headers, data=body_json.encode("utf-8") if body is not None else None, timeout=30) as resp:
                text = await resp.text()
                resp.raise_for_status()
        except (ClientError, TimeoutError) as err:
            raise GwmRuApiError(f"Cannot connect to GWM RU: {err}") from err
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as err:
            raise GwmRuApiError("Invalid GWM RU JSON response") from err
        if not isinstance(payload, dict):
            raise GwmRuApiError("Invalid GWM RU response structure")
        code = str(payload.get("code") if payload.get("code") is not None else "")
        if code == "000000":
            return payload
        description = str(payload.get("description") or payload.get("message") or code or "unknown")
        if with_token and retry_auth and _is_auth_error(code, description):
            _LOGGER.info(
                "GWM RU session expired (code=%s); logging in again",
                code or "unknown",
            )
            await self._async_relogin_after_auth_error(self._access_token)
            return await self._request(
                method,
                path,
                params=params,
                body=body,
                with_token=with_token,
                vin_header=vin_header,
                retry_auth=False,
            )
        if not with_token or _is_auth_error(code, description):
            raise ConfigEntryAuthFailed(description)
        raise GwmRuApiError(description)

    def _headers(self, method: str, path: str, url: str, body_json: str, with_token: bool, vin: str | None) -> dict[str, str]:
        timestamp, nonce, sign = sign_request(method, path, url, body_json)
        headers = {"Accept": "application/json", "Content-Type": "application/json; charset=UTF-8", f"{AUTH_PREFIX}-auth-appkey": APP_KEY, f"{AUTH_PREFIX}-auth-timestamp": timestamp, f"{AUTH_PREFIX}-auth-sign": sign, f"{AUTH_PREFIX}-auth-nonce": nonce, "ip": self._local_ip, "rs": "2", "appId": APP_ID, "brand": BRAND, "terminal": TERMINAL, "enterpriseId": ENTERPRISE_ID, "systemType": SYSTEM_TYPE, "cVer": APP_VERSION, "timeZone": "GMT+03:00", "channel": "APP", "language": LANGUAGE, "regionCode": REGION_CODE, "country": COUNTRY, "communityBrand": "1", "deviceId": self._device_id, "iccid": self._device_id, "User-Agent": "GWM"}
        if with_token and self._access_token:
            headers["accessToken"] = self._access_token
        if vin:
            headers["vin"] = vin
        return headers


def sign_request(method: str, path: str, full_url: str, body_json: str = "") -> tuple[str, str, str]:
    timestamp = str(int(time.time() * 1000))
    nonce = hashlib.md5(str(time.time_ns()).encode("utf-8")).hexdigest()[:16]
    auth_string = f"{AUTH_PREFIX}-auth-appkey:{APP_KEY}{AUTH_PREFIX}-auth-nonce:{nonce}{AUTH_PREFIX}-auth-timestamp:{timestamp}"
    if method.upper() == "GET":
        params = format_get_parameter(full_url)
    elif method.upper() == "POST":
        params = "json=" + body_json
    else:
        params = ""
    raw = method.upper() + path + auth_string + params + APP_SEC
    raw = re.sub(r"\s+", "", raw)
    encoded = quote_plus(raw, safe="")
    return timestamp, nonce, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def format_get_parameter(full_url: str) -> str:
    query = parse_qs(urlparse(full_url).query, keep_blank_values=True)
    out = ""
    for key in sorted(set(query.keys())):
        value = query[key][0] if query[key] else ""
        out += key.lower() + "=" + value
    return out


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _make_t5_seq_no() -> str:
    return uuid.uuid4().hex + "1234"
