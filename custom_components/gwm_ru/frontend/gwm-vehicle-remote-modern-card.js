/* GWM RU Studio remotes. SPDX-License-Identifier: GPL-3.0-only
 * Reuses the StarLine-derived artwork and the existing remote command logic.
 * See LICENSE.starline and THIRD_PARTY_NOTICES.md.
 */
(() => {
  const Base = customElements.get('gwm-vehicle-remote-card');
  if (!Base) throw new Error('GWM RU Studio requires the base remote card');

  // Both layouts share telemetry resolution, capability checks, confirmations,
  // busy states and service calls with the original card.
  class StudioRemote extends Base {
    static getGridOptions() { return {columns:12, rows:10, min_columns:6}; }
    getCardSize() { return 10; }
    _render() {
      if (!this._hass) { super._render(); return; }
      const known = !this._isUnavailable('tbox');
      const online = known && this._isOn('tbox');
      const engineKnown = !this._isUnavailable('engine');
      const engine = this._isOn('engine');
      const lockedKnown = !this._isUnavailable('unlocked');
      const locked = lockedKnown && !this._isOn('unlocked');
      const dark = this._config.dark ?? this._hass.themes?.darkMode ?? false;
      const wide = this.constructor.horizontal === true;
      const markup = `
        <style>
          :host{display:block;font-family:var(--paper-font-body1_-_font-family,Roboto,system-ui,sans-serif);container-type:inline-size;--studio-accent:var(--primary-color,#03a9f4)}
          *{box-sizing:border-box}
          ha-card{display:block;overflow:hidden;color:var(--primary-text-color,#212121);background:var(--ha-card-background,var(--card-background-color,#fff));border:1px solid var(--ha-card-border-color,var(--divider-color,#ddd));border-radius:28px;box-shadow:var(--ha-card-box-shadow,none)}
          .studio{padding:20px;display:grid;gap:22px;min-width:0;--studio-surface:var(--secondary-background-color,#f3f4f6);--studio-muted:var(--secondary-text-color,#727272)}
          .dark{--studio-surface:var(--secondary-background-color,#252a32);--studio-muted:var(--secondary-text-color,#a5adb4)}
          header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
          h2{margin:0;font-size:clamp(24px,6cqi,34px);line-height:1.1;letter-spacing:-.04em;font-weight:600;overflow-wrap:anywhere}
          .connection{margin-left:auto;flex:0 0 auto;display:flex;align-items:center;gap:7px;border:1px solid var(--divider-color,#ddd);border-radius:99px;padding:8px 10px;font-size:11px;line-height:16px}
          .dot{width:6px;height:6px;border-radius:50%;background:var(--studio-muted)}
          .online .dot{background:var(--success-color,#43a047)}.offline .dot{background:var(--error-color,#db4437)}
          .hero{min-width:0;display:flex;flex-direction:column}
          .vehicle-scene{position:relative;display:grid;place-items:center;background:var(--studio-surface);border-radius:24px;margin-top:18px;padding:16px 16px 10px;min-height:200px;color:var(--studio-accent);overflow:hidden}
          .scene-top{width:100%;display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:11px;color:var(--studio-muted)}
          .security-label{display:flex;align-items:center;gap:6px;color:var(--primary-text-color)}
          .security-label ha-icon{--mdc-icon-size:15px}
          .starline-car{width:min(100%,290px);height:auto;display:block;margin:8px auto 0}
          .security{opacity:.24}.door-indicator,.trunk-indicator,.exhaust,.climate-indicator{transition:opacity .2s}
          .smoke{animation:smoke 1.5s steps(1,end) infinite;opacity:0}.smoke-2{animation-delay:-1s}.smoke-3{animation-delay:-.5s}
          .fan{animation:fanSpin 2s linear infinite}.exhaust[opacity="0"] .smoke,.climate-indicator[opacity="0"] .fan{animation:none}
          @keyframes smoke{0%,100%{opacity:1}33.333%,99.999%{opacity:0}}@keyframes fanSpin{to{transform:rotate(360deg)}}
          .hero-footer{display:flex;align-items:center;justify-content:space-between;gap:10px;width:100%;padding:8px 0 0}
          .engine-state{display:flex;align-items:center;gap:7px;font-size:12px;line-height:18px;color:var(--primary-text-color)}
          .engine-state ha-icon{--mdc-icon-size:18px;color:var(--studio-accent)}
          .update{font-size:10px;color:var(--studio-muted);text-align:right;line-height:15px}
          .control-zone,.sensor-zone{min-width:0}
          .section-label{display:flex;align-items:center;gap:10px;font-size:10px;letter-spacing:.12em;text-transform:uppercase;font-weight:600;color:var(--studio-muted);margin:0 0 12px}
          .section-label:after{content:'';height:1px;flex:1;background:var(--divider-color,#ddd)}
          .remote-controls{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
          .remote-action{appearance:none;display:flex;align-items:center;gap:10px;min-width:0;min-height:58px;padding:10px;border:1px solid transparent;border-radius:18px;background:var(--studio-surface);color:var(--primary-text-color);font:inherit;text-align:left;cursor:pointer;transition:background .18s,transform .12s,border-color .18s}
          .remote-action>span:last-child{font-size:13px;line-height:18px;font-weight:500;overflow-wrap:anywhere}
          .action-circle{display:grid;place-items:center;width:34px;height:34px;flex:0 0 34px;border-radius:12px;background:color-mix(in srgb,var(--studio-accent) 10%,transparent);color:var(--studio-accent)}
          .action-circle ha-icon{--mdc-icon-size:21px}
          .remote-action[data-control="engine"]{grid-column:1/-1;min-height:68px;background:var(--studio-accent);color:var(--text-primary-color,#fff);padding:12px 16px;border-radius:20px}
          .remote-action[data-control="engine"] .action-circle{background:color-mix(in srgb,var(--text-primary-color,#fff) 18%,transparent);color:inherit;width:42px;height:42px;flex-basis:42px;border-radius:14px}
          .remote-action[data-control="engine"]>span:last-child{font-size:16px;font-weight:600}
          .remote-action.active:not([data-control="engine"]){border-color:color-mix(in srgb,var(--studio-accent) 35%,transparent);background:color-mix(in srgb,var(--studio-accent) 10%,var(--studio-surface))}
          .remote-action.warn .action-circle{color:var(--warning-color,#f9a825)}
          .remote-action:disabled{opacity:.45;cursor:default}.remote-action.busy{opacity:.7}.remote-action.busy .action-circle{animation:fanSpin 2s linear infinite}
          .remote-action:not(:disabled):hover{border-color:var(--studio-accent);filter:brightness(.96)}
          .remote-action:not(:disabled):active{transform:scale(.98)}
          .remote-action:focus-visible{outline:2px solid var(--studio-accent);outline-offset:3px}
          .status-dock,.info-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
          .info-grid{margin-top:10px}
          .status-tile,.info-tile{display:flex;align-items:center;gap:8px;min-width:0;min-height:58px;padding:10px;border:1px solid var(--divider-color,#ddd);border-radius:16px;background:transparent}
          .status-icon{display:grid;place-items:center;flex:0 0 24px;color:var(--studio-muted)}
          .status-icon ha-icon,.info-tile>ha-icon{--mdc-icon-size:20px;color:var(--studio-muted)}
          .status-copy,.info-tile>div{display:grid;gap:3px;min-width:0}
          .status-copy small,.info-tile small{font-size:10px;line-height:14px;color:var(--studio-muted)}
          .status-copy strong,.info-tile strong{font-size:13px;font-weight:500;line-height:18px;overflow-wrap:anywhere}
          .status-tile.warn,.status-tile.unlock{border-color:var(--warning-color,#f9a825)}
          .status-tile.warn .status-icon,.status-tile.unlock .status-icon{color:var(--warning-color,#f9a825)}
          .status-tile.climate .status-icon ha-icon{animation:fanSpin 2s linear infinite}
          .wide{grid-template-columns:minmax(230px,.85fr) minmax(360px,1.4fr);grid-template-areas:'hero controls' 'hero sensors';gap:22px 28px;padding:24px}
          .wide .hero{grid-area:hero}.wide .control-zone{grid-area:controls}.wide .sensor-zone{grid-area:sensors}
          .wide .vehicle-scene{flex:1;min-height:260px;align-content:center}
          .wide .scene-top{position:absolute;top:16px;left:16px;width:calc(100% - 32px)}
          .wide .hero-footer{margin-top:16px}
          .wide .remote-controls{grid-template-columns:repeat(3,minmax(0,1fr))}
          .wide .remote-action[data-control="engine"]{grid-column:auto;min-height:58px;padding:10px;border-radius:18px}
          .wide .remote-action[data-control="engine"]>span:last-child{font-size:13px}
          .wide .remote-action[data-control="engine"] .action-circle{width:34px;height:34px;flex-basis:34px;border-radius:12px}
          .wide .status-dock,.wide .info-grid{grid-template-columns:repeat(4,minmax(0,1fr))}
          @container(max-width:800px){.wide{grid-template-columns:1fr;grid-template-areas:'hero' 'controls' 'sensors';padding:20px}.wide .vehicle-scene{min-height:200px}.wide .remote-controls,.wide .status-dock,.wide .info-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.wide .remote-action[data-control="engine"]{grid-column:1/-1}}
          @container(max-width:340px){.studio,.wide{padding:14px;gap:18px}header{flex-wrap:wrap}.connection{padding:5px 8px}.remote-controls,.wide .remote-controls,.status-dock,.info-grid,.wide .status-dock,.wide .info-grid{grid-template-columns:1fr}.vehicle-scene{padding:12px;min-height:180px}.hero-footer{flex-wrap:wrap}}
          @media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important}}
        </style>
        <ha-card><div class="studio ${wide ? 'wide' : ''} ${dark ? 'dark' : ''}">
          <section class="hero">
            <header>${this._title() ? `<h2>${this._escape(this._title())}</h2>` : ""}
              <div class="connection ${known ? online ? 'online' : 'offline' : ''}"><span class="dot"></span>${known ? online ? 'Онлайн' : 'Оффлайн' : 'Нет данных'}</div>
            </header>
            <div class="vehicle-scene">
              <div class="scene-top"><span class="security-label">${this._icon(locked ? 'mdi:shield-lock-outline' : 'mdi:shield-outline')}${lockedKnown ? locked ? 'На охране' : 'Замок открыт' : 'Замок · нет данных'}</span></div>
              ${this._carSvg()}
              <div class="hero-footer"><span class="engine-state">${this._icon('mdi:engine-outline')}${engineKnown ? engine ? 'Двигатель работает' : 'Двигатель выключен' : 'Двигатель · нет данных'}</span><span class="update">${this._escape(this._relativeUpdate())}</span></div>
            </div>
          </section>
          ${this._renderControls()}
          ${this._telemetryIds().length ? `<section class="sensor-zone"><div class="section-label">Телеметрия</div>${this._renderStatuses()}</section>` : ""}
        </div></ha-card>`;
      const template = document.createElement('template');
      template.innerHTML = markup;
      this._syncDom(this.shadowRoot, template.content);
    }
  }
  class StudioHorizontalRemote extends StudioRemote {
    static horizontal = true;
    static getGridOptions() { return {columns:24, rows:6, min_columns:12}; }
    getCardSize() { return 6; }
  }
  for (const [tag, constructor, name] of [
    ['gwm-vehicle-remote-modern-card', StudioRemote, 'GWM RU — Studio · вертикальный'],
    ['gwm-vehicle-remote-modern-horizontal-card', StudioHorizontalRemote, 'GWM RU — Studio · горизонтальный'],
  ]) {
    if (!customElements.get(tag)) customElements.define(tag, constructor);
    window.customCards = window.customCards || [];
    if (!window.customCards.some(card => card.type === tag)) window.customCards.push({type:tag, name, description:'Современный пульт Studio: сцена автомобиля, выразительные команды и отдельная телеметрия. Поддерживает тему Home Assistant.', preview:true, documentationURL:'https://github.com/roblencheg/HAVAL_H3'});
  }
})();
