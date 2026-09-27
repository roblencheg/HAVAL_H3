/* GWM RU primary card visual editor v0.1.0-beta.25 */
(() => {
  const CARD_VERSION = "0.1.0-beta.25";

  const CONTROL_OPTIONS = [
    ["engine", "Двигатель"],
    ["lock", "Центральный замок"],
    ["trunk", "Багажник"],
    ["windows", "Окна"],
    ["climate", "Климат / кондиционер"],
    ["refresh", "Обновить данные"],
  ];

  const INFO_OPTIONS = [
    ["fuel_liters", "Топливо, литры"],
    ["fuel_percent", "Топливо, проценты"],
    ["range", "Запас хода"],
    ["mileage", "Пробег"],
    ["alerts", "Предупреждения дверей / окон / багажника"],
    ["tires", "Шины: давление и температура"],
    ["tbox_header", "T-Box Online / Offline в заголовке"],
    ["tbox", "T-Box в разделе «Система»"],
    ["gsm", "Уровень GSM"],
    ["gps", "GPS"],
    ["last_command", "Последняя удалённая команда"],
    ["last_update", "Время последнего обновления"],
    ["seat_driver", "Подогрев сиденья водителя"],
    ["seat_passenger", "Подогрев сиденья пассажира"],
  ];

  const DETAIL_OPTIONS = [
    ["engine_runtime", "Таймер удалённого запуска двигателя"],
    ["climate_temperature", "Температура климата"],
    ["climate_runtime", "Таймер климата"],
  ];

  const DEFAULT_CONTROLS = CONTROL_OPTIONS.map(([value]) => value);
  const DEFAULT_INFO = INFO_OPTIONS.map(([value]) => value);
  const DEFAULT_DETAILS = DETAIL_OPTIONS.map(([value]) => value);

  const FEATURE_BY_INFO = {
    seat_driver: "seat_heat_driver",
    seat_passenger: "seat_heat_passenger",
  };

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  class GwmVehicleCardEditor extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._config = {};
      this._hass = null;
    }

    set hass(hass) {
      this._hass = hass;
      this._syncProfileEditor();
    }

    setConfig(config) {
      this._config = {
        controls: [...DEFAULT_CONTROLS],
        info: [...DEFAULT_INFO],
        details: [...DEFAULT_DETAILS],
        confirm_controls: true,
        engine_runtime: 15,
        ...config,
      };
      for (const [key, supported] of [["controls", DEFAULT_CONTROLS], ["info", DEFAULT_INFO], ["details", DEFAULT_DETAILS]]) {
        if (Array.isArray(this._config[key])) {
          this._config[key] = this._config[key].filter(value => supported.includes(value));
        }
      }
      this._render();
    }

    _featureFlags() {
      if (!this._hass) return {};
      const entity = Object.values(this._hass.states || {}).find((state) =>
        String(state?.entity_id || "").startsWith("sensor.") &&
        state?.attributes &&
        Object.prototype.hasOwnProperty.call(state.attributes, "sunroof") &&
        Object.prototype.hasOwnProperty.call(state.attributes, "steering_wheel_heat")
      );
      return entity?.attributes || {};
    }

    _syncProfileEditor() {
      const mount = this.shadowRoot.querySelector("#preparation-profiles");
      if (!mount) return;
      if (!customElements.get("gwm-vehicle-card")) {
        if (!this._waitingForCard) {
          this._waitingForCard = true;
          customElements.whenDefined("gwm-vehicle-card").then(() => {
            this._waitingForCard = false;
            this._syncProfileEditor();
          });
        }
        return;
      }
      if (!this._profileEditor) {
        this._profileEditor = document.createElement("gwm-vehicle-card");
        // Share vehicle resolution and profile storage with the dashboard card.
        // This instance renders only profile settings, without vehicle controls.
        this._profileEditor._profileEditorHost = true;
        this._profileEditor.addEventListener("profile-visibility-changed", event => {
          event.stopPropagation();
          this._emit({...this._config, visible_profiles:event.detail.profiles});
        });
      }
      const token = JSON.stringify(this._config);
      if (token !== this._profileConfigToken) {
        this._profileConfigToken = token;
        this._profileEditor.setConfig(this._config);
      }
      if (this._hass) this._profileEditor.hass = this._hass;
      if (this._profileEditor.parentElement !== mount) mount.append(this._profileEditor);
    }

    _available(option, kind) {
      const flags = this._featureFlags();
      const capability = kind === "controls"
        ? undefined
        : FEATURE_BY_INFO[option];
      if (!capability || !(capability in flags)) return true;
      return flags[capability] !== false;
    }

    _toggleList(key, value, checked) {
      const fallback = key === "controls" ? DEFAULT_CONTROLS : key === "info" ? DEFAULT_INFO : DEFAULT_DETAILS;
      const current = Array.isArray(this._config[key]) ? [...this._config[key]] : [...fallback];
      const next = checked
        ? (current.includes(value) ? current : [...current, value])
        : current.filter((item) => item !== value);
      this._emit({ ...this._config, [key]: next });
    }

    _emit(config) {
      this._config = config;
      this.dispatchEvent(new CustomEvent("config-changed", {
        detail: { config },
        bubbles: true,
        composed: true,
      }));
      this._render();
    }

    _renderGroup(title, key, options) {
      const fallback = key === "controls" ? DEFAULT_CONTROLS : key === "info" ? DEFAULT_INFO : DEFAULT_DETAILS;
      const selected = Array.isArray(this._config[key]) ? this._config[key] : fallback;
      return `
        <section>
          <h4>${escapeHtml(title)}</h4>
          <div class="grid">
            ${options.map(([value, label]) => {
              const available = this._available(value, key);
              return `
                <label class="check ${available ? "" : "unavailable"}">
                  <input type="checkbox" data-list="${key}" data-value="${value}" ${selected.includes(value) ? "checked" : ""} ${available ? "" : "disabled"}>
                  <span>${escapeHtml(label)}${available ? "" : " · нет в комплектации"}</span>
                </label>`;
            }).join("")}
          </div>
        </section>`;
    }

    _render() {
      if (!this.shadowRoot) return;
      const title = this._config.title || "";
      const drivetrain = this._config.drivetrain || "";
      const engineRuntime = Math.min(30, Math.max(5, Number(this._config.engine_runtime) || 15));
      this.shadowRoot.innerHTML = `
        <style>
          :host { display:block; }
          .editor { display:grid; gap:16px; padding:4px 0 12px; }
          section { display:grid; gap:8px; }
          h4 { margin:0; font-size:14px; color:var(--primary-text-color); }
          .fields { display:grid; grid-template-columns:minmax(0,1fr) minmax(120px,.45fr); gap:12px; }
          .field { display:grid; gap:6px; color:var(--secondary-text-color); font-size:12px; }
          input[type="text"], input[type="number"] {
            width:100%; min-height:40px; border-radius:8px; padding:0 10px;
            border:1px solid var(--divider-color); background:var(--card-background-color);
            color:var(--primary-text-color); font:inherit; box-sizing:border-box;
          }
          .grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:7px 14px; }
          .check { display:flex; align-items:center; gap:8px; min-height:30px; font-size:13px; color:var(--primary-text-color); }
          .check.unavailable { opacity:.5; }
          .note { padding:10px 12px; border-radius:10px; background:color-mix(in srgb,var(--primary-color) 7%,transparent); color:var(--secondary-text-color); font-size:12px; line-height:1.4; }
          @media (max-width:520px) { .grid,.fields { grid-template-columns:1fr; } }
        </style>
        <div class="editor">
          <div class="fields">
            <label class="field">
              Название карточки (необязательно)
              <input id="title" type="text" value="${escapeHtml(title)}" placeholder="Haval Vehicle">
            </label>
            <label class="field">
              Привод (необязательно)
              <input id="drivetrain" type="text" value="${escapeHtml(drivetrain)}" placeholder="2WD / 4WD">
            </label>
          </div>
          <label class="field">
            Таймер запуска по умолчанию, мин
            <input id="engine-runtime" type="number" min="5" max="30" step="1" value="${engineRuntime}">
          </label>
          <label class="check">
            <input id="confirm-controls" type="checkbox" ${this._config.confirm_controls !== false ? "checked" : ""}>
            <span>Подтверждать удалённые команды</span>
          </label>
          <div id="preparation-profiles"></div>
          <label class="check">
            <input id="collapse-climate" type="checkbox" ${this._config.collapse_climate ? "checked" : ""}>
            <span>Сворачивать блок климата</span>
          </label>
          ${this._renderGroup("Кнопки управления", "controls", CONTROL_OPTIONS)}
          ${this._renderGroup("Датчики и информация", "info", INFO_OPTIONS)}
          ${this._renderGroup("Дополнительные панели", "details", DETAIL_OPTIONS)}
          <div class="note">Настройки комплектации в GWM RU → Настроить имеют приоритет. Отсутствующее оборудование нельзя принудительно показать карточкой. Существующие карточки без этих параметров продолжают показывать полный прежний набор элементов.</div>
        </div>`;

      this._syncProfileEditor();

      this.shadowRoot.querySelectorAll("[data-list]").forEach((input) => {
        input.addEventListener("change", () => this._toggleList(input.dataset.list, input.dataset.value, input.checked));
      });
      this.shadowRoot.getElementById("collapse-climate")?.addEventListener("change", event => {
        this._emit({...this._config, collapse_climate:event.target.checked});
      });
      this.shadowRoot.getElementById("confirm-controls")?.addEventListener("change", (event) => {
        this._emit({ ...this._config, confirm_controls: event.target.checked });
      });
      this.shadowRoot.getElementById("title")?.addEventListener("change", (event) => {
        const value = String(event.target.value || "").trim();
        const next = { ...this._config };
        if (value) next.title = value; else delete next.title;
        this._emit(next);
      });
      this.shadowRoot.getElementById("drivetrain")?.addEventListener("change", (event) => {
        const value = String(event.target.value || "").trim().toUpperCase();
        const next = { ...this._config };
        if (value) next.drivetrain = value; else delete next.drivetrain;
        this._emit(next);
      });
      this.shadowRoot.getElementById("engine-runtime")?.addEventListener("change", (event) => {
        const value = Math.min(30, Math.max(5, Number(event.target.value) || 15));
        this._emit({ ...this._config, engine_runtime: value });
      });
    }
  }

  if (!customElements.get("gwm-vehicle-card-editor")) {
    customElements.define("gwm-vehicle-card-editor", GwmVehicleCardEditor);
  }

  function selected(config, key, fallback) {
    return new Set(Array.isArray(config?.[key]) ? config[key] : fallback);
  }

  function sectionByTitle(root, title) {
    return [...root.querySelectorAll(".section")].find((section) =>
      section.querySelector(".section-title")?.textContent?.trim() === title
    );
  }

  function setVisible(node, visible) {
    if (node) node.style.display = visible ? "" : "none";
  }

  function applyVisibility(card) {
    const root = card.shadowRoot;
    if (!root?.querySelector("ha-card")) return;

    const controls = selected(card._config, "controls", DEFAULT_CONTROLS);
    const info = selected(card._config, "info", DEFAULT_INFO);
    const details = selected(card._config, "details", DEFAULT_DETAILS);

    const statsMap = [
      ["fuel_liters", "Топливо л"],
      ["fuel_percent", "Топливо %"],
      ["range", "Запас"],
      ["mileage", "Пробег"],
    ];
    const stats = root.querySelector(".stats");
    statsMap.forEach(([key, label]) => {
      const tile = [...(stats?.querySelectorAll(".stat") || [])].find((node) => node.querySelector("span")?.textContent?.trim() === label);
      setVisible(tile, info.has(key));
    });
    if (stats) setVisible(stats, statsMap.some(([key]) => info.has(key)));

    setVisible(root.querySelector(".chips"), info.has("alerts"));
    setVisible(root.querySelector(".header .online"), info.has("tbox_header"));

    const controlSection = sectionByTitle(root, "Управление");
    const actionMap = {
      engine: "engine",
      lock: "lock",
      trunk: "trunk",
      windows: "windows",
      sunroof: "sunroof",
      sunshade: "sunshade",
      refresh: "refresh",
    };
    Object.entries(actionMap).forEach(([key, action]) => {
      setVisible(controlSection?.querySelector(`[data-action="${action}"]`), controls.has(key));
    });
    const engineTimer = controlSection?.querySelector(".timer-panel");
    setVisible(engineTimer, controls.has("engine") && details.has("engine_runtime"));
    const visibleMainControl = Object.keys(actionMap).some((key) => controls.has(key));
    setVisible(controlSection, visibleMainControl || (controls.has("engine") && details.has("engine_runtime")));

    const climateSection = sectionByTitle(root, "Климат");
    const panel = climateSection?.querySelector(".climate-panel");
    setVisible(panel?.querySelector(".climate-top"), controls.has("climate"));
    setVisible(panel?.querySelector(".climate-main"), details.has("climate_temperature"));
    setVisible(panel?.querySelector(":scope > .runtime"), details.has("climate_runtime"));

    const comfort = panel?.querySelector(".comfort");
    const comfortActions = {
      steering: "steering-heat",
      rear_defrost: "rear-defrost",
      front_defrost: "front-defrost",
    };
    Object.entries(comfortActions).forEach(([key, action]) => {
      setVisible(comfort?.querySelector(`[data-action="${action}"]`), controls.has(key));
    });
    const readonlyMap = {
      seat_driver: "Сиденье водителя",
      seat_passenger: "Сиденье пассажира",
      windscreen_heat: "Обогрев лобового",
    };
    Object.entries(readonlyMap).forEach(([key, title]) => {
      const node = [...(comfort?.querySelectorAll(".control") || [])].find((item) => item.querySelector("strong")?.textContent?.trim() === title);
      setVisible(node, info.has(key));
    });
    const comfortWanted = Object.keys(comfortActions).some((key) => controls.has(key)) || Object.keys(readonlyMap).some((key) => info.has(key));
    setVisible(comfort, comfortWanted);
    const climateWanted = controls.has("climate") || details.has("climate_temperature") || details.has("climate_runtime") || comfortWanted;
    setVisible(climateSection, climateWanted);

    setVisible(sectionByTitle(root, "Шины"), info.has("tires"));

    const systemSection = sectionByTitle(root, "Система");
    const system = systemSection?.querySelector(".system");
    const systemItems = [...(system?.querySelectorAll(".system-item") || [])];
    const systemKeys = ["tbox", "gsm", "gps", "last_command"];
    systemKeys.forEach((key, index) => setVisible(systemItems[index], info.has(key)));

    let updateItem = system?.querySelector('[data-gwm-extra="last-update"]');
    if (info.has("last_update")) {
      if (!updateItem && system) {
        updateItem = document.createElement("span");
        updateItem.className = "system-item";
        updateItem.dataset.gwmExtra = "last-update";
        updateItem.innerHTML = `<ha-icon icon="mdi:clock-outline"></ha-icon><span>${escapeHtml(typeof card._relativeUpdate === "function" ? card._relativeUpdate() : "Время обновления неизвестно")}</span>`;
        system.appendChild(updateItem);
      }
      setVisible(updateItem, true);
    } else {
      setVisible(updateItem, false);
    }
    const systemWanted = systemKeys.some((key) => info.has(key)) || info.has("last_update");
    setVisible(systemSection, systemWanted);
  }

  function patchCard(Card) {
    Card.getConfigElement = () => document.createElement("gwm-vehicle-card-editor");
    Card.getStubConfig = () => ({
      controls: [...DEFAULT_CONTROLS],
      info: [...DEFAULT_INFO],
      details: [...DEFAULT_DETAILS],
    });

    if (!Card.prototype._gwmVisualEditorPatched) {
      const originalRender = Card.prototype._render;
      Card.prototype._render = function patchedRender(...args) {
        const result = originalRender.apply(this, args);
        try {
          applyVisibility(this);
        } catch (err) {
          console.error("[GWM RU Card Editor] visibility update failed", err);
        }
        return result;
      };
      Card.prototype._gwmVisualEditorPatched = true;
    }
  }

  const existingCard = customElements.get("gwm-vehicle-card");
  if (existingCard) {
    patchCard(existingCard);
  } else {
    customElements.whenDefined("gwm-vehicle-card")
      .then(() => {
        const Card = customElements.get("gwm-vehicle-card");
        if (Card) patchCard(Card);
      })
      .catch((err) => {
        console.error("[GWM RU Card Editor] card registration wait failed", err);
      });
  }

  console.info(
    `%c GWM RU CARD EDITOR %c ${CARD_VERSION} `,
    "background:#1976d2;color:white;font-weight:bold;padding:2px 6px;border-radius:3px",
    "background:#263238;color:white;padding:2px 6px;border-radius:3px"
  );
})();
