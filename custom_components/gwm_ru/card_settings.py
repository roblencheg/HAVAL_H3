"""Validated, vehicle-specific card preferences (no remote actions)."""
RANGES = {"temperature": (16, 32), "climate_time": (5, 30), "engine_time": (5, 30),
          "driver": (1, 3), "passenger": (1, 3), "seat_time": (1, 10)}
BOOLEANS = {"driver_enabled", "passenger_enabled", "comfort_start", "climate_enabled"}


def validate_settings(settings: dict) -> dict:
    if not isinstance(settings, dict):
        raise ValueError("Настройки должны быть объектом")
    for key, value in settings.items():
        if key == "selected_profile":
            if not isinstance(value, str) or len(value) > 64:
                raise ValueError("Недопустимый профиль")
        elif key in RANGES:
            low, high = RANGES[key]
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"Недопустимое значение {key}")
        elif key in BOOLEANS:
            if type(value) is not bool:
                raise ValueError(f"Недопустимое значение {key}")
        else:
            raise ValueError(f"Неизвестная настройка {key}")
    return dict(settings)
