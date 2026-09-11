"""T5 remote command definitions for GWM RU."""

COMMANDS = {
    "flash_lights": {
        "key": "flash_lights",
        "name": "Моргнуть фарами",
        "expected_remote_type": "0x06",
        "risk": "low",
        "icon": "mdi:car-light-high",
        "instructions": {"0x06": {"search": {"whistle": "0", "flashing": "1"}}},
    },
    "horn": {
        "key": "horn",
        "name": "Подать звуковой сигнал",
        "expected_remote_type": "0x06",
        "risk": "low",
        "icon": "mdi:bugle",
        "instructions": {"0x06": {"search": {"whistle": "1", "flashing": "0"}}},
    },
    "flash_and_horn": {
        "key": "flash_and_horn",
        "name": "Моргнуть фарами и подать сигнал",
        "expected_remote_type": "0x06",
        "risk": "low",
        "icon": "mdi:car-light-high",
        "instructions": {"0x06": {"search": {"whistle": "1", "flashing": "1"}}},
    },
    "unlock_vehicle": {
        "key": "unlock_vehicle",
        "name": "Открыть двери",
        "expected_remote_type": "0x05",
        "risk": "medium",
        "icon": "mdi:car-door-lock-open",
        "instructions": {"0x05": {"switchOrder": "1", "operationTime": "0"}},
    },
    "lock_vehicle": {
        "key": "lock_vehicle",
        "name": "Закрыть двери",
        "expected_remote_type": "0x05",
        "risk": "medium",
        "icon": "mdi:car-door-lock",
        "instructions": {"0x05": {"switchOrder": "2", "operationTime": "0"}},
    },
    "engine_start": {
        "key": "engine_start",
        "name": "Запустить двигатель",
        "expected_remote_type": "0x03",
        "risk": "high",
        "icon": "mdi:engine",
        "instructions": {
            "0x03": {
                "operationTime": "15",
                "switchOrder": "1",
            }
        },
    },
    "engine_stop": {
        "key": "engine_stop",
        "name": "Остановить двигатель",
        "expected_remote_type": "0x03",
        "risk": "high",
        "icon": "mdi:engine-off",
        "instructions": {
            "0x03": {
                "operationTime": "0",
                "switchOrder": "2",
            }
        },
    },
    "open_trunk": {
        "key": "open_trunk",
        "name": "Открыть багажник",
        "expected_remote_type": "0x09",
        "risk": "medium",
        "icon": "mdi:car-back",
        "instructions": {"0x09": {"switchOrder": "1", "operationTime": "0"}},
    },
    "close_trunk": {
        "key": "close_trunk",
        "name": "Закрыть багажник",
        "expected_remote_type": "0x09",
        "risk": "medium",
        "icon": "mdi:car-back",
        "instructions": {"0x09": {"switchOrder": "2", "operationTime": "0"}},
    },
    "close_windows": {
        "key": "close_windows",
        "name": "Закрыть окна",
        "expected_remote_type": "0x08",
        "risk": "low",
        "icon": "mdi:car-door",
        "instructions": {
            "0x08": {
                "switchOrder": "2",
                "window": {
                    "leftFront": 0,
                    "leftBack": 0,
                    "rightFront": 0,
                    "rightBack": 0,
                }
            }
        },
    },
    "close_sunroof": {
        "key": "close_sunroof",
        "name": "Закрыть люк",
        "expected_remote_type": "0x08",
        "risk": "low",
        "icon": "mdi:car-door",
        "instructions": {"0x08": {"switchOrder": "2", "window": {"skyLight": 0}}},
    },
    "open_sunroof": {
        "key": "open_sunroof",
        "name": "Открыть люк",
        "expected_remote_type": "0x08",
        "risk": "medium",
        "icon": "mdi:car-door",
        "instructions": {"0x08": {"switchOrder": "1", "window": {"skyLight": 10}}},
    },
    "open_sunshade": {
        "key": "open_sunshade",
        "name": "Открыть шторку люка",
        "expected_remote_type": "0x08",
        "risk": "medium",
        "icon": "mdi:blinds-open",
        "instructions": {"0x08": {"switchOrder": "1", "window": {"shadeScreen": 10}}},
    },
    "close_sunshade": {
        "key": "close_sunshade",
        "name": "Закрыть шторку люка",
        "expected_remote_type": "0x08",
        "risk": "medium",
        "icon": "mdi:blinds-vertical-closed",
        "instructions": {"0x08": {"switchOrder": "2", "window": {}}},
    },
    "rear_defrost_on": {
        "key": "rear_defrost_on",
        "name": "Включить обогрев заднего стекла",
        "expected_remote_type": "0x0B",
        "risk": "medium",
        "icon": "mdi:hot-tub",
        "instructions": {
            "0x0B": {
                "defrost": {
                    "switchOrder": "1",
                    "operationTime": "10",
                    "defrostBack": "1",
                }
            }
        },
    },
    "rear_defrost_off": {
        "key": "rear_defrost_off",
        "name": "Выключить обогрев заднего стекла",
        "expected_remote_type": "0x0B",
        "risk": "medium",
        "icon": "mdi:hot-tub",
        "instructions": {
            "0x0B": {
                "defrost": {
                    "switchOrder": "2",
                    "defrostBack": "1",
                }
            }
        },
    },
    "steering_wheel_heat_on": {
        "key": "steering_wheel_heat_on",
        "name": "Включить обогрев руля",
        "expected_remote_type": "0x19",
        "risk": "medium",
        "icon": "mdi:steering",
        "instructions": {
            "0x19": {
                "switchOrder": "1",
                "operationTime": "10",
            }
        },
    },
    "steering_wheel_heat_off": {
        "key": "steering_wheel_heat_off",
        "name": "Выключить обогрев руля",
        "expected_remote_type": "0x19",
        "risk": "medium",
        "icon": "mdi:steering",
        "instructions": {
            "0x19": {
                "switchOrder": "2",
                "operationTime": "0",
            }
        },
    },
    "windshield_heat_on": {
        "key": "windshield_heat_on",
        "name": "Включить обогрев лобового стекла",
        "expected_remote_type": "0x2A",
        "risk": "medium",
        "icon": "mdi:car-defrost-front",
        "instructions": {
            "0x2A": {
                "switchOrder": "1",
                "operationTime": "15",
            }
        },
    },
    "windshield_heat_off": {
        "key": "windshield_heat_off",
        "name": "Выключить обогрев лобового стекла",
        "expected_remote_type": "0x2A",
        "risk": "medium",
        "icon": "mdi:car-defrost-front",
        "instructions": {
            "0x2A": {
                "switchOrder": "2",
                "operationTime": "0",
            }
        },
    },
    "set_driver_seat_heat": {
        "key": "set_driver_seat_heat",
        "name": "Установить обогрев водительского сиденья",
        "expected_remote_type": "0x0A",
        "risk": "medium",
        "icon": "mdi:car-seat-heater",
        "dynamic": "seat_heat",
        "seat": "driver",
    },
    "set_passenger_seat_heat": {
        "key": "set_passenger_seat_heat",
        "name": "Установить обогрев пассажирского сиденья",
        "expected_remote_type": "0x0A",
        "risk": "medium",
        "icon": "mdi:car-seat-heater",
        "dynamic": "seat_heat",
        "seat": "passenger",
    },
}
