"""Sensors for GWM RU."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import supports_state
from .const import DOMAIN, ITEM_MAP, EXTRA_SENSORS
from .coordinator import GwmRuCoordinator
from .entity import GwmRuEntity, setup_vehicle_entities


@dataclass(frozen=True, kw_only=True)
class GwmRuSensorDescription(SensorEntityDescription):
    state_key: str


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: GwmRuCoordinator = hass.data[DOMAIN][entry.entry_id]
    descriptions = tuple(
        GwmRuSensorDescription(
            key=defn.key,
            state_key=defn.key,
            name=defn.name,
            native_unit_of_measurement=defn.unit,
            icon=defn.icon,
            device_class=defn.device_class,
        )
        for defn in list(ITEM_MAP.values()) + list(EXTRA_SENSORS.values())
    )

    def entities_for_vehicle(vehicle):
        entities: list[SensorEntity] = [
            GwmRuSensor(coordinator, vehicle["vin"], description)
            for description in descriptions
            if supports_state(vehicle, description.state_key)
        ]
        if (vehicle.get("capabilities") or {}).get("remote_history"):
            entities.append(GwmRuRemoteHistorySensor(coordinator, vehicle["vin"]))
        return entities

    setup_vehicle_entities(coordinator, async_add_entities, entities_for_vehicle)


class GwmRuSensor(GwmRuEntity, SensorEntity):
    entity_description: GwmRuSensorDescription

    def __init__(self, coordinator: GwmRuCoordinator, vin: str, description: GwmRuSensorDescription) -> None:
        super().__init__(coordinator, vin)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entity_prefix(vin)}_{description.key}"

    @property
    def native_value(self) -> Any:
        return ((self.vehicle or {}).get("state") or {}).get(self.entity_description.state_key)


class GwmRuRemoteHistorySensor(GwmRuEntity, SensorEntity):
    """Expose recent remote command history for one vehicle."""

    _attr_name = "История удалённых команд"
    _attr_icon = "mdi:history"

    def __init__(self, coordinator: GwmRuCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{coordinator.entity_prefix(vin)}_remote_command_history"

    @property
    def native_value(self) -> str | None:
        history = (self.vehicle or {}).get("remote_history") or []
        if not history:
            return None
        return _history_label(history[0])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        history = (self.vehicle or {}).get("remote_history") or []
        return {
            "count": len(history),
            "history": [_normalize_history_item(item) for item in history[:20]],
        }


def _history_label(item: dict[str, Any]) -> str:
    remote_type = str(item.get("remoteType") or "")
    params = _parse_params(item.get("params"))
    switch_order = _extract_switch_order(params)
    names = {
        "0x03": {"1": "Запуск двигателя", "0": "Остановка двигателя", "2": "Остановка двигателя"},
        "0x04": {"1": "Включение климата", "0": "Выключение климата", "2": "Выключение климата"},
        "0x05": {"1": "Открытие дверей", "0": "Закрытие дверей", "2": "Закрытие дверей"},
        "0x09": {"1": "Открытие багажника", "0": "Закрытие багажника", "2": "Закрытие багажника"},
    }
    if remote_type == "0x06":
        search = ((params.get("0x06") or {}).get("search") or {}) if isinstance(params, dict) else {}
        flashing = str(search.get("flashing") or "0") == "1"
        whistle = str(search.get("whistle") or "0") == "1"
        if flashing and whistle:
            name = "Свет и сигнал"
        elif flashing:
            name = "Моргание фарами"
        elif whistle:
            name = "Звуковой сигнал"
        else:
            name = "Поиск автомобиля"
    else:
        name = names.get(remote_type, {}).get(switch_order, remote_type or "Удалённая команда")
    if str(item.get("resultCode")) not in {"0", "6"}:
        return f"{name}: ошибка {item.get('resultCode')}"
    return name


def _parse_params(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _extract_switch_order(params: dict[str, Any]) -> str:
    for value in params.values():
        if not isinstance(value, dict):
            continue
        if "switchOrder" in value:
            return str(value.get("switchOrder"))
        for nested in value.values():
            if isinstance(nested, dict) and "switchOrder" in nested:
                return str(nested.get("switchOrder"))
    return ""


def _normalize_history_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": _history_label(item),
        "remote_type": item.get("remoteType"),
        "result_code": item.get("resultCode"),
        "result_msg": item.get("resultMsg"),
        "created_at": item.get("createdAt"),
        "modified_at": item.get("modifiedAt"),
        "params": _parse_params(item.get("params")),
    }
