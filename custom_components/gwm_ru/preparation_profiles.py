"""Vehicle preparation presets; editing these never issues remote commands."""
from uuid import uuid4

from .card_settings import validate_settings

DEFAULT_SETTINGS = {
    "temperature": 22, "climate_time": 15, "engine_time": 15,
    "climate_enabled": True, "driver_enabled": True, "passenger_enabled": True,
    "driver": 3, "passenger": 3, "seat_time": 5,
}
MAX_PROFILES = 20


def profile_settings(settings: dict) -> dict:
    """Require a complete snapshot, without card-only preferences."""
    if not isinstance(settings, dict) or settings.keys() != DEFAULT_SETTINGS.keys():
        raise ValueError("Нужен полный набор настроек профиля")
    return validate_settings(settings)


def profile_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 40:
        raise ValueError("Название профиля: от 1 до 40 символов")
    return name.strip()


def initial_profiles() -> list[dict]:
    return [
        {"id": "winter", "name": "Зима", "settings": {**DEFAULT_SETTINGS, "temperature": 26, "seat_time": 10}},
        {"id": "summer", "name": "Лето", "settings": {**DEFAULT_SETTINGS, "temperature": 20, "driver_enabled": False, "passenger_enabled": False}},
        {"id": "driver", "name": "Только водитель", "settings": {**DEFAULT_SETTINGS, "passenger_enabled": False}},
    ]


def validate_profiles(profiles: list) -> list[dict]:
    if not isinstance(profiles, list) or len(profiles) > MAX_PROFILES:
        raise ValueError("Допускается до 20 профилей на автомобиль")
    result = []
    for item in profiles:
        if not isinstance(item, dict) or set(item) != {"id", "name", "settings"}:
            raise ValueError("Повреждённый профиль")
        identity = item["id"]
        if not isinstance(identity, str) or not identity or len(identity) > 64 or any(p["id"] == identity for p in result):
            raise ValueError("Недопустимый идентификатор профиля")
        result.append({"id": identity, "name": profile_name(item["name"]), "settings": profile_settings(item["settings"])})
    return result


def change_profiles(profiles: list, action: str, *, profile_id: str = "", name: str = "", settings: dict | None = None) -> list[dict]:
    """Return a new validated list, leaving the original unchanged on error."""
    result = validate_profiles(profiles)
    existing = next((p for p in result if p["id"] == profile_id), None)
    if action != "create" and existing is None:
        raise ValueError("Профиль не найден. Обновите карточку")
    if action == "create":
        result.append({"id": uuid4().hex, "name": profile_name(name), "settings": profile_settings(settings)})
    elif action == "update":
        existing.update(name=profile_name(name), settings=profile_settings(settings))
    elif action == "copy":
        result.append({"id": uuid4().hex, "name": profile_name(name), "settings": dict(existing["settings"])})
    elif action == "delete":
        result.remove(existing)
    else:
        raise ValueError("Неизвестное действие с профилем")
    return validate_profiles(result)
