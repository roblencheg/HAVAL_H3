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

from .const import (
    APP_ID,
    APP_KEY,
    APP_SEC,
    APP_VERSION,
    AUTH_PREFIX,
    BASE_URL,
    BRAND,
    COUNTRY,
    ENDPOINT_CHECK_SECURITY_PASSWORD,
    ENDPOINT_FIND_STATUS,
    ENDPOINT_LAST_STATUS,
    ENDPOINT_LOGIN,
    ENDPOINT_T5_CTRL_RESULT,
    ENDPOINT_T5_SEND_CMD,
    ENDPOINT_VEHICLES,
    ENTERPRISE_ID,
    LANGUAGE,
    REGION_CODE,
    SYSTEM_TYPE,
    TERMINAL,
)
from .helpers import normalize_phone, redact_vehicle, build_state

_LOGGER = logging.getLogger(__name__)


class GwmRuApiError(HomeAssistantError):
    """Raised when the GWM RU API returns an error."""


class GwmRuApiClient:
    """Small async client for the unofficial GWM RU API."""

    def __init__(
        self,
        session: ClientSession,
        phone: str,
        password: str,
        device_id: str,
        country: str,
        country_code: str,
    ) -> None:
        self._session = session
        self._phone = normalize_phone(phone)
        self._password = password
        self._device_id = device_id
        self._country = country
        self._country_code = country_code
        self._access_token: str | None = None
        self._login_lock = asyncio.Lock()

    async def async_login(self) -> None:
        """Log in and store the access token in memory."""
        async with self._login_lock:
            body = {
                "account": self._phone,
                "password": self._password,
                "agreement": [1, 2, 18, 19],
                "smsCode": None,
                "msgType": None,
                "model": "Home Assistant",
                "type": 1,
                "deviceId": self._device_id,
                "appType": 0,
                "pushToken": "",
                "country": self._country,
                "countryCode": self._country_code,
                "isEncrypt": False,
            }
            payload = await self._request("POST", ENDPOINT_LOGIN, body=body, with_token=False)
            data = payload.get("data") or {}
            token = data.get("accessToken")
            if not token:
                raise ConfigEntryAuthFailed("GWM RU login did not return accessToken")
            self._access_token = str(token)

    async def async_update(self) -> dict[str, Any]:
        """Fetch vehicle list and current status."""
        await self._ensure_login()
        vehicles = await self._get_vehicles()
        if not vehicles:
            raise GwmRuApiError("No vehicles returned by GWM RU account")

        car = vehicles[0]
        vin = car.get("vin")
        imsi = car.get("imsi")
        vehicle_id = car.get("vehicleId")
        if not vin:
            raise GwmRuApiError("Vehicle does not contain VIN")

        status = await self._get_last_status(str(vin))
        tbox: dict[str, Any] = {}
        if imsi and vehicle_id:
            tbox = await self._find_status(str(imsi), str(vehicle_id), str(vin))

        state = build_state(status, tbox)
        location = {
            "latitude": status.get("latitude"),
            "longitude": status.get("longitude"),
            "gps_accuracy": 50,
        }
        vehicle_name = car.get("vehicleName") or car.get("modelName") or "GWM vehicle"

        car_data = redact_vehicle(car)
        model_name = car_data.get("modelName") or ""
        name_parts = model_name.split(maxsplit=1)
        state["brand"] = car_data.get("brandName") or (name_parts[0] if name_parts else None)
        state["model"] = model_name or car_data.get("model")
        state["color"] = car_data.get("color")

        return {
            "vin": vin,
            "vehicle": car_data,
            "vehicle_name": vehicle_name,
            "state": state,
            "location": location,
        }

    async def async_check_security_password(
        self,
        security_pin: str,
        check_type: int = 3,
    ) -> str:
        """Check GWM security PIN and return MD5 hash for command payload."""
        await self._ensure_login()
        pin_md5 = hashlib.md5(security_pin.encode("utf-8")).hexdigest()
        body = {
            "type": str(check_type),
            "securityPassword": pin_md5,
        }
        await self._request(
            "POST",
            ENDPOINT_CHECK_SECURITY_PASSWORD,
            body=body,
        )
        return pin_md5

    async def async_send_t5_command(
        self,
        vin: str,
        instructions: dict,
        expected_remote_type: str,
        security_pin: str | None = None,
    ) -> dict[str, Any]:
        """Send a T5 remote command and poll for result."""
        await self._ensure_login()

        security_password = None
        if security_pin:
            security_password = await self.async_check_security_password(security_pin, 3)

        seq_no = _make_t5_seq_no()
        body = {
            "vin": vin,
            "seqNo": seq_no,
            "remoteType": "0",
            "instructions": instructions,
            "securityPassword": security_password,
            "type": 3,
            "compoundCommandTemplateId": None,
        }
        _LOGGER.debug("Sending T5 command: seqNo=%s type=3", seq_no)
        send_payload = await self._request(
            "POST",
            ENDPOINT_T5_SEND_CMD,
            body=body,
            vin_header=vin,
        )
        data = send_payload.get("data") or {}
        if isinstance(data, dict):
            seq_no = data.get("seqNo") or seq_no

        await asyncio.sleep(2)
        return await self.async_poll_t5_result(vin, seq_no, expected_remote_type)

    async def async_poll_t5_result(
        self,
        vin: str,
        seq_no: str,
        expected_remote_type: str,
        timeout: int = 300,
        interval: int = 1,
    ) -> dict[str, Any]:
        """Poll for T5 remote command result."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            await asyncio.sleep(interval)
            try:
                payload = await self._request(
                    "GET",
                    ENDPOINT_T5_CTRL_RESULT,
                    params={"seqNo": seq_no},
                    vin_header=vin,
                )
            except GwmRuApiError:
                continue
            data = payload.get("data")
            if not isinstance(data, list):
                continue
            for bean in data:
                if bean.get("remoteType") == expected_remote_type:
                    result_code = str(bean.get("resultCode", ""))
                    result_msg = str(bean.get("resultMsg") or "")
                    if result_code in {"0", "6"}:
                        _LOGGER.debug("T5 command succeeded: code=%s msg=%s", result_code, result_msg)
                        return bean
                    if result_code in {"1000", "2000"}:
                        _LOGGER.debug("T5 command pending: code=%s", result_code)
                        break
                    _LOGGER.warning("T5 command failed: code=%s msg=%s", result_code, result_msg)
                    raise HomeAssistantError(
                        f"Command failed: {result_msg}" if result_msg else f"Error code {result_code}"
                    )
        raise HomeAssistantError("Command timed out after 300 seconds")

    async def _ensure_login(self) -> None:
        if not self._access_token:
            await self.async_login()

    async def _get_vehicles(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", ENDPOINT_VEHICLES)
        data = payload.get("data") or []
        return data if isinstance(data, list) else []

    async def _get_last_status(self, vin: str) -> dict[str, Any]:
        payload = await self._request(
            "GET",
            ENDPOINT_LAST_STATUS,
            params={"vin": vin, "seqNo": "", "modelId": ""},
            vin_header=vin,
        )
        data = payload.get("data") or {}
        return data if isinstance(data, dict) else {}

    async def _find_status(self, imsi: str, vehicle_id: str, vin: str) -> dict[str, Any]:
        payload = await self._request(
            "GET",
            ENDPOINT_FIND_STATUS,
            params={"imsi": imsi, "vehicleId": vehicle_id},
            vin_header=vin,
        )
        data = payload.get("data") or {}
        return data if isinstance(data, dict) else {}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        with_token: bool = True,
        vin_header: str | None = None,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        params = params or {}
        body_json = json.dumps(body, ensure_ascii=False, separators=(",", ":")) if body is not None else ""
        query = urlencode(params, doseq=False)
        url = BASE_URL + path + ("?" + query if query else "")
        headers = self._headers(method, path, url, body_json, with_token, vin_header)

        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                data=body_json.encode("utf-8") if body is not None else None,
                timeout=30,
            ) as resp:
                text = await resp.text()
        except ClientError as err:
            raise GwmRuApiError(f"Cannot connect to GWM RU: {err}") from err

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as err:
            raise GwmRuApiError(f"Invalid GWM RU response: {text[:200]}") from err

        code = str(payload.get("code"))
        if code == "000000":
            return payload

        if with_token and retry_auth and code in {"401", "401000", "308001", "308002", "308003"}:
            _LOGGER.debug("GWM RU token expired, refreshing session")
            self._access_token = None
            await self.async_login()
            return await self._request(
                method,
                path,
                params=params,
                body=body,
                with_token=with_token,
                vin_header=vin_header,
                retry_auth=False,
            )

        description = str(payload.get("description") or payload.get("message") or code)
        _LOGGER.debug("GWM RU error: code=%s description=%s path=%s", code, description, path)
        if not with_token:
            raise ConfigEntryAuthFailed(description)
        raise GwmRuApiError(description)

    def _headers(self, method: str, path: str, url: str, body_json: str, with_token: bool, vin: str | None) -> dict[str, str]:
        timestamp, nonce, sign = sign_request(method, path, url, body_json)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json; charset=UTF-8",
            f"{AUTH_PREFIX}-auth-appkey": APP_KEY,
            f"{AUTH_PREFIX}-auth-timestamp": timestamp,
            f"{AUTH_PREFIX}-auth-sign": sign,
            f"{AUTH_PREFIX}-auth-nonce": nonce,
            "ip": local_ip(),
            "rs": "2",
            "appId": APP_ID,
            "brand": BRAND,
            "terminal": TERMINAL,
            "enterpriseId": ENTERPRISE_ID,
            "systemType": SYSTEM_TYPE,
            "cVer": APP_VERSION,
            "timeZone": "GMT+03:00",
            "channel": "APP",
            "language": LANGUAGE,
            "regionCode": REGION_CODE,
            "country": COUNTRY,
            "communityBrand": "1",
            "deviceId": self._device_id,
            "iccid": self._device_id,
            "User-Agent": "GWM",
        }
        if with_token and self._access_token:
            headers["accessToken"] = self._access_token
        if vin:
            headers["vin"] = vin
        return headers


def sign_request(method: str, path: str, full_url: str, body_json: str = "") -> tuple[str, str, str]:
    timestamp = str(int(time.time() * 1000))
    nonce = hashlib.md5(str(time.time_ns()).encode("utf-8")).hexdigest()[:16]
    auth_string = (
        f"{AUTH_PREFIX}-auth-appkey:{APP_KEY}"
        f"{AUTH_PREFIX}-auth-nonce:{nonce}"
        f"{AUTH_PREFIX}-auth-timestamp:{timestamp}"
    )
    if method.upper() == "GET":
        params = format_get_parameter(full_url)
    elif method.upper() == "POST":
        params = "json=" + body_json
    else:
        params = ""
    raw = method.upper() + path + auth_string + params + APP_SEC
    raw = re.sub(r"\s*|\t|\r|\n", "", raw)
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
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _make_t5_seq_no() -> str:
    """Generate a T5 sequence number."""
    return uuid.uuid4().hex + "1234"
