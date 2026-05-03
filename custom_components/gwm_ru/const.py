"""Constants for the GWM RU integration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


DOMAIN = "gwm_ru"
PLATFORMS = ["button", "sensor", "binary_sensor", "device_tracker"]

CONF_PHONE = "phone"
CONF_COUNTRY = "country"
CONF_COUNTRY_CODE = "country_code"
CONF_DEVICE_ID = "device_id"
CONF_POLL_INTERVAL = "poll_interval"
CONF_ENABLE_REMOTE_CONTROLS = "enable_remote_controls"
CONF_ENABLE_DANGEROUS_CONTROLS = "enable_dangerous_controls"
CONF_COMMAND_COOLDOWN = "command_cooldown_seconds"
CONF_SECURITY_PIN = "security_pin"

DEFAULT_COUNTRY = "RU"
DEFAULT_COUNTRY_CODE = "+7"
DEFAULT_POLL_INTERVAL = 300
DEFAULT_ENABLE_REMOTE_CONTROLS = False
DEFAULT_ENABLE_DANGEROUS_CONTROLS = False
DEFAULT_COMMAND_COOLDOWN = 30

BASE_URL = "https://rus-h5-gateway.gwmcloud.com"

AUTH_PREFIX = "gwm"
APP_ID = "1"
BRAND = "1"
TERMINAL = "GW_APP_Haval"
ENTERPRISE_ID = "CC01"
SYSTEM_TYPE = "1"
APP_VERSION = "2.2.3"
LANGUAGE = "ru"
REGION_CODE = "RU"
COUNTRY = "RU"

# Extracted from the public Android APK. This is not a user secret, but do not log it.
APP_KEY = "4694605273"
APP_SEC = "e4e478c00f570e76a8993653a7b81d57"

ENDPOINT_LOGIN = "/app-api/api/v1.0/userAuth/loginAccount"
ENDPOINT_VEHICLES = "/app-api/api/v1.0/vehicle/acquireVehicles"
ENDPOINT_LAST_STATUS = "/app-api/api/v1.0/vehicle/getLastStatus"
ENDPOINT_FIND_STATUS = "/app-api/api/v1.0/vehicle/findStatus"
ENDPOINT_T5_SEND_CMD = "/app-api/api/v1.0/vehicle/T5/sendCmd"
ENDPOINT_T5_CTRL_RESULT = "/app-api/api/v1.0/vehicle/getRemoteCtrlResultT5"
ENDPOINT_CHECK_SECURITY_PASSWORD = "/app-api/api/v1.0/userAuth/checkSecurityPassword"

KPA_TO_ATM = 101.325


class Conversion(Enum):
    """Conversion type for item values."""

    PRESSURE = "pressure"


@dataclass
class SensorDefBase:
    """Base sensor definition."""

    key: str
    name: str
    unit: str | None
    icon: str | None
    device_class: str | None


@dataclass
class ItemSensorDef(SensorDefBase):
    """Sensor definition for vehicle status items."""

    code: str
    convert: Conversion | None


@dataclass
class ExtraSensorDef(SensorDefBase):
    """Sensor definition derived from vehicle metadata."""


ITEM_MAP: dict[str, ItemSensorDef] = {
    "2011007": ItemSensorDef("range_km", "Запас хода", "km", "mdi:map-marker-distance", None, "2011007", None),
    "2017002": ItemSensorDef("fuel_liters", "Топливо", "L", "mdi:fuel", None, "2017002", None),
    "2103010": ItemSensorDef("mileage_total", "Пробег", "km", "mdi:counter", None, "2103010", None),
    "2101001": ItemSensorDef("tire_fl_pressure", "Давление в шине передней левой", "атм", "mdi:car-tire-alert", "pressure", "2101001", Conversion.PRESSURE),
    "2101005": ItemSensorDef("tire_fl_temp", "Температура шины передней левой", "°C", "mdi:thermometer", "temperature", "2101005", None),
    "2101002": ItemSensorDef("tire_fr_pressure", "Давление в шине передней правой", "атм", "mdi:car-tire-alert", "pressure", "2101002", Conversion.PRESSURE),
    "2101006": ItemSensorDef("tire_fr_temp", "Температура шины передней правой", "°C", "mdi:thermometer", "temperature", "2101006", None),
    "2101003": ItemSensorDef("tire_rl_pressure", "Давление в шине задней левой", "атм", "mdi:car-tire-alert", "pressure", "2101003", Conversion.PRESSURE),
    "2101007": ItemSensorDef("tire_rl_temp", "Температура шины задней левой", "°C", "mdi:thermometer", "temperature", "2101007", None),
    "2101004": ItemSensorDef("tire_rr_pressure", "Давление в шине задней правой", "атм", "mdi:car-tire-alert", "pressure", "2101004", Conversion.PRESSURE),
    "2101008": ItemSensorDef("tire_rr_temp", "Температура шины задней правой", "°C", "mdi:thermometer", "temperature", "2101008", None),
}

EXTRA_SENSORS: dict[str, ExtraSensorDef] = {
    "brand": ExtraSensorDef("brand", "Марка", None, "mdi:car", None),
    "model": ExtraSensorDef("model", "Модель", None, "mdi:car-info", None),
    "color": ExtraSensorDef("color", "Цвет", None, "mdi:palette", None),
    "oil_qty": ExtraSensorDef("oil_qty", "Уровень масла", None, "mdi:oil", None),
    "service_status": ExtraSensorDef("service_status", "Статус обслуживания", None, "mdi:car-connected", None),
    "tbox_status": ExtraSensorDef("tbox_status", "Статус TBOX", None, "mdi:access-point-network", None),
}
