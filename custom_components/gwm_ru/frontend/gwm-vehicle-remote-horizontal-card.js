/*
 * GWM RU Horizontal Animated Remote Card.
 * SPDX-License-Identifier: GPL-3.0-only
 *
 * This card reuses the animated StarLine-derived remote card and presents it
 * in a wide dashboard layout. See LICENSE.starline and THIRD_PARTY_NOTICES.md.
 */
(() => {
  const BASE_TAG = "gwm-vehicle-remote-card";
  const TAG = "gwm-vehicle-remote-horizontal-card";
  const BaseCard = customElements.get(BASE_TAG);

  if (!BaseCard) {
    console.error("[GWM RU] Horizontal remote card: base remote card is not registered");
    return;
  }

  class GwmVehicleRemoteHorizontalCard extends BaseCard {
    static getConfigElement() {
      return document.createElement("gwm-vehicle-remote-card-editor");
    }

    static getGridOptions() {
      return { columns: 12, rows: 5, min_columns: 8, min_rows: 4 };
    }

    getCardSize() {
      return 5;
    }

    _render() {
      super._render();
      if (!this.shadowRoot) return;

      const style = document.createElement("style");
      style.dataset.gwmHorizontal = "true";
      style.textContent = `
        /* Wide layout: animated vehicle on the left, actions on the right. */
        .wrap {
          display:grid !important;
          grid-template-columns:minmax(250px,.9fr) minmax(390px,1.45fr) !important;
          grid-template-areas:
            "hero controls"
            "hero statuses"
            "hero info" !important;
          gap:10px 16px !important;
          align-items:start !important;
          padding:14px 16px !important;
          container-type:inline-size;
        }

        .hero {
          grid-area:hero;
          min-width:0;
          align-self:stretch;
          padding:2px 4px 0;
        }

        .vehicle-name {
          font-size:18px !important;
          line-height:23px !important;
          padding-right:104px !important;
        }

        .connection-card {
          min-width:92px !important;
          padding:5px 9px !important;
          border-radius:16px !important;
          font-size:10px !important;
        }

        .gsm-line { margin-top:2px !important; }

        .starline-car {
          width:min(100%,280px) !important;
          margin:10px auto 0 !important;
        }

        /* Actions remain visually dominant and isolated from passive state. */
        .remote-controls {
          grid-area:controls;
          display:grid !important;
          grid-template-columns:repeat(3,minmax(0,1fr)) !important;
          gap:7px !important;
          max-width:none !important;
          margin:0 !important;
          padding:0 0 10px !important;
          border-bottom:1px solid var(--divider-color) !important;
        }

        .remote-action {
          min-height:48px !important;
          padding:4px 10px 4px 6px !important;
          border-radius:24px !important;
          gap:8px !important;
        }

        .action-circle,
        .remote-action:nth-child(2) .action-circle,
        .remote-action:nth-child(n+4) .action-circle {
          width:36px !important;
          height:36px !important;
          flex:0 0 36px !important;
          border-radius:18px !important;
        }

        .action-circle ha-icon,
        .remote-action:nth-child(n+4) ha-icon {
          --mdc-icon-size:18px !important;
        }

        .remote-action > span:last-child {
          font-size:12px !important;
          line-height:15px !important;
        }

        /* Passive state is deliberately smaller than actions. */
        .status-dock {
          grid-area:statuses;
          display:grid !important;
          grid-template-columns:repeat(4,minmax(0,1fr)) !important;
          gap:6px !important;
          margin:0 !important;
          padding:0 !important;
          border:0 !important;
        }

        .status-tile {
          min-height:38px !important;
          padding:4px 8px !important;
          gap:6px !important;
          border-radius:19px !important;
        }

        .status-icon {
          width:26px !important;
          height:26px !important;
          flex:0 0 26px !important;
          border-radius:13px !important;
        }

        .status-icon ha-icon { --mdc-icon-size:15px !important; }

        .status-copy { gap:0 !important; min-width:0; }

        .status-copy small {
          font-size:9px !important;
          line-height:11px !important;
          white-space:nowrap;
          overflow:hidden;
          text-overflow:ellipsis;
        }

        .status-copy strong {
          font-size:11px !important;
          line-height:13px !important;
          white-space:nowrap !important;
          overflow:hidden !important;
          text-overflow:ellipsis !important;
        }

        .info-grid {
          grid-area:info;
          display:grid !important;
          grid-template-columns:repeat(4,minmax(0,1fr)) !important;
          gap:6px !important;
          margin:0 !important;
          padding:0 !important;
          border:0 !important;
        }

        .info-tile {
          min-height:36px !important;
          padding:4px 8px !important;
          gap:6px !important;
          border-radius:18px !important;
        }

        .info-tile > ha-icon { --mdc-icon-size:15px !important; }

        .info-tile small {
          font-size:9px !important;
          line-height:11px !important;
        }

        .info-tile strong {
          font-size:11px !important;
          line-height:13px !important;
          white-space:nowrap !important;
          overflow:hidden !important;
          text-overflow:ellipsis !important;
        }

        /* On narrow sections the card gracefully falls back to the normal flow. */
        @container (max-width:720px) {
          .wrap {
            display:block !important;
            padding:14px !important;
          }

          .hero { padding:0 !important; }

          .starline-car {
            width:min(100%,260px) !important;
            margin:10px auto 4px !important;
          }

          .remote-controls {
            grid-template-columns:repeat(2,minmax(0,1fr)) !important;
            margin:12px 0 10px !important;
          }

          .status-dock,
          .info-grid {
            grid-template-columns:repeat(2,minmax(0,1fr)) !important;
            margin-top:8px !important;
          }
        }
      `;

      this.shadowRoot.append(style);
    }
  }

  if (!customElements.get(TAG)) {
    customElements.define(TAG, GwmVehicleRemoteHorizontalCard);
  }

  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === TAG)) {
    window.customCards.push({
      type: TAG,
      name: "GWM RU — анимированный пульт · горизонтальный",
      description: "Горизонтальный анимированный пульт: автомобиль слева, управляющие кнопки справа, компактные сенсоры отдельным блоком",
      preview: true,
      documentationURL: "https://github.com/roblencheg/HAVAL_H3",
    });
  }

  console.info(
    "%c GWM RU HORIZONTAL REMOTE %c 1.0.0 ",
    "background:#0f1922;color:white;font-weight:bold;padding:2px 6px;border-radius:3px",
    "background:#526474;color:white;padding:2px 6px;border-radius:3px",
  );
})();
