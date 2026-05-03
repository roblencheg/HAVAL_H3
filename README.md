# GWM RU for Home Assistant

Неофициальная интеграция Home Assistant для российского облака GWM / HAVAL / TANK / ORA / WEY с поддержкой удалённого управления.

Проверено на Haval H3 через российское приложение GWM 2.2.3

## Возможности

- **Мониторинг автомобиля**: запас хода, уровень топлива, пробег
- **Давление и температура в шинах** по всем колёсам
- **Статус TBOX**: онлайн, уровень сигнала
- **GPS-трекер**: местоположение автомобиля на карте
- **Удалённое управление** (требуется PIN-код):
  - Заблокировать / разблокировать двери
  - Открыть / закрыть багажник
  - Открыть / закрыть окна
  - Открыть / закрыть люк
  - Открыть / закрыть шторку люка
  - Включить / выключить обогрев заднего стекла (с таймером)
  - Моргнуть фарами
  - Подать звуковой сигнал
  - Фары + сигнал
- **Кнопки управления** в интерфейсе HA (появляются при сохранении PIN-кода в настройках)
- **HA-сервисы** для каждого действия — используйте в автоматизациях и сценариях
- **Кнопка принудительного обновления** данных
- **Подтверждение для команд среднего риска** (замки, багажник, люк, шторка, обогрев)

## Установка

### Вариант 1: HACS (рекомендуется)

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=roblencheg&repository=HAVAL_H3&category=integration)

1. HACS → Integrations → ⋮ → Custom repositories
2. Repository: `https://github.com/roblencheg/HAVAL_H3`
3. Category: `Integration`
4. Установите **GWM RU**
5. Перезапустите Home Assistant

### Вариант 2: Вручную

1. Скопируйте папку `custom_components/gwm_ru` в `/config/custom_components/gwm_ru`
2. Перезапустите Home Assistant

## Настройка

[![Open your Home Assistant instance and start configuring the GWM RU integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=gwm_ru)

### Первичная настройка

1. **Настройки → Устройства и службы → Добавить интеграцию → GWM RU**
2. Введите **телефон** (в любом формате: `+7923...`, `7923...`, `8923...` или просто `923...`)
3. Введите **пароль** от приложения GWM
4. Укажите **PIN-код безопасности** (6 цифр, задаётся в личном кабинете GWM) — для удалённого управления

### Настройки интеграции

**Настройки → Устройства и службы → GWM RU → Настроить**

- **Poll interval** — периодичность обновления датчиков (в секундах, по умолчанию 300)
- **Remote controls** — включить удалённое управление
- **Security PIN** — PIN-код безопасности (если не указан при первичной настройке)
- **Command cooldown** — задержка между командами (в секундах, по умолчанию 30)
- **Clear security PIN** — удалить сохранённый PIN-код

### PIN-код безопасности

Для отправки команд требуется PIN-код (6 цифр), который задаётся в личном кабинете GWM. Его можно:
- Сохранить в настройках интеграции — тогда кнопки управления появятся в интерфейсе HA
- Передавать при каждом вызове сервиса (поле `security_pin`) — для автоматизаций

> PIN-код хранится в открытом виде в конфигурации HA. Не сообщайте его третьим лицам.

## Данные, которые предоставляет интеграция

- **Запас хода** и **уровень топлива**
- **Пробег**, **марка**, **модель**, **цвет**
- **Давление и температура каждой шины**
- **Уровень масла** и **статус обслуживания**
- **TBOX**: онлайн, статус
- **GPS-координаты** автомобиля (device tracker)

## Удалённое управление

Управление включается в настройках интеграции (флажок «Remote controls»). Команды среднего риска (замки, багажник, люк, шторка, обогрев) требуют подтверждения при вызове через сервис.

После сохранения PIN-кода в интерфейсе HA появятся кнопки для каждой команды.

## Примеры автоматизаций

### Автоматически закрывать окна при уходе из дома

```yaml
alias: "Закрыть окна при уходе"
description: ""
triggers:
  - trigger: state
    entity_id: person.my_phone
    to: "not_home"
conditions:
  - condition: state
    entity_id: sensor.gwm_ru_tbox_online
    state: "on"
actions:
  - action: gwm_ru.close_windows
    data:
      confirm: true
      security_pin: "123456"
```

### Закрывать машину каждый вечер

```yaml
alias: "Закрыть авто в 23:00"
description: ""
triggers:
  - trigger: time
    at: "23:00:00"
conditions:
  - condition: state
    entity_id: person.my_phone
    state: "home"
actions:
  - action: gwm_ru.lock_vehicle
    data:
      confirm: true
```

### Включать обогрев стекла при минусовой температуре

```yaml
alias: "Обогрев стекла по температуре"
description: ""
triggers:
  - trigger: numeric_state
    entity_id: sensor.gwm_ru_outdoor_temperature
    below: -5
actions:
  - action: gwm_ru.rear_defrost_on
    data:
      confirm: true
      operation_time: 15
```

### Подать сигнал при срабатывании охранной сигнализации

```yaml
alias: "Сигнал при тревоге"
description: ""
triggers:
  - trigger: state
    entity_id: alarm_control_panel.home_alarm
    to: "triggered"
actions:
  - action: gwm_ru.flash_and_horn
    data:
      confirm: false
```

> Если PIN-код сохранён в настройках интеграции, поле `security_pin` в автоматизациях можно не указывать.

## Безопасность

Интеграция хранит пароль от учётной записи GWM и PIN-код безопасности в конфигурации Home Assistant.

Проект не связан с GWM, HAVAL, TANK, ORA или WEY. Используйте на свой риск.

## Версия

Текущая версия: **1.0.0**

> **v1.0.0**: Стабильный релиз. PIN-код безопасности обязателен для всех команд. Показываются только кнопки низкого риска (фары, сигнал, окна). Опциональный PIN-код в настройках интеграции, проверка наличия PIN-кода перед отправкой команды.
