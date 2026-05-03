"""T5 remote command definitions for GWM RU."""

COMMANDS = {
    "flash_lights": {
        "key": "flash_lights",
        "name": "Моргнуть фарами",
        "expected_remote_type": "0x06",
        "risk": "low",
        "requires_confirm": False,
        "icon": "mdi:car-light-high",
        "instructions": {"0x06": {"search": {"whistle": "0", "flashing": "1"}}},
    },
    "horn": {
        "key": "horn",
        "name": "Подать звуковой сигнал",
        "expected_remote_type": "0x06",
        "risk": "low",
        "requires_confirm": False,
        "icon": "mdi:bugle",
        "instructions": {"0x06": {"search": {"whistle": "1", "flashing": "0"}}},
    },
    "flash_and_horn": {
        "key": "flash_and_horn",
        "name": "Моргнуть фарами и подать сигнал",
        "expected_remote_type": "0x06",
        "risk": "low",
        "requires_confirm": False,
        "icon": "mdi:car-light-high",
        "instructions": {"0x06": {"search": {"whistle": "1", "flashing": "1"}}},
    },
    "unlock_vehicle": {
        "key": "unlock_vehicle",
        "name": "Открыть двери",
        "expected_remote_type": "0x05",
        "risk": "medium",
        "requires_confirm": True,
        "icon": "mdi:car-door-lock-open",
        "instructions": {"0x05": {"switchOrder": "1", "operationTime": "0"}},
    },
    "lock_vehicle": {
        "key": "lock_vehicle",
        "name": "Закрыть двери",
        "expected_remote_type": "0x05",
        "risk": "medium",
        "requires_confirm": True,
        "icon": "mdi:car-door-lock",
        "instructions": {"0x05": {"switchOrder": "2", "operationTime": "0"}},
    },
    "open_trunk": {
        "key": "open_trunk",
        "name": "Открыть багажник",
        "expected_remote_type": "0x09",
        "risk": "medium",
        "requires_confirm": True,
        "icon": "mdi:car-back",
        "instructions": {"0x09": {"switchOrder": "1", "operationTime": "0"}},
    },
    "close_trunk": {
        "key": "close_trunk",
        "name": "Закрыть багажник",
        "expected_remote_type": "0x09",
        "risk": "medium",
        "requires_confirm": True,
        "icon": "mdi:car-back",
        "instructions": {"0x09": {"switchOrder": "2", "operationTime": "0"}},
    },
    "close_windows": {
        "key": "close_windows",
        "name": "Закрыть окна",
        "expected_remote_type": "0x08",
        "risk": "low",
        "requires_confirm": False,
        "icon": "mdi:car-door",
        "instructions": {
            "0x08": {
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
        "requires_confirm": False,
        "icon": "mdi:car-door",
        "instructions": {"0x08": {"window": {"skyLight": 0}}},
    },
    "open_sunroof": {
        "key": "open_sunroof",
        "name": "Открыть люк",
        "expected_remote_type": "0x08",
        "risk": "medium",
        "requires_confirm": True,
        "icon": "mdi:car-door",
        "instructions": {"0x08": {"window": {"skyLight": 10}}},
    },
    "open_sunshade": {
        "key": "open_sunshade",
        "name": "Открыть шторку люка",
        "expected_remote_type": "0x08",
        "risk": "medium",
        "requires_confirm": True,
        "icon": "mdi:blinds-open",
        "instructions": {"0x08": {"switchOrder": "1", "window": {"shadeScreen": 10}}},
    },
    "close_sunshade": {
        "key": "close_sunshade",
        "name": "Закрыть шторку люка",
        "expected_remote_type": "0x08",
        "risk": "medium",
        "requires_confirm": True,
        "icon": "mdi:blinds-vertical-closed",
        "instructions": {"0x08": {"switchOrder": "2", "window": {}}},
    },
    "rear_defrost_on": {
        "key": "rear_defrost_on",
        "name": "Включить обогрев заднего стекла",
        "expected_remote_type": "0x0B",
        "risk": "medium",
        "requires_confirm": True,
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
        "requires_confirm": True,
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
}
