/* GWM RU alpha.20 entity-surface compatibility layer */
(() => {
  const VERSION = "0.1.0-beta.25";
  const SAFE_CAPABILITIES = new Set([
    "seat_heat_driver",
    "seat_heat_passenger",
    "sunroof",
    "steering_wheel_heat",
    "rear_defrost",
    "front_windscreen_heat",
  ]);
  const SAFE_REMOTE_CONTROLS = new Set([
    "seat_heating",
    "lock",
    "engine",
    "climate",
    "trunk",
    "refresh",
    "steering",
    "rear_defrost",
    "sunroof",
    "sunshade",
  ]);
  const SAFE_REMOTE_STATUSES = new Set([
    "engine",
    "climate",
    "fuel",
    "mileage",
    "doors",
    "windows",
    "trunk",
    "lock",
  ]);
  const SAFE_REMOTE_INFO = new Set([
    "fuel",
    "range",
    "mileage",
    "tires",
    "gsm",
    "gps",
    "climate",
    "update",
  ]);

  const WINDOW_RAW_SOURCE = {
    window1Raw: "window1",
    window2Raw: "window2",
    window3Raw: "window3",
    window4Raw: "window4",
  };

  function makeVirtualState(card, originalState, key) {
    const direct = (name) => originalState.call(card, name);
    const tbox = direct("tbox");
    const refresh = direct("refresh");

    if (key === "unlocked") {
      const lock = direct("lock");
      if (!lock) return undefined;
      if (["unknown", "unavailable"].includes(lock.state)) {
        return { state: lock.state, attributes: {} };
      }
      if (lock.state === "unlocked") return { state: "on", attributes: {} };
      if (lock.state === "locked") return { state: "off", attributes: {} };
      return { state: "unknown", attributes: {} };
    }

    if (key in WINDOW_RAW_SOURCE) {
      const windowState = direct(WINDOW_RAW_SOURCE[key]);
      const raw = windowState?.attributes?.raw_state;
      return raw === undefined || raw === null
        ? undefined
        : { state: String(raw), attributes: {} };
    }

    if (key === "signal") {
      const raw = tbox?.attributes?.signal_level_raw;
      return raw === undefined || raw === null
        ? undefined
        : { state: String(raw), attributes: {} };
    }

    if (key === "modelCode") {
      const value = tbox?.attributes?.model_code_raw;
      return value === undefined || value === null || value === ""
        ? undefined
        : { state: String(value), attributes: {} };
    }

    if (key === "oilQty") {
      const value = tbox?.attributes?.oil_qty_raw;
      return value === undefined || value === null
        ? undefined
        : { state: String(value), attributes: {} };
    }

    if (key === "gps") {
      const available = tbox?.attributes?.gps_available;
      return typeof available === "boolean"
        ? { state: available ? "on" : "off", attributes: {} }
        : undefined;
    }

    if (key === "featureFlags") {
      const flags = tbox?.attributes?.feature_flags;
      return flags && typeof flags === "object"
        ? { state: "configured", attributes: { ...flags } }
        : undefined;
    }

    if (key === "lastUpdate") {
      const value = refresh?.attributes?.last_successful_update;
      return value ? { state: String(value), attributes: {} } : undefined;
    }

    if (key === "lastCommand") {
      const name = refresh?.attributes?.last_command_name;
      const status = refresh?.attributes?.last_command_status;
      const inProgress = refresh?.attributes?.command_in_progress === true;
      if (!name && !status && !inProgress) return undefined;
      const suffix = status === "pending"
        ? "выполняется"
        : status === "success"
          ? "выполнено"
          : status === "error"
            ? "ошибка"
            : status || "";
      return {
        state: [name, suffix].filter(Boolean).join(" — ") || "команда",
        attributes: {
          in_progress: inProgress,
          status,
          result_code: refresh?.attributes?.last_command_result_code,
          result_message: refresh?.attributes?.last_command_result_message,
        },
      };
    }

    return undefined;
  }

  function patchCommon(tagName) {
    customElements.whenDefined(tagName).then(() => {
      const Card = customElements.get(tagName);
      const proto = Card?.prototype;
      if (!proto || proto.__gwmAlpha20Common) return;
      proto.__gwmAlpha20Common = true;

      const originalState = proto._state;
      if (typeof originalState === "function") {
        proto._state = function alpha20State(key) {
          const state = originalState.call(this, key);
          return state || makeVirtualState(this, originalState, key);
        };
      }

      proto._featureEnabled = function alpha20FeatureEnabled(capability) {
        if (!SAFE_CAPABILITIES.has(capability)) return false;
        const flags = this._state?.("featureFlags")?.attributes;
        return !flags || !(capability in flags) || flags[capability] !== false;
      };
    });
  }

  function patchMainCard() {
    const tagName = "gwm-vehicle-card";
    patchCommon(tagName);
    customElements.whenDefined(tagName).then(() => {
      const Card = customElements.get(tagName);
      const proto = Card?.prototype;
      if (!proto || proto.__gwmAlpha20Main) return;
      proto.__gwmAlpha20Main = true;

      const originalResolve = proto._resolveEntities;
      if (typeof originalResolve === "function") {
        proto._resolveEntities = async function alpha20ResolveEntities(...args) {
          const previousEntities = this._entities;
          await originalResolve.apply(this, args);
          if (this._entities === previousEntities) return;
          const entities = this._entities || {};
          const oldFl = entities.windowFl;
          const oldFr = entities.windowFr;
          const oldRl = entities.windowRl;
          const oldRr = entities.windowRr;
          // alpha.16 used the pre-field-test window labels.  alpha.20 fixes the
          // main card without changing the stable binary-sensor unique IDs.
          entities.windowFl = oldFr;
          entities.windowFr = oldFl;
          entities.windowRl = oldRr;
          entities.windowRr = oldRl;
        };
      }

    });
  }

  function patchRemoteCard() {
    const tagName = "gwm-vehicle-remote-card";
    patchCommon(tagName);
    customElements.whenDefined(tagName).then(() => {
      const Card = customElements.get(tagName);
      const proto = Card?.prototype;
      if (!proto || proto.__gwmAlpha20Remote) return;
      proto.__gwmAlpha20Remote = true;

      const originalRenderControls = proto._renderControls;
      if (typeof originalRenderControls === "function") {
        proto._renderControls = function alpha20RenderControls(...args) {
          const previous = this._config?.controls;
          if (this._config) {
            this._config.controls = (Array.isArray(previous) ? previous : [])
              .filter((key) => SAFE_REMOTE_CONTROLS.has(key));
          }
          try {
            return originalRenderControls.apply(this, args);
          } finally {
            if (this._config) this._config.controls = previous;
          }
        };
      }

      const originalRenderStatuses = proto._renderStatuses;
      if (typeof originalRenderStatuses === "function") {
        proto._renderStatuses = function alpha20RenderStatuses(...args) {
          const previous = this._config?.statuses;
          if (this._config) {
            this._config.statuses = (Array.isArray(previous) ? previous : [])
              .filter((key) => SAFE_REMOTE_STATUSES.has(key));
          }
          try {
            return originalRenderStatuses.apply(this, args);
          } finally {
            if (this._config) this._config.statuses = previous;
          }
        };
      }

      const originalRenderInfo = proto._renderInfo;
      if (typeof originalRenderInfo === "function") {
        proto._renderInfo = function alpha20RenderInfo(...args) {
          const previous = this._config?.info;
          if (this._config) {
            this._config.info = (Array.isArray(previous) ? previous : [])
              .filter((key) => SAFE_REMOTE_INFO.has(key));
          }
          try {
            return originalRenderInfo.apply(this, args);
          } finally {
            if (this._config) this._config.info = previous;
          }
        };
      }
    });
  }

  function patchRemoteEditor() {
    const tagName = "gwm-vehicle-remote-card-editor";
    customElements.whenDefined(tagName).then(() => {
      const Editor = customElements.get(tagName);
      const proto = Editor?.prototype;
      if (!proto || proto.__gwmAlpha20Editor) return;
      proto.__gwmAlpha20Editor = true;
      const originalGroup = proto._group;
      if (typeof originalGroup !== "function") return;
      proto._group = function alpha20Group(title, key, options) {
        let filtered = options;
        if (key === "controls") filtered = options.filter(([value]) => SAFE_REMOTE_CONTROLS.has(value));
        if (key === "statuses") filtered = options.filter(([value]) => SAFE_REMOTE_STATUSES.has(value));
        if (key === "info") filtered = options.filter(([value]) => SAFE_REMOTE_INFO.has(value));
        return originalGroup.call(this, title, key, filtered);
      };
    });
  }

  patchMainCard();
  patchRemoteCard();
  patchRemoteEditor();

  console.info(
    `%c GWM RU %c ${VERSION} entity cleanup `,
    "background:#0f1922;color:white;font-weight:bold;padding:2px 6px;border-radius:3px",
    "background:#526474;color:white;padding:2px 6px;border-radius:3px",
  );
})();
