/* GWM RU Card v1.1.2 */
(() => {
  const CARD_VERSION = "1.0.0";
  const INTEGRATION = "gwm_ru";

  const SUFFIX = {
    engine: "_engine_on",
    doors: "_doors_open",
    windows: "_windows_open",
    windowFl: "_window_fl_open",
    windowFr: "_window_fr_open",
    windowRl: "_window_rl_open",
    windowRr: "_window_rr_open",
    trunk: "_trunk_open",
    unlocked: "_locked",
    climateOn: "_climate_on",
    tbox: "_tbox_online",
    gps: "_gps_enabled",
    lock: "_central_lock",
    climate: "_climate",
    climateRuntime: "_climate_runtime",
    refresh: "_refresh",
    fuel: "_fuel_liters",
    fuelPercent: "_fuel_percent",
    range: "_range_km",
    mileage: "_mileage_total",
    modelCode: "_model_code_raw",
    oilQty: "_oil_qty",
    lastUpdate: "_last_successful_update",
    tireFlWarning: "_tire_fl_pressure_alarm",
    tireFrWarning: "_tire_fr_pressure_alarm",
    tireRlWarning: "_tire_rl_pressure_alarm",
    tireRrWarning: "_tire_rr_pressure_alarm",
    tireFlP: "_tire_fl_pressure",
    tireFrP: "_tire_fr_pressure",
    tireRlP: "_tire_rl_pressure",
    tireRrP: "_tire_rr_pressure",
    tireFlT: "_tire_fl_temp",
    tireFrT: "_tire_fr_temp",
    tireRlT: "_tire_rl_temp",
    tireRrT: "_tire_rr_temp",
    signal: "_tbox_signal_raw",
    lastCommand: "_last_command",
    featureFlags: "_feature_flags",
    steeringHeat: "_steering_wheel_heater_on",
    rearDefrost: "_rear_defroster_on",
    frontDefrost: "_front_defrost_on",
    windscreenHeat: "_windshield_heater_on",
    seatDriver: "_driver_seat_heater_state",
    seatPassenger: "_passenger_seat_heater_state",
    sunroofOpen: "_sunroof_open",
  };

  class GwmVehicleCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._config = {};
      this._hass = null;
      this._entityRegistry = [];
      this._device = null;
      this._entities = {};
      this._resolving = false;
      this._settingsToken = null;
      this._resolvedKey = null;
      this._busy = new Set();
      this._engineRuntime = 15;
      this._assumed = {};
    }

    static getStubConfig() {
      return {};
    }

    static getGridOptions() {
      return { columns: 12, rows: 10, min_columns: 6, min_rows: 6 };
    }

    setConfig(config) {
      if ((config.device_id || "") !== (this._config.device_id || "") || (config.entity || "") !== (this._config.entity || "")) {
        this._entryId = undefined;
        this._entities = {};
      }
      this._config = {
        confirm_controls: true,
        engine_runtime: 15,
        ...config,
      };
      const configuredRuntime = Number(this._config.engine_runtime);
      if (Number.isFinite(configuredRuntime)) {
        this._engineRuntime = Math.min(30, Math.max(5, configuredRuntime));
      }
      this._resolvedKey = null;
      this._settingsToken = null;
      if (this._hass) this._resolveEntities();
      this._render();
    }

    set hass(hass) {
      if (this._hass?.connection !== hass?.connection) this._resolvedKey = null;
      this._hass = hass;
      const key = `${this._config.device_id || ""}|${this._config.entity || ""}`;
      if (this._resolvedKey !== key && !this._resolving && !this._resolveRetryTimer) {
        this._resolveEntities();
      }
      this._render();
    }

    getCardSize() {
      return 10;
    }

    _awaitResponse(promise, milliseconds = 15000) {
      let timer;
      return Promise.race([promise, new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error("Home Assistant не ответил вовремя. Обновите данные перед повторной командой: её результат может быть неизвестен.")), milliseconds);
      })]).finally(() => clearTimeout(timer));
    }

    disconnectedCallback() {
      clearTimeout(this._resolveRetryTimer);
      this._resolveRetryTimer = null;
    }

    async _resolveEntities() {
      if (!this._hass || this._resolving) return;
      clearTimeout(this._resolveRetryTimer);
      this._resolveRetryTimer = null;
      this._resolving = true;
      const config = {...this._config};
      const resolveKey = `${config.device_id || ""}|${config.entity || ""}`;
      try {
        const registry = await this._awaitResponse(this._hass.callWS({
          type: "config/entity_registry/list",
        }));
        this._entityRegistry = Array.isArray(registry) ? registry : [];

        let deviceId = config.device_id || null;
        if (!deviceId && config.entity) {
          const selected = this._entityRegistry.find(
            (entry) => entry.entity_id === config.entity
          );
          deviceId = selected?.device_id || null;
        }

        const gwmEntries = this._entityRegistry.filter(
          (entry) => entry.platform === INTEGRATION
        );

        if (!deviceId) {
          deviceId = gwmEntries.find((entry) => entry.device_id)?.device_id || null;
        }

        const vehicleEntries = deviceId
          ? gwmEntries.filter((entry) => entry.device_id === deviceId)
          : gwmEntries;

        const devices = await this._awaitResponse(this._hass.callWS({
          type: "config/device_registry/list",
        }));
        if (resolveKey !== `${this._config.device_id || ""}|${this._config.entity || ""}`) return;
        if (!Array.isArray(devices)) throw new Error("Реестр устройств Home Assistant недоступен");
        this._device = Array.isArray(devices)
          ? devices.find((device) => device.id === deviceId) || null
          : null;

        this._entryId = vehicleEntries.find((entry) => entry.config_entry_id)?.config_entry_id;
        this._entities = {};
        for (const [key, suffix] of Object.entries(SUFFIX)) {
          const found = vehicleEntries.find((entry) =>
            String(entry.unique_id || "").endsWith(suffix)
          );
          if (found) this._entities[key] = found.entity_id;
        }

        this._entities.climate ||=
          vehicleEntries.find((entry) =>
            entry.entity_id.startsWith("climate.")
          )?.entity_id;
        this._entities.lock ||=
          vehicleEntries.find((entry) =>
            entry.entity_id.startsWith("lock.")
          )?.entity_id;
        this._entities.refresh ||=
          vehicleEntries.find(
            (entry) =>
              entry.entity_id.startsWith("button.") &&
              /refresh|obnov/i.test(entry.entity_id)
          )?.entity_id;

        if (!this._entryId || !Object.keys(this._entities).length) throw new Error("Автомобиль пока не найден в Home Assistant");
        this._resolvedKey = resolveKey;
      } catch (err) {
        console.error("[GWM RU Card] entity discovery failed", err);
      } finally {
        this._resolving = false;
        if (this._resolvedKey !== `${this._config.device_id || ""}|${this._config.entity || ""}`) {
          this._resolveRetryTimer = setTimeout(() => { this._resolveRetryTimer = null; if (this.isConnected) this._resolveEntities(); }, 10000);
        }
        this._render();
      }
    }

    _isGwmUniqueId(uniqueId) {
      if (!uniqueId) return false;
      return Object.values(SUFFIX).some((suffix) =>
        String(uniqueId).endsWith(suffix)
      );
    }

    _state(key) {
      const entityId = this._entities[key];
      return entityId ? this._hass?.states?.[entityId] : undefined;
    }

    _isOn(key) {
      return this._state(key)?.state === "on";
    }

    _isUnavailable(key) {
      const state = this._state(key)?.state;
      return !state || state === "unknown" || state === "unavailable";
    }

    _remoteCommandInProgress() {
      const state = this._state("lastCommand");
      return state?.attributes?.in_progress === true;
    }

    _isRemoteAction(id) {
      return id !== "refresh" && !String(id).startsWith("readonly-");
    }

    _featureOn(key) {
      if (!this._isUnavailable(key)) return this._isOn(key);
      return Boolean(this._assumed[key]);
    }

    _value(key, fallback = "—") {
      const stateObj = this._state(key);
      if (!stateObj || ["unknown", "unavailable", ""].includes(stateObj.state)) {
        return fallback;
      }
      const unit = stateObj.attributes?.unit_of_measurement;
      return `${stateObj.state}${unit ? ` ${unit}` : ""}`;
    }

    _rawValue(key) {
      const stateObj = this._state(key);
      if (!stateObj || ["unknown", "unavailable", ""].includes(stateObj.state)) {
        return null;
      }
      return String(stateObj.state);
    }

    _featureEnabled(capability) {
      const flags = this._state("featureFlags");
      if (!flags?.attributes || !(capability in flags.attributes)) return true;
      return flags.attributes[capability] !== false;
    }

    _seatValue(key) {
      const raw = this._rawValue(key);
      if (raw === null) return "Нет данных";
      const value = Number(raw);
      if (Number.isFinite(value)) {
        return value === 0
          ? "Выключен"
          : `Включён · уровень ${value}`;
      }
      return `${raw}`;
    }

    _drivetrain() {
      if (this._config.drivetrain) {
        return String(this._config.drivetrain).toUpperCase();
      }

      const raw = (this._rawValue("modelCode") || "").toUpperCase();
      if (!raw) return null;
      if (raw.includes("CC7150BA24C")) return "4WD";
      if (raw.includes("CC7150BA00B") || raw.includes("CC7150BA01B")) {
        return "2WD";
      }
      return null;
    }

    _headerTitle() {
      if (this._config.title) return String(this._config.title);
      const drivetrain = this._drivetrain();
      return drivetrain ? `Haval ${drivetrain}` : "Haval";
    }

    _openWindows() {
      const definitions = [
        ["windowFl", "переднее левое"],
        ["windowFr", "переднее правое"],
        ["windowRl", "заднее левое"],
        ["windowRr", "заднее правое"],
      ];
      const known = definitions.filter(([key]) => !this._isUnavailable(key));
      const open = known
        .filter(([key]) => this._isOn(key))
        .map(([, label]) => label);

      if (!known.length && this._isOn("windows")) {
        return ["одно или несколько окон"];
      }
      return open;
    }

    _windowSubtitle() {
      if (this._isUnavailable("windows")) return "Нет данных";
      const open = this._openWindows();
      if (open.length) {
        return `Открыты: ${open.join(", ")} · закрыть все`;
      }
      return "Все закрыты · проветрить";
    }

    _relativeUpdate() {
      const raw = this._rawValue("lastUpdate");
      if (!raw) return "Время обновления неизвестно";

      const then = new Date(raw).getTime();
      if (!Number.isFinite(then)) return "Время обновления неизвестно";

      const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
      if (seconds < 15) return "Обновлено только что";
      if (seconds < 60) return `Обновлено ${seconds} сек назад`;
      const minutes = Math.floor(seconds / 60);
      if (minutes < 60) return `Обновлено ${minutes} мин назад`;
      const hours = Math.floor(minutes / 60);
      if (hours < 24) return `Обновлено ${hours} ч назад`;
      const days = Math.floor(hours / 24);
      return `Обновлено ${days} дн назад`;
    }

    _commandLabel() {
      const raw = this._value("lastCommand", "");
      if (!raw) return "";
      const names = {
        "0x03": "Двигатель",
        "0x04": "Климат",
        "0x05": "Центральный замок",
        "0x06": "Свет / сигнал",
        "0x08": "Окна / люк",
        "0x09": "Багажник",
        "0x0A": "Подогрев сидений",
        "0x0B": "Обогрев заднего стекла",
        "0x19": "Обогрев руля",
        "0x2A": "Обогрев лобового стекла",
      };
      return raw.replace(/^(0x[0-9A-Fa-f]+)\b/, (code) => {
        const normalized = `0x${code.slice(2).toUpperCase()}`;
        return names[normalized] || code;
      });
    }

    _labelBool(key, onLabel, offLabel, unknownLabel = "—") {
      if (this._isUnavailable(key)) return unknownLabel;
      return this._isOn(key) ? onLabel : offLabel;
    }

    _escape(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    _icon(icon) {
      return `<ha-icon icon="${icon}"></ha-icon>`;
    }

    _statusChip(icon, label, tone = "safe") {
      return `<div class="chip ${tone}">${this._icon(icon)}<span>${this._escape(label)}</span></div>`;
    }

    _control(id, icon, title, subtitle, tone = "", disabled = false) {
      const remoteBusy =
        this._remoteCommandInProgress() && this._isRemoteAction(id);
      const effectiveDisabled = disabled || remoteBusy;
      const busy = this._busy.has(id) || remoteBusy;
      const visibleSubtitle = remoteBusy
        ? "Выполняется удалённая команда…"
        : subtitle;
      return `
        <button
          class="control ${tone} ${busy ? "busy" : ""} ${effectiveDisabled ? "disabled" : ""}"
          ${effectiveDisabled ? "disabled" : `data-action="${id}"`}
          type="button"
        >
          ${this._icon(icon)}
          <span class="control-copy">
            <strong>${this._escape(title)}</strong>
            <small>${this._escape(visibleSubtitle)}</small>
          </span>
        </button>`;
    }

    _comfortControl(id, key, icon, title, { experimental = false } = {}) {
      const on = this._featureOn(key);
      const unknown = this._isUnavailable(key);
      const subtitle = unknown
        ? `${on ? "Выключить" : "Включить"}${experimental ? " · эксперимент" : ""}`
        : `${on ? "Включен · выключить" : "Выключен · включить"}${experimental ? " · эксперимент" : ""}`;
      return this._control(id, icon, title, subtitle, on ? "active" : "");
    }

    _readOnlyComfort(key, icon, title, value) {
      return this._control(
        `readonly-${key}`,
        icon,
        title,
        value,
        "readonly",
        true
      );
    }

    _roofControl(id, assumedKey, icon, title) {
      const assumed = this._assumed[assumedKey];
      const subtitle =
        assumed === true
          ? "Открыта · закрыть · эксперимент"
          : assumed === false
            ? "Закрыта · открыть · эксперимент"
            : "Открыть / закрыть · эксперимент";
      return this._control(id, icon, title, subtitle, "experimental");
    }

    _levelBars(rawValue, max, kind = "flat") {
      const number = Number(rawValue);
      if (!Number.isFinite(number)) {
        return `<span class="level unknown" title="Нет данных">—</span>`;
      }
      const active = Math.max(0, Math.min(max, Math.round(number)));
      const bars = [];
      for (let i = 1; i <= max; i += 1) {
        const height =
          kind === "signal"
            ? Math.round(4 + ((i - 1) / Math.max(1, max - 1)) * 10)
            : 10;
        bars.push(
          `<i class="${i <= active ? "on" : ""}" style="height:${height}px"></i>`
        );
      }
      return `<span class="level ${kind}" aria-label="${active} из ${max}">${bars.join("")}</span>`;
    }

    _tire(label, pKey, tKey, warningKey) {
      const warning = this._state(warningKey)?.state;
      const active = warning === "on";
      const status = active ? "Предупреждение давления" : warning === "off" ? "Нет предупреждения давления" : "Статус предупреждения недоступен";
      return `
        <div class="tire${active ? " warning" : ""}" title="${status}" aria-label="${label}: ${status}">
          <strong>${label}${active ? ' <ha-icon icon="mdi:car-tire-alert" aria-label="Предупреждение давления"></ha-icon>' : warning !== "off" ? ' <small>?</small>' : ""}</strong>
          <span>${this._escape(this._value(pKey))}</span>
          <small>${this._escape(this._value(tKey))}</small>
        </div>`;
    }

    _restoreCardSettings() {
      if (!this._entryId) return;
      if (this._settingsEntry !== this._entryId) {
        this._settingsEntry = this._entryId;
        this._settingsToken = null;
        this._seatSettings = {driver:3, passenger:3, operation_time:5};
        this._seatEnabled = {driver:true, passenger:true};
        this._comfortStart = false;
        this._climateEnabled = true;
        this._selectedProfile = "";
        this._profileNameDraft = null;
        this._comfortTemperature = undefined;
        this._comfortRuntime = undefined;
        this._engineRuntime = Number(this._config.engine_runtime) || 15;
      }
      const saved = this._state("refresh")?.attributes?.card_settings;
      if (!saved) return;
      const token = JSON.stringify(saved);
      if (token === this._settingsToken) return;
      this._settingsToken = token;
      if ((saved.selected_profile || "") !== this._selectedProfile) this._profileNameDraft = null;
      for (const [field, property] of [["temperature","_comfortTemperature"],["climate_time","_comfortRuntime"],["engine_time","_engineRuntime"],["comfort_start","_comfortStart"],["climate_enabled","_climateEnabled"],["selected_profile","_selectedProfile"]]) {
        if (saved[field] !== undefined) this[property] = saved[field];
      }
      for (const key of ["driver","passenger"]) {
        if (saved[key] !== undefined) this._seatSettings[key] = saved[key];
        if (saved[`${key}_enabled`] !== undefined) this._seatEnabled[key] = saved[`${key}_enabled`];
      }
      if (saved.seat_time !== undefined) this._seatSettings.operation_time = saved.seat_time;
    }

    _saveCardSettings(settings) {
      this._updateProfileSummary();
      if (!this._entryId || !this._hass) return Promise.resolve();
      const entryId = this._entryId;
      this._settingsSave = (this._settingsSave || Promise.resolve()).then(() =>
        this._awaitResponse(this._hass.callService(INTEGRATION, "save_card_settings", {entry_id:entryId, settings}), 30000)
      ).catch(error => { console.error("GWM settings save failed", error); alert("Не удалось сохранить настройки карточки. Проверьте подключение к Home Assistant."); });
      return this._settingsSave;
    }

    _profileDraft() {
      const number = (value, fallback, min, max) => Number.isInteger(Number(value)) && Number(value) >= min && Number(value) <= max ? Number(value) : fallback;
      return {
        engine_time:number(this._engineRuntime,15,5,30),
        temperature:number(this._comfortTemperature ?? this._state("climate")?.attributes?.temperature,22,16,32),
        climate_time:number(this._comfortRuntime ?? this._state("climateRuntime")?.state,15,5,30),
        climate_enabled:this._climateEnabled !== false,
        driver_enabled:this._seatEnabled?.driver !== false,
        passenger_enabled:this._seatEnabled?.passenger !== false,
        driver:number(this._seatSettings?.driver,3,1,3),
        passenger:number(this._seatSettings?.passenger,3,1,3),
        seat_time:number(this._seatSettings?.operation_time,5,1,10),
      };
    }

    _profiles() { return this._state("refresh")?.attributes?.preparation_profiles || []; }

    _visibleProfiles() {
      const ids = this._config.visible_profiles;
      return this._profiles().filter(profile => !Array.isArray(ids) || ids.includes(profile.id));
    }

    _profileSummary() {
      const d = this._profileDraft();
      const seat = key => this._featureEnabled(`seat_heat_${key}`) ? (d[`${key}_enabled`] ? d[key] : "выкл") : "нет";
      return `Двигатель ${d.engine_time} мин · ${d.climate_enabled ? `Климат ${d.temperature} °C / ${d.climate_time} мин` : "Климат: пропустить"} · Сиденья ${seat("driver")} / ${seat("passenger")} · ${d.seat_time} мин`;
    }

    _updateProfileSummary() {
      const selected = this._profiles().find(p => p.id === this._selectedProfile);
      const d = this._profileDraft();
      const changed = selected && (Object.keys(d).some(key => d[key] !== selected.settings[key]) || (this._profileNameDraft !== null && this._profileNameDraft !== undefined && this._profileNameDraft !== selected.name));
      const status = this.shadowRoot?.querySelector("[data-profile-status]");
      if (status) status.textContent = selected ? (changed ? "Изменён" : "Сохранён") : "Текущие настройки";
      const summary = this.shadowRoot?.querySelector("[data-profile-summary]");
      if (summary) summary.textContent = this._profileSummary();
    }

    _profilePanel() {
      const profiles = this._profiles();
      const selected = profiles.find(p => p.id === this._selectedProfile);
      const d = this._profileDraft();
      const range = (key,label,min,max,unit="") => `<label class="profile-field"><span>${label}<b>${d[key]}${unit}</b></span><input aria-label="Профиль: ${label}" data-profile-field="${key}" type="range" min="${min}" max="${max}" step="1" value="${d[key]}"></label>`;
      const check = (key,label) => `<label class="profile-check"><input data-profile-field="${key}" type="checkbox" ${d[key] ? "checked" : ""}>${label}</label>`;
      const busy = this._busy.has("profiles") || !this._entryId || this._resolving;
      return `<div class="section preparation">
        <div class="section-title">${this._profileEditorHost ? "Профили подготовки" : "Подготовка автомобиля"} <small data-profile-status></small></div>
        <fieldset ${busy ? "disabled" : ""}>
          ${this._profileEditorHost ? `<div class="profile-visibility"><b>Кнопки профилей в карточке</b>${profiles.map(p => `<label class="profile-check"><input type="checkbox" data-profile-visible="${this._escape(p.id)}" ${this._visibleProfiles().some(visible => visible.id === p.id) ? "checked" : ""}>${this._escape(p.name)}</label>`).join("")}<small>Отметьте профили для показа под климатом. Снятие флажка скрывает кнопку только в этой карточке.</small></div>
          <div class="profile-toolbar"><select aria-label="Профиль подготовки" id="profile-select"><option value="">Текущие настройки</option>${profiles.map(p => `<option value="${this._escape(p.id)}" ${p.id === this._selectedProfile ? "selected" : ""}>${this._escape(p.name)}</option>`).join("")}</select></div>` : `<div class="profile-choices" role="group" aria-label="Профили подготовки">${this._visibleProfiles().map(p => `<button type="button" data-profile-choice="${this._escape(p.id)}" aria-pressed="${p.id === this._selectedProfile}" class="profile-choice ${p.id === this._selectedProfile ? "selected" : ""}">${this._escape(p.name)}</button>`).join("")}</div>`}
          <p data-profile-summary></p>
          ${this._profileEditorHost ? `<div class="profile-editor">
            <label class="profile-field">Название профиля<input id="profile-name" maxlength="40" value="${this._escape(this._profileNameDraft ?? selected?.name ?? "")}" placeholder="Например, Зима"></label>
            ${range("engine_time","Время двигателя",5,30," мин")}
            ${check("climate_enabled","Включать климат при подготовке")}
            ${range("temperature","Температура",16,32," °C")}${range("climate_time","Время климата",5,30," мин")}
            ${["driver","passenger"].filter(key => this._featureEnabled(`seat_heat_${key}`)).map(key => check(`${key}_enabled`,key === "driver" ? "Подогрев водителя" : "Подогрев пассажира") + range(key,key === "driver" ? "Мощность водителя" : "Мощность пассажира",1,3)).join("")}
            ${range("seat_time","Время подогрева",1,10," мин")}
            <div class="profile-buttons"><button type="button" data-profile-operation="create" ${profiles.length >= 20 ? "disabled" : ""}>Сохранить как новый</button>
            ${selected ? `<button type="button" data-profile-operation="update">Сохранить изменения</button><button type="button" data-profile-operation="select">Вернуть сохранённое</button><button type="button" data-profile-operation="copy" ${profiles.length >= 20 ? "disabled" : ""}>Копировать</button><button type="button" data-profile-operation="delete">Удалить</button>` : ""}</div>
          </div>` : ""}
        </fieldset>
        ${this._profileEditorHost ? "" : `<button type="button" id="preparation-start" ${!this._entryId || this._busy.size || this._remoteCommandInProgress() || this._isUnavailable("engine") || this._isOn("engine") ? "disabled" : ""}>${this._busy.has("preparation") ? "Подготовка…" : "Запустить подготовку"}</button>`}
        ${this._profileEditorHost ? "<small>Профили сохраняются кнопками выше сразу для всех карточек этого автомобиля. Команды автомобилю не отправляются. Отмена редактора карточки не отменяет сохранение профиля.</small>" : ""}
      </div>`;
    }

    async _manageProfile(action, profileId = this._selectedProfile) {
      const selected = this._profiles().find(p => p.id === profileId);
      if (action === "delete" && !window.confirm(`Удалить профиль «${selected?.name}»?`)) return;
      const nameInput = this.shadowRoot.getElementById("profile-name");
      const name = action === "copy" ? `${selected?.name || "Профиль"} — копия`.slice(0,40) : nameInput?.value.trim();
      if (["create","update"].includes(action) && !name) { nameInput?.focus(); return; }
      const settings = this._profileDraft();
      const entryId = this._entryId;
      return this._runBusy("profiles", async () => {
        await this._settingsSave;
        await this._hass.callService(INTEGRATION,"manage_preparation_profile",{entry_id:entryId,action,profile_id:profileId || "",...(["create","update","copy"].includes(action) ? {name} : {}),...(["create","update"].includes(action) ? {settings} : {})});
        this._profileNameDraft = null;
      });
    }

    _preparationData() {
      const d = this._profileDraft();
      return {entry_id:this._entryId,engine_time:d.engine_time,temperature:d.temperature,climate_time:d.climate_time,climate_enabled:d.climate_enabled,seat_time:d.seat_time,
        ...(this._featureEnabled("seat_heat_driver") ? {driver:d.driver_enabled ? d.driver : 0} : {}),
        ...(this._featureEnabled("seat_heat_passenger") ? {passenger:d.passenger_enabled ? d.passenger : 0} : {})};
    }

    _render() {
      this._restoreCardSettings();
      if (!this.shadowRoot) return;
      if (!this._hass) {
        this.shadowRoot.innerHTML =
          `<ha-card><div style="padding:16px">GWM RU Card</div></ha-card>`;
        return;
      }

      const climate = this._state("climate");
      const targetTemp = Number(
        this._comfortTemperature ?? climate?.attributes?.temperature ??
          climate?.attributes?.target_temp ??
          22
      );
      const runtime = Number(
        this._comfortRuntime ?? this._state("climateRuntime")?.state ??
          climate?.attributes?.operation_time_minutes ??
          15
      );
      const engineRuntime = Number.isFinite(this._engineRuntime)
        ? this._engineRuntime
        : 15;

      const engineKnown = !this._isUnavailable("engine");
      const lockKnown = !this._isUnavailable("unlocked");
      const trunkKnown = !this._isUnavailable("trunk");
      const windowsKnown = !this._isUnavailable("windows");
      const climateKnown = !this._isUnavailable("climateOn") || (climate && !["unknown", "unavailable"].includes(climate.state));
      const onlineKnown = !this._isUnavailable("tbox");
      const engineOn = engineKnown && this._isOn("engine");
      const unlocked = lockKnown && this._isOn("unlocked");
      const climateOn =
        this._isOn("climateOn") || climate?.state === "heat_cool";
      const trunkOpen = trunkKnown && this._isOn("trunk");
      const windowsOpen = windowsKnown && this._isOn("windows");
      const doorsOpen = this._isOn("doors");
      const online = onlineKnown && this._isOn("tbox");

      const alerts = [
        doorsOpen
          ? this._statusChip("mdi:car-door-open", "Открыта дверь", "danger")
          : "",
        windowsOpen
          ? this._statusChip(
              "mdi:car-door",
              this._openWindows().length
                ? `Окна: ${this._openWindows().join(", ")}`
                : "Открыто окно",
              "danger"
            )
          : "",
        trunkOpen
          ? this._statusChip("mdi:car-back", "Открыт багажник", "danger")
          : "",
      ].filter(Boolean);

      const windscreenStatus = this._labelBool(
        "windscreenHeat",
        "Включен",
        "Выключен",
        "Нет данных"
      );

      this.shadowRoot.innerHTML = `
        <style>
          :host { display:block; }
          * { box-sizing:border-box; }
          ha-card {
            overflow:hidden;
            border-radius:var(--ha-card-border-radius,18px);
            background:var(--ha-card-background,var(--card-background-color));
          }
          .wrap { padding:18px; color:var(--primary-text-color); }
          .header {
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:12px;
          }
          .title {
            min-width:0;
            flex:1;
          }
          .title h2 {
            margin:0;
            font-size:21px;
            font-weight:700;
            line-height:1.2;
            white-space:nowrap;
            overflow:hidden;
            text-overflow:ellipsis;
          }
          .online {
            display:flex;
            align-items:center;
            gap:6px;
            font-size:12px;
            color:var(--secondary-text-color);
            white-space:nowrap;
          }
          .dot {
            width:9px;
            height:9px;
            border-radius:50%;
            background:var(--disabled-text-color);
          }
          .dot.on { background:var(--success-color,#43a047); }
          .stats {
            display:grid;
            grid-template-columns:repeat(4,minmax(0,1fr));
            gap:8px;
            margin-top:15px;
          }
          .stat {
            min-width:0;
            border-radius:13px;
            padding:10px;
            background:color-mix(
              in srgb,
              var(--primary-color) 6%,
              transparent
            );
          }
          .stat span {
            display:block;
            color:var(--secondary-text-color);
            font-size:10px;
            white-space:nowrap;
          }
          .stat b {
            display:block;
            margin-top:4px;
            font-size:13px;
            overflow:hidden;
            text-overflow:ellipsis;
            white-space:nowrap;
          }
          .chips {
            display:flex;
            gap:7px;
            flex-wrap:wrap;
            margin-top:10px;
          }
          .chip {
            display:flex;
            align-items:center;
            gap:5px;
            border-radius:999px;
            padding:7px 10px;
            font-size:12px;
            font-weight:600;
          }
          .chip ha-icon { --mdc-icon-size:17px; }
          .chip.danger {
            color:var(--error-color,#d32f2f);
            background:color-mix(
              in srgb,
              var(--error-color,#d32f2f) 11%,
              transparent
            );
          }
          .section { margin-top:18px; }
          .section-title {
            margin:0 0 9px;
            font-size:11px;
            letter-spacing:.09em;
            font-weight:700;
            color:var(--secondary-text-color);
            text-transform:uppercase;
          }
          .controls,
          .comfort {
            display:grid;
            grid-template-columns:repeat(3,minmax(0,1fr));
            gap:8px;
          }
          .control {
            appearance:none;
            border:0;
            text-align:left;
            min-width:0;
            min-height:66px;
            border-radius:14px;
            padding:11px;
            cursor:pointer;
            background:color-mix(
              in srgb,
              var(--primary-color) 7%,
              var(--card-background-color)
            );
            color:var(--primary-text-color);
            display:flex;
            gap:9px;
            align-items:center;
            transition:transform .12s ease,background .12s ease;
          }
          .control:hover {
            background:color-mix(
              in srgb,
              var(--primary-color) 12%,
              var(--card-background-color)
            );
          }
          .control:active { transform:scale(.98); }
          .control ha-icon {
            --mdc-icon-size:25px;
            color:var(--primary-color);
            flex:none;
          }
          .control.active ha-icon { color:var(--warning-color,#f9a825); }
          .control.danger ha-icon { color:var(--error-color,#d32f2f); }
          .control.experimental ha-icon { color:var(--warning-color,#f9a825); }
          .control.busy {
            opacity:.55;
            pointer-events:none;
          }
          .control.disabled {
            cursor:default;
            opacity:.58;
          }
          .control-copy {
            min-width:0;
            display:flex;
            flex-direction:column;
            gap:3px;
          }
          .control-copy strong {
            font-size:12px;
            white-space:nowrap;
            overflow:hidden;
            text-overflow:ellipsis;
          }
          .control-copy small {
            font-size:10px;
            color:var(--secondary-text-color);
            line-height:1.25;
            white-space:normal;
          }
          .timer-panel,
          .climate-panel {
            border-radius:16px;
            background:color-mix(in srgb,var(--primary-color) 6%,transparent);
            padding:14px;
          }
          .timer-panel { margin-top:9px; }
          .timer-head {
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:10px;
            margin-bottom:4px;
          }
          .timer-head span {
            display:flex;
            align-items:center;
            gap:7px;
            font-size:12px;
            color:var(--secondary-text-color);
          }
          .timer-head ha-icon { --mdc-icon-size:18px; }
          .runtime {
            display:flex;
            align-items:center;
            gap:10px;
            margin-top:10px;
          }
          .runtime input {
            flex:1;
            accent-color:var(--primary-color);
          }
          .runtime b {
            min-width:52px;
            text-align:right;
            font-size:12px;
          }
          .climate-top {
            display:grid;
            grid-template-columns:1fr;
            margin-bottom:10px;
          }
          .climate-main {
            display:grid;
            grid-template-columns:auto 1fr auto;
            gap:10px;
            align-items:center;
          }
          .temp-btn {
            width:38px;
            height:38px;
            border-radius:12px;
            border:0;
            cursor:pointer;
            background:var(--card-background-color);
            color:var(--primary-text-color);
            font-size:22px;
          }
          .temp { text-align:center; }
          .temp strong { font-size:27px; }
          .temp small {
            display:block;
            color:var(--secondary-text-color);
            margin-top:2px;
          }
          .comfort { margin-top:10px; }
          .tires {
            display:grid;
            grid-template-columns:repeat(4,1fr);
            gap:8px;
          }
          .tire {
            text-align:center;
            border-radius:13px;
            padding:10px 5px;
            background:color-mix(
              in srgb,
              var(--secondary-text-color) 5%,
              transparent
            );
          }
          .tire.warning {
            box-shadow:inset 0 0 0 1px var(--error-color,#db4437);
            background:color-mix(in srgb,var(--error-color,#db4437) 14%,transparent);
          }
          .tire.warning strong { color:var(--error-color,#db4437); }
          .tire strong ha-icon { --mdc-icon-size:16px; }
          .tire strong small { display:inline; }
          .tire strong {
            display:block;
            color:var(--secondary-text-color);
            font-size:10px;
          }
          .tire span {
            display:block;
            font-size:13px;
            font-weight:700;
            margin-top:5px;
          }
          .tire small {
            display:block;
            color:var(--secondary-text-color);
            margin-top:2px;
          }
          .system {
            display:flex;
            flex-wrap:wrap;
            align-items:center;
            gap:14px;
            color:var(--secondary-text-color);
            font-size:12px;
          }
          .system-item {
            display:flex;
            align-items:center;
            gap:6px;
            min-height:20px;
          }
          .system-item ha-icon { --mdc-icon-size:17px; }
          .level {
            display:inline-flex;
            align-items:flex-end;
            gap:2px;
            height:15px;
          }
          .level i {
            display:block;
            width:4px;
            border-radius:1px;
            background:color-mix(
              in srgb,
              var(--secondary-text-color) 22%,
              transparent
            );
          }
          .level.flat i { width:5px; }
          .level i.on { background:var(--primary-color); }
          .level.unknown { align-items:center; }
          .preparation { padding:16px; border-radius:18px; background:var(--secondary-background-color, #292f33); }
          .preparation fieldset { border:0; margin:0; padding:0; min-width:0; }
          .preparation .section-title { display:flex; flex-wrap:wrap; gap:8px; justify-content:space-between; }
          [data-profile-status] { text-transform:none; letter-spacing:normal; }
          .preparation small, .preparation p { color:var(--secondary-text-color); font-size:12px; line-height:1.5; }
          .profile-toolbar { display:flex; flex-wrap:wrap; gap:8px; }
          .profile-toolbar select { flex:1; min-width:120px; }
          .preparation button, .preparation select, #profile-name { font:inherit; font-size:13px; color:var(--primary-text-color); background:var(--card-background-color,#303539); border:1px solid var(--divider-color,#555); border-radius:10px; padding:10px; box-sizing:border-box; }
          .preparation button { cursor:pointer; }
          .preparation button:disabled { opacity:.45; cursor:default; }
          .preparation input { accent-color:var(--primary-color,#03a9f4); }
          .profile-editor { display:grid; gap:14px; padding:12px 0; }
          .profile-field { display:grid; gap:8px; font-size:13px; min-width:0; }
          .profile-field span { display:flex; justify-content:space-between; gap:8px; }
          .profile-field input { width:100%; min-width:0; }
          .profile-check { display:flex; align-items:center; gap:8px; font-size:13px; }
          .profile-buttons { display:flex; flex-wrap:wrap; gap:8px; }
          .profile-choices { display:flex; flex-wrap:wrap; gap:8px; }
          .preparation .profile-choice { flex:1 1 auto; min-width:72px; max-width:100%; overflow-wrap:anywhere; transition:background-color .15s, border-color .15s; }
          .preparation .profile-choice.selected { border-color:var(--primary-color,#03a9f4); background:color-mix(in srgb,var(--primary-color,#03a9f4) 22%,var(--card-background-color,#303539)); box-shadow:inset 0 0 0 1px var(--primary-color,#03a9f4); font-weight:700; }
          .profile-visibility { display:grid; gap:8px; padding-bottom:16px; font-size:13px; }
          .profile-choice:focus-visible { outline:2px solid var(--primary-color,#03a9f4); outline-offset:3px; }
          .climate-toggle { width:100%; display:flex; align-items:center; justify-content:space-between; border:0; padding:10px 0; background:none; color:var(--secondary-text-color); font-family:inherit; cursor:pointer; text-align:left; }
          .climate-toggle::after { content:"⌄"; font-size:20px; }
          .climate-toggle[aria-expanded="true"]::after { content:"⌃"; }
          .climate-toggle:focus-visible { outline:2px solid var(--primary-color); outline-offset:3px; border-radius:6px; }
          .climate-panel[hidden] { display:none; }
          @media (prefers-reduced-motion:reduce) { .preparation .profile-choice { transition:none; } }
          #preparation-start { display:block; width:100%; margin:8px 0; background:var(--primary-color,#03a9f4); color:var(--text-primary-color,#fff); font-weight:600; }
          @media (max-width:600px) {
            .wrap { padding:14px; }
            .controls,
            .comfort {
              grid-template-columns:repeat(2,minmax(0,1fr));
            }
            .stats { grid-template-columns:repeat(2,minmax(0,1fr)); }
            .tires { grid-template-columns:repeat(2,1fr); }
            .title h2 { font-size:18px; }
          }
                  /* 2026 reference baseline: HA Tile/Sections + Bubble Card + Mushroom typography */
          :host {
            --gwm-row-height:56px;
            --gwm-pill-radius:28px;
            --gwm-chip-height:36px;
            --gwm-chip-radius:19px;
            --gwm-sub-button:36px;
            --gwm-gap:8px;
            --gwm-surface:var(--secondary-background-color,color-mix(in srgb,var(--primary-text-color) 6%,var(--card-background-color)));
          }
          ha-card {
            border-radius:var(--ha-card-border-radius,20px);
            border:var(--ha-card-border-width,1px) solid var(--ha-card-border-color,var(--divider-color));
            box-shadow:var(--ha-card-box-shadow,none);
          }
          .wrap { padding:16px; }
          .header { min-height:40px; }
          .title h2 { font-size:20px; font-weight:600; line-height:1.25; }
          .online {
            min-height:var(--gwm-chip-height);
            padding:0 12px;
            border-radius:var(--gwm-chip-radius);
            background:var(--gwm-surface);
            font-size:12px;
            font-weight:400;
          }
          .dot { width:8px; height:8px; }
          .stats { gap:var(--gwm-gap); margin-top:16px; }
          .stat {
            min-height:var(--gwm-row-height);
            display:grid;
            align-content:center;
            border-radius:var(--gwm-pill-radius);
            padding:7px 16px;
            background:var(--gwm-surface);
          }
          .stat span { font-size:12px; font-weight:400; }
          .stat b { margin-top:2px; font-size:14px; font-weight:500; }
          .chips { gap:var(--gwm-gap); margin-top:8px; }
          .chip {
            min-height:var(--gwm-chip-height);
            border-radius:var(--gwm-chip-radius);
            padding:0 12px;
            font-size:12px;
            font-weight:500;
          }
          .section { margin-top:20px; }
          .section-title {
            margin:0 0 8px;
            font-size:14px;
            line-height:20px;
            letter-spacing:0;
            font-weight:600;
            text-transform:none;
            color:var(--primary-text-color);
          }
          .controls,.comfort {
            grid-template-columns:repeat(2,minmax(0,1fr));
            gap:var(--gwm-gap);
          }
          .control {
            min-height:var(--gwm-row-height);
            border-radius:var(--gwm-pill-radius);
            padding:6px 14px 6px 8px;
            gap:10px;
            background:var(--gwm-surface);
            transition:background-color 180ms ease,transform 120ms ease;
          }
          .control:hover {
            background:color-mix(in srgb,var(--primary-color) 10%,var(--gwm-surface));
          }
          .control ha-icon {
            --mdc-icon-size:20px;
            width:40px;
            height:40px;
            display:grid;
            place-items:center;
            border-radius:20px;
            background:color-mix(in srgb,var(--primary-color) 12%,transparent);
            color:var(--primary-color);
          }
          .control.active {
            background:color-mix(in srgb,var(--primary-color) 12%,var(--gwm-surface));
          }
          .control.active ha-icon {
            background:var(--primary-color);
            color:var(--text-primary-color,#fff);
          }
          .control.danger ha-icon {
            background:color-mix(in srgb,var(--error-color,#d32f2f) 14%,transparent);
            color:var(--error-color,#d32f2f);
          }
          .control.experimental ha-icon {
            background:color-mix(in srgb,var(--warning-color,#f9a825) 14%,transparent);
            color:var(--warning-color,#f9a825);
          }
          .control-copy { gap:1px; }
          .control-copy strong { font-size:14px; font-weight:500; }
          .control-copy small { font-size:12px; font-weight:400; line-height:16px; }
          .timer-panel,.climate-panel,.seat-panel,.preparation {
            border-radius:24px;
            background:var(--gwm-surface);
            box-shadow:none;
          }
          .timer-panel,.climate-panel { padding:16px; }
          .timer-head span,.runtime b { font-size:12px; }
          .temp-btn {
            width:var(--gwm-sub-button);
            height:var(--gwm-sub-button);
            border-radius:18px;
            border:var(--ha-card-border-width,1px) solid var(--ha-card-border-color,var(--divider-color));
            background:var(--card-background-color);
            font-size:20px;
          }
          .temp strong { font-size:26px; font-weight:500; }
          .tire {
            min-height:64px;
            display:grid;
            align-content:center;
            border-radius:20px;
            background:var(--gwm-surface);
            padding:10px 8px;
          }
          .tire strong { font-size:12px; font-weight:400; }
          .tire span { font-size:14px; font-weight:500; margin-top:2px; }
          .system { gap:8px; }
          .system-item {
            min-height:var(--gwm-chip-height);
            padding:0 10px;
            border-radius:var(--gwm-chip-radius);
            background:var(--gwm-surface);
            font-size:12px;
          }
          .preparation { padding:16px; }
          .preparation button,.preparation select,#profile-name {
            min-height:40px;
            border-radius:20px;
            border:var(--ha-card-border-width,1px) solid var(--ha-card-border-color,var(--divider-color));
            background:var(--card-background-color);
            font-size:13px;
          }
          #preparation-start {
            min-height:var(--gwm-row-height);
            border-radius:var(--gwm-pill-radius);
          }
          @media (max-width:600px) {
            .wrap { padding:14px; }
            .stats,.controls,.comfort,.tires { grid-template-columns:repeat(2,minmax(0,1fr)); }
            .title h2 { font-size:20px; }
          }
          @media (max-width:380px) {
            .controls,.comfort { grid-template-columns:1fr; }
          }
</style>

        ${this._profileEditorHost ? this._profilePanel() : `<ha-card>
          <div class="wrap">
            <div class="header">
              <div class="title">
                <h2>${this._escape(this._headerTitle())}</h2>
              </div>
              <div class="online">
                <span class="dot ${online ? "on" : ""}"></span>
                ${onlineKnown ? (online ? "Online" : "Offline") : "Нет данных"}
              </div>
            </div>

            <div class="stats">
              <div class="stat">
                <span>Топливо л</span>
                <b>${this._escape(this._value("fuel"))}</b>
              </div>
              <div class="stat">
                <span>Топливо %</span>
                <b>${this._escape(this._value("fuelPercent"))}</b>
              </div>
              <div class="stat">
                <span>Запас</span>
                <b>${this._escape(this._value("range"))}</b>
              </div>
              <div class="stat">
                <span>Пробег</span>
                <b>${this._escape(this._value("mileage"))}</b>
              </div>
            </div>

            ${
              alerts.length
                ? `<div class="chips">${alerts.join("")}</div>`
                : ""
            }

            <div class="section">
              <div class="section-title">Управление</div>
              <div class="controls">
                ${this._control(
                  "engine",
                  engineOn ? "mdi:engine-off" : "mdi:engine",
                  "Двигатель",
                  engineKnown ? (engineOn ? "Остановить" : `Запустить · ${engineRuntime} мин`) : "Нет данных",
                  engineOn ? "active" : "",
                  !engineKnown
                )}
                ${this._control(
                  "lock",
                  unlocked ? "mdi:lock" : "mdi:lock-open-variant",
                  "Замок",
                  lockKnown ? (unlocked ? "Закрыть" : "Открыть") : "Нет данных",
                  unlocked ? "active" : "",
                  !lockKnown
                )}
                ${this._control(
                  "trunk",
                  "mdi:car-back",
                  "Багажник",
                  trunkKnown ? (trunkOpen ? "Закрыть" : "Открыть") : "Нет данных",
                  trunkOpen ? "danger" : "",
                  !trunkKnown
                )}
                ${this._control(
                  "windows",
                  "mdi:car-door",
                  "Окна",
                  this._windowSubtitle(),
                  windowsOpen ? "danger" : "",
                  !windowsKnown
                )}
                ${this._featureEnabled("sunroof") ? this._roofControl(
                  "sunroof",
                  "sunroofOpen",
                  "mdi:car-select",
                  "Панорама"
                ) : ""}
                ${this._featureEnabled("sunshade") ? this._roofControl(
                  "sunshade",
                  "sunshadeOpen",
                  "mdi:blinds",
                  "Шторка"
                ) : ""}
                ${this._control(
                  "refresh",
                  "mdi:refresh",
                  "Обновить",
                  this._relativeUpdate()
                )}
              </div>

              <div class="timer-panel">
                <div class="timer-head">
                  <span>${this._icon("mdi:timer-outline")}Таймер автозапуска двигателя</span>
                  <b id="engine-runtime-label">${engineRuntime} мин</b>
                </div>
                <div class="runtime">
                  <input
                    id="engine-runtime"
                    type="range"
                    min="5"
                    max="30"
                    step="1"
                    value="${engineRuntime}"
                    ${engineOn || !engineKnown ? "disabled" : ""}
                  >
                  <b>${engineRuntime} мин</b>
                </div>
              </div>
            </div>

            <div class="section">
              ${this._config.collapse_climate ? `<button type="button" id="climate-toggle" class="section-title climate-toggle" aria-expanded="${this._climateExpanded === true}" aria-controls="climate-content">Климат</button>` : `<div class="section-title">Климат</div>`}
              <div id="climate-content" class="climate-panel" ${this._config.collapse_climate && this._climateExpanded !== true ? "hidden" : ""}>
                <label style="display:flex;gap:8px;align-items:center;font-size:13px;margin-bottom:12px"><input id="comfort-start" type="checkbox" ${this._comfortStart ? "checked" : ""}>Включить климат и сиденья при запуске</label>
                <div class="climate-top">
                  ${this._control(
                    "climate",
                    "mdi:air-conditioner",
                    "Кондиционер",
                    climateKnown ? (climateOn ? "Выключить" : "Включить") : "Нет данных",
                    climateOn ? "active" : "",
                    !climateKnown
                  )}
                </div>

                <div class="climate-main">
                  <button class="temp-btn" data-temp-step="-1" type="button">−</button>
                  <div class="temp">
                    <strong>${Number.isFinite(targetTemp) ? targetTemp : 22} °C</strong>
                    <small>${climateOn ? "Работает" : "Выключен"}</small>
                  </div>
                  <button class="temp-btn" data-temp-step="1" type="button">+</button>
                </div>

                <div class="runtime">
                  ${this._icon("mdi:timer-outline")}
                  <input
                    id="runtime"
                    type="range"
                    min="5"
                    max="30"
                    step="1"
                    value="${Number.isFinite(runtime) ? runtime : 15}"
                  >
                  <b>${Number.isFinite(runtime) ? runtime : 15} мин</b>
                </div>

                <div class="comfort">
                  ${this._featureEnabled("steering_wheel_heat") ? this._comfortControl(
                    "steering-heat",
                    "steeringHeat",
                    "mdi:steering",
                    "Обогрев руля"
                  ) : ""}
                  ${this._seatHeatingPanel()}
                  ${this._featureEnabled("rear_defrost") ? this._comfortControl(
                    "rear-defrost",
                    "rearDefrost",
                    "mdi:car-defrost-rear",
                    "Обогрев заднего стекла"
                  ) : ""}
                  ${this._featureEnabled("front_defrost") ? this._comfortControl(
                    "front-defrost",
                    "frontDefrost",
                    "mdi:car-defrost-front",
                    "Обдув лобового",
                    { experimental: true }
                  ) : ""}
                  ${this._featureEnabled("front_windscreen_heat") ? this._readOnlyComfort(
                    "windscreenHeat",
                    "mdi:car-defrost-front",
                    "Обогрев лобового",
                    windscreenStatus
                  ) : ""}
                </div>
              </div>
            </div>

            ${this._profilePanel()}
            <div class="section">
              <div class="section-title">Шины</div>
              <div class="tires">
                ${this._tire("ПЛ", "tireFlP", "tireFlT", "tireFlWarning")}
                ${this._tire("ПП", "tireFrP", "tireFrT", "tireFrWarning")}
                ${this._tire("ЗЛ", "tireRlP", "tireRlT", "tireRlWarning")}
                ${this._tire("ЗП", "tireRrP", "tireRrT", "tireRrWarning")}
              </div>
            </div>

            <div class="section">
              <div class="section-title">Система</div>
              <div class="system">
                <span class="system-item">
                  ${this._icon(online ? "mdi:cloud-check" : "mdi:cloud-off-outline")}
                  T-Box ${online ? "online" : "offline"}
                </span>
                <span class="system-item" title="Уровень GSM T-Box">
                  GSM ${this._levelBars(this._rawValue("signal"), 4, "signal")}
                </span>
                <span class="system-item">
                  ${this._icon("mdi:crosshairs-gps")}
                  GPS ${this._labelBool("gps", "есть", "нет")}
                </span>
                ${
                  this._state("lastCommand")
                    ? `<span class="system-item">${this._icon("mdi:cloud-check-outline")}${this._escape(this._commandLabel())}</span>`
                    : ""
                }
              </div>
            </div>
          </div>
        </ha-card>`}`;

      this._bindActions();
    }

    _seatHeatingPanel() {
      const seats = [["driver", "seat_heat_driver", "seatDriver", "Водитель"], ["passenger", "seat_heat_passenger", "seatPassenger", "Пассажир"]].filter(([, feature]) => this._featureEnabled(feature));
      if (!seats.length) return "";
      this._seatSettings ||= {driver: 3, passenger: 3, operation_time: 5};
      this._seatEnabled ||= {driver: true, passenger: true};
      return `<div class="seat-panel">
        <style>
          .seat-panel{grid-column:1/-1;padding:14px;border-radius:14px;background:var(--card-background-color)}
          .seat-row{display:grid;grid-template-columns:minmax(100px,1fr) minmax(100px,1fr);align-items:center;gap:14px;padding:12px 0;border-bottom:1px solid var(--divider-color)}
          .seat-name{display:flex;align-items:center;gap:6px;font-size:13px;font-weight:600}
          .seat-status{display:block;font-size:11px;color:var(--secondary-text-color);margin-top:4px}
          .seat-status.on{color:var(--warning-color,#e58b12)}
          .seat-slider input{width:100%;margin:0;accent-color:var(--primary-color);cursor:pointer}
          .seat-ticks{display:flex;justify-content:space-between;font-size:11px;color:var(--secondary-text-color);padding:0 5px;margin-top:3px}
          .seat-panel>.control{width:100%;margin-top:12px}
          .seat-name input{accent-color:var(--primary-color)}
        
</style>
        <strong>Подогрев сидений</strong>
        ${seats.map(([key, , sensor, label]) => `<div class="seat-row">
          <div><label class="seat-name"><input type="checkbox" data-seat-enable="${key}" aria-label="Включить: ${label}" ${this._seatEnabled[key] ? "checked" : ""}>${label}</label>
          <span class="seat-status ${Number(this._rawValue(sensor))>0 ? "on" : ""}" role="status" data-seat-status="${key}">${this._escape(this._seatValue(sensor))}</span></div>
          <div class="seat-slider"><input aria-label="Подогрев: ${label}" data-seat-setting="${key}" type="range" min="1" max="3" step="1" value="${Math.max(1,this._seatSettings[key])}" ${this._seatEnabled[key] ? "" : "disabled"}><div class="seat-ticks"><span>1</span><span>2</span><span>3</span></div></div>
        </div>`).join("")}
        <div class="seat-row"><div class="seat-name">Таймер <span data-seat-time>${this._seatSettings.operation_time} мин</span></div>
        <div class="seat-slider"><input aria-label="Таймер подогрева" data-seat-setting="operation_time" type="range" min="1" max="10" step="1" value="${this._seatSettings.operation_time}"><div class="seat-ticks"><span>1 мин</span><span>10 мин</span></div></div></div>
        ${this._control("seat-heating", "mdi:car-seat-heater", "Применить", "Уровни и таймер", "", !this._entryId || this._busy.has("seat-heating") || this._remoteCommandInProgress())}
      </div>`;
    }

    _bindActions() {
      this.shadowRoot.getElementById("climate-toggle")?.addEventListener("click", event => {
        this._climateExpanded = !this._climateExpanded;
        event.currentTarget.setAttribute("aria-expanded", String(this._climateExpanded));
        this.shadowRoot.getElementById("climate-content").hidden = !this._climateExpanded;
      });
      this._updateProfileSummary();
      this.shadowRoot.getElementById("profile-select")?.addEventListener("change", event => this._manageProfile("select",event.target.value));
      this.shadowRoot.querySelectorAll("[data-profile-choice]").forEach(button => button.addEventListener("click", () => this._manageProfile("select",button.dataset.profileChoice)));
      this.shadowRoot.querySelectorAll("[data-profile-visible]").forEach(input => input.addEventListener("change", () => {
        const visible = new Set(this._visibleProfiles().map(profile => profile.id));
        if (input.checked) visible.add(input.dataset.profileVisible); else visible.delete(input.dataset.profileVisible);
        this.dispatchEvent(new CustomEvent("profile-visibility-changed", {detail:{profiles:[...visible]},bubbles:true,composed:true}));
      }));
      this.shadowRoot.getElementById("profile-name")?.addEventListener("input", event => {this._profileNameDraft = event.target.value; this._updateProfileSummary();});
      this.shadowRoot.querySelectorAll("[data-profile-operation]").forEach(button => button.addEventListener("click", () => this._manageProfile(button.dataset.profileOperation)));
      this.shadowRoot.querySelectorAll("[data-profile-field]").forEach(input => {
        input.addEventListener("input", () => {
          const label = input.previousElementSibling?.querySelector("b");
          if (label) label.textContent = `${input.value}${input.dataset.profileField === "temperature" ? " °C" : input.dataset.profileField.endsWith("time") ? " мин" : ""}`;
        });
        input.addEventListener("change", () => {
          const key = input.dataset.profileField;
          const value = input.type === "checkbox" ? input.checked : Number(input.value);
          if (input.type !== "checkbox" && (!Number.isInteger(value) || value < Number(input.min) || value > Number(input.max))) return;
          const properties = {engine_time:"_engineRuntime",temperature:"_comfortTemperature",climate_time:"_comfortRuntime",climate_enabled:"_climateEnabled"};
          if (properties[key]) this[properties[key]] = value;
          else if (key.endsWith("_enabled")) this._seatEnabled[key.replace("_enabled","")] = value;
          else this._seatSettings[key === "seat_time" ? "operation_time" : key] = value;
          this._comfortStart = true;
          this._saveCardSettings({[key]:value,comfort_start:true});
          this._render();
        });
      });
      this.shadowRoot.getElementById("preparation-start")?.addEventListener("click", () => {
        if (!this._entryId || this._busy.size || this._remoteCommandInProgress() || this._isUnavailable("engine") || this._isOn("engine")) return;
        const data = this._preparationData();
        if (!this._confirm(`Запустить подготовку? ${this._profileSummary()}. Команды выполняются по очереди.`)) return;
        this._runBusy("preparation", () => this._hass.callService(INTEGRATION,"start_with_comfort",data));
      });
      this.shadowRoot.getElementById("comfort-start")?.addEventListener("change", event => {
        this._comfortStart = event.target.checked;
        this._saveCardSettings({comfort_start:this._comfortStart});
        this._comfortTemperature ??= Number(this._state("climate")?.attributes?.temperature ?? 22);
        this._comfortRuntime ??= Number(this._state("climateRuntime")?.state ?? 15);
        if (!Number.isFinite(this._comfortTemperature)) this._comfortTemperature = 22;
        if (!Number.isFinite(this._comfortRuntime)) this._comfortRuntime = 15;
        this._render();
      });
      this.shadowRoot.querySelectorAll("[data-seat-enable]").forEach(input => input.addEventListener("change", () => {
        this._seatEnabled[input.dataset.seatEnable] = input.checked;
        this._saveCardSettings({[`${input.dataset.seatEnable}_enabled`]:input.checked});
        this.shadowRoot.querySelector(`[data-seat-setting="${input.dataset.seatEnable}"]`).disabled = !input.checked;
      }));
      this.shadowRoot.querySelectorAll("[data-seat-setting]").forEach(input => {
        input.addEventListener("change", () => this._saveCardSettings({[input.dataset.seatSetting === "operation_time" ? "seat_time" : input.dataset.seatSetting]:Number(input.value)}));
        input.addEventListener("input", () => {
          const value = Number(input.value);
          const maximum = input.dataset.seatSetting === "operation_time" ? 10 : 3;
          const minimum = 1;
          if (!Number.isInteger(value) || value < minimum || value > maximum) {
            input.value = this._seatSettings[input.dataset.seatSetting];
            return;
          }
          this._seatSettings[input.dataset.seatSetting] = value;
          if (input.dataset.seatSetting === "operation_time") this.shadowRoot.querySelector("[data-seat-time]").textContent = `${value} мин`;
        });
      });
      this.shadowRoot.querySelectorAll("[data-action]").forEach((button) =>
        button.addEventListener("click", () =>
          this._handleAction(button.dataset.action)
        )
      );

      this.shadowRoot.querySelectorAll("[data-temp-step]").forEach((button) =>
        button.addEventListener("click", () =>
          this._changeTemperature(Number(button.dataset.tempStep))
        )
      );

      const runtime = this.shadowRoot.getElementById("runtime");
      if (runtime) {
        runtime.addEventListener("change", () =>
          this._setRuntime(Number(runtime.value))
        );
      }

      const engineRuntime = this.shadowRoot.getElementById("engine-runtime");
      if (engineRuntime) {
        engineRuntime.addEventListener("change", () => this._saveCardSettings({engine_time:Number(engineRuntime.value)}));
        engineRuntime.addEventListener("input", () => {
          const value = Number(engineRuntime.value);
          if (!Number.isFinite(value)) return;
          this._engineRuntime = value;
          const label = this.shadowRoot.getElementById("engine-runtime-label");
          if (label) label.textContent = `${value} мин`;
          const rightValue = engineRuntime.parentElement?.querySelector("b");
          if (rightValue) rightValue.textContent = `${value} мин`;
        });
      }
    }

    _confirm(message) {
      if (this._config.confirm_controls === false) return true;
      return window.confirm(message);
    }

    async _runBusy(key, fn, onSuccess = null) {
      if (this._busy.has(key)) return;
      this._busy.add(key);
      this._render();
      try {
        await this._awaitResponse(Promise.resolve().then(fn), key === "profiles" ? 30000 : key === "refresh" ? 150000 : (key === "preparation" || (key === "engine" && this._comfortStart)) ? 1800000 : 600000);
        if (onSuccess) onSuccess();
      } catch (err) {
        console.error(`[GWM RU Card] ${key} failed`, err);
        alert(`GWM RU: ${err?.message || String(err)}`);
      } finally {
        this._busy.delete(key);
        this._render();
      }
    }

    async _handleAction(action) {
      if (!this._hass) return;

      const engineOn = this._isOn("engine");
      const unlocked = this._isOn("unlocked");
      const climateOn =
        this._isOn("climateOn") ||
        this._state("climate")?.state === "heat_cool";
      const trunkOpen = this._isOn("trunk");
      const windowsOpen = this._isOn("windows");

      if (action === "engine") {
        const runtime = Math.min(
          30,
          Math.max(5, Number(this._engineRuntime) || 15)
        );
        if (!engineOn) {
          const blockers = [];
          if (unlocked) blockers.push("автомобиль не закрыт");
          if (this._isOn("doors")) blockers.push("открыта дверь");
          if (trunkOpen) blockers.push("открыт багажник");
          if (blockers.length) {
            alert(
              `GWM RU: запуск сейчас недоступен — ${blockers.join(", ")}. Обновите данные после изменения состояния автомобиля.`
            );
            return;
          }
        }
        const message = engineOn
          ? "Остановить двигатель?"
          : `Запустить двигатель на ${runtime} мин${this._comfortStart ? " с выбранным климатом и подогревами (по очереди)" : ""}? Перед отправкой интеграция ещё раз проверит состояние автомобиля.`;
        if (!this._confirm(message)) return;
        return this._runBusy(action, () =>
          this._hass.callService(
            INTEGRATION,
            engineOn ? "engine_stop" : this._comfortStart ? "start_with_comfort" : "engine_start",
            engineOn ? {entry_id:this._entryId} : this._comfortStart ? this._preparationData() : { entry_id:this._entryId, operation_time: runtime }
          )
        );
      }

      if (action === "lock") {
        if (!this._confirm(unlocked ? "Закрыть автомобиль?" : "Разблокировать автомобиль?")) return;
        return this._runBusy(action, () =>
          this._hass.callService(INTEGRATION, unlocked ? "lock_vehicle" : "unlock_vehicle", {
            entry_id: this._entryId,
          })
        );
      }

      if (action === "climate") {
        const entityId = this._entities.climate;
        if (!entityId) {
          return alert("GWM RU: сущность климата не найдена");
        }
        if (
          !this._confirm(
            climateOn
              ? "Выключить кондиционер?"
              : "Запустить кондиционер? На автомобиле с ДВС может запуститься двигатель."
          )
        ) {
          return;
        }
        return this._runBusy(action, () =>
          this._hass.callService(
            "climate",
            climateOn ? "turn_off" : "turn_on",
            { entity_id: entityId }
          )
        );
      }

      if (action === "trunk") {
        if (
          !this._confirm(
            trunkOpen ? "Закрыть багажник?" : "Открыть багажник?"
          )
        ) {
          return;
        }
        return this._runBusy(action, () =>
          this._hass.callService(
            INTEGRATION,
            trunkOpen ? "close_trunk" : "open_trunk",
            {}
          )
        );
      }

      if (action === "seat-heating") {
        if (!this._entryId) return;
        const data = {entry_id: this._entryId, operation_time: this._seatSettings.operation_time};
        if (this._featureEnabled("seat_heat_driver")) data.driver = this._seatEnabled.driver ? this._seatSettings.driver : 0;
        if (this._featureEnabled("seat_heat_passenger")) data.passenger = this._seatEnabled.passenger ? this._seatSettings.passenger : 0;
        return this._runBusy(action, () => this._hass.callService(INTEGRATION, "set_seat_heating", data));
      }

      if (action === "windows") {
        const open = this._openWindows();
        const shouldClose = windowsOpen || open.length > 0;
        const message = shouldClose
          ? `Закрыть все окна${open.length ? `? Сейчас открыты: ${open.join(", ")}.` : "?"}`
          : "Приоткрыть окна для проветривания? Команда ещё не проверена на автомобиле.";
        if (!this._confirm(message)) return;
        return this._runBusy(action, () =>
          this._hass.callService(
            INTEGRATION,
            shouldClose ? "close_windows" : "open_windows",
            {entry_id: this._entryId}
          )
        );
      }

      if (action === "refresh") {
        const entityId = this._entities.refresh;
        if (!entityId) {
          return alert("GWM RU: кнопка обновления не найдена");
        }
        return this._runBusy(action, () =>
          this._hass.callService("button", "press", { entity_id: entityId })
        );
      }

      if (action === "sunroof") {
        return this._toggleRoof(
          action,
          "sunroofOpen",
          "open_sunroof",
          "close_sunroof",
          "панораму"
        );
      }

      if (action === "sunshade") {
        return this._toggleRoof(
          action,
          "sunshadeOpen",
          "open_sunshade",
          "close_sunshade",
          "шторку"
        );
      }

      if (action === "steering-heat") {
        return this._toggleComfort(
          action,
          "steeringHeat",
          "steering_wheel_heat_on",
          "steering_wheel_heat_off",
          "обогрев руля"
        );
      }

      if (action === "rear-defrost") {
        return this._toggleComfort(
          action,
          "rearDefrost",
          "rear_defrost_on",
          "rear_defrost_off",
          "обогрев заднего стекла"
        );
      }

      if (action === "front-defrost") {
        return this._toggleComfort(
          action,
          "frontDefrost",
          "front_defrost_on",
          "front_defrost_off",
          "обдув лобового стекла"
        );
      }
    }

    async _toggleRoof(action, assumedKey, openService, closeService, label) {
      let current = this._assumed[assumedKey];
      if (current === undefined) {
        const open = window.confirm(
          `${label[0].toUpperCase()}${label.slice(1)}: ОК — открыть, Отмена — закрыть.`
        );
        current = !open;
      }
      const nextOpen = !current;
      const service = nextOpen ? openService : closeService;
      if (
        this._config.confirm_controls !== false &&
        !this._confirm(`${nextOpen ? "Открыть" : "Закрыть"} ${label}?`)
      ) {
        return;
      }
      return this._runBusy(
        action,
        () => this._hass.callService(INTEGRATION, service, {}),
        () => {
          this._assumed[assumedKey] = nextOpen;
        }
      );
    }

    async _toggleComfort(action, key, onService, offService, label) {
      const isOn = this._featureOn(key);
      const nextOn = !isOn;
      if (!this._confirm(`${nextOn ? "Включить" : "Выключить"} ${label}?`)) {
        return;
      }

      return this._runBusy(
        action,
        () =>
          this._hass.callService(
            INTEGRATION,
            nextOn ? onService : offService,
            {}
          ),
        () => {
          this._assumed[key] = nextOn;
        }
      );
    }

    async _changeTemperature(step) {
      if (this._comfortStart || this._selectedProfile) {
        this._comfortTemperature = Math.min(32, Math.max(16, this._comfortTemperature + step));
        this._saveCardSettings({temperature:this._comfortTemperature});
        this._render();
        return;
      }
      const climate = this._state("climate");
      const entityId = this._entities.climate;
      if (!climate || !entityId) return;
      const current = Number(this._comfortTemperature ?? climate.attributes?.temperature ?? 22);
      const min = Number(climate.attributes?.min_temp ?? 16);
      const max = Number(climate.attributes?.max_temp ?? 32);
      const next = Math.min(max, Math.max(min, current + step));
      this._comfortTemperature = next;
      this._saveCardSettings({temperature:next});
      await this._runBusy("temperature", () =>
        this._hass.callService("climate", "set_temperature", {
          entity_id: entityId,
          temperature: next,
        })
      );
    }

    async _setRuntime(value) {
      if (!Number.isInteger(value) || value < 5 || value > 30) return;
      this._comfortRuntime = value;
      this._saveCardSettings({climate_time:value});
      if (this._comfortStart || this._selectedProfile) {
        this._comfortRuntime = Math.min(30, Math.max(5, value));
        this._render();
        return;
      }
      const entityId = this._entities.climateRuntime;
      if (!entityId || !Number.isFinite(value)) return;
      await this._runBusy("runtime", () =>
        this._hass.callService("number", "set_value", {
          entity_id: entityId,
          value,
        })
      );
    }
  }

  if (!customElements.get("gwm-vehicle-card")) {
    customElements.define("gwm-vehicle-card", GwmVehicleCard);
  }

  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === "gwm-vehicle-card")) {
    window.customCards.push({
      type: "gwm-vehicle-card",
      name: "GWM RU",
      description: "Карточка автомобиля автомобиля GWM для интеграции GWM RU",
      preview: true,
      documentationURL: "https://github.com/roblencheg/HAVAL_H3",
    });
  }

  console.info(
    `%c GWM RU CARD %c ${CARD_VERSION} `,
    "background:#1976d2;color:white;font-weight:bold;padding:2px 6px;border-radius:3px",
    "background:#263238;color:white;padding:2px 6px;border-radius:3px"
  );
})();
