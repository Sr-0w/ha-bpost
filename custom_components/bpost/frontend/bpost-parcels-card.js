/* Bpost Parcels — generic Lovelace card for the My bpost integration.
 *
 * Type: custom:bpost-parcels-card
 * Options:
 *   title         Card title (default: localized "Parcels")
 *   show_history  Include delivered/inactive parcels (default: false)
 *
 * Theme-safe: all colors come from Home Assistant CSS variables, so the
 * card follows the default theme as well as any theme applied to the card.
 * No dependencies besides <ha-card> and <ha-icon>.
 */

const T = {
  en: {
    parcels: "Parcels", empty: "No parcels", history: "History",
    tracking: "Tracking", pickup: "Pickup point", expected: "Expected",
    inTransit: "Out for delivery", delivered: "Delivered", preparing: "In preparation",
    failed: "Delivery failed", announced: "Announced", returning: "Returning",
  },
  fr: {
    parcels: "Colis", empty: "Aucun colis", history: "Historique",
    tracking: "Suivi", pickup: "Point de retrait", expected: "Prévu",
    inTransit: "En tournée", delivered: "Livré", preparing: "En préparation",
    failed: "Échec de livraison", announced: "Annoncé", returning: "En retour",
  },
  nl: {
    parcels: "Pakketten", empty: "Geen pakketten", history: "Geschiedenis",
    tracking: "Tracering", pickup: "Afhaalpunt", expected: "Verwacht",
    inTransit: "Onderweg", delivered: "Bezorgd", preparing: "In voorbereiding",
    failed: "Bezorging mislukt", announced: "Aangekondigd", returning: "Retour",
  },
  de: {
    parcels: "Pakete", empty: "Keine Pakete", history: "Verlauf",
    tracking: "Sendungsverfolgung", pickup: "Abholstation", expected: "Erwartet",
    inTransit: "In Zustellung", delivered: "Zugestellt", preparing: "In Vorbereitung",
    failed: "Zustellung fehlgeschlagen", announced: "Angekündigt", returning: "Rücksendung",
  },
};

const STATUS_LABEL = {
  OUT_FOR_DELIVERY: "inTransit", OUTFORDELIVERY: "inTransit", AROUND: "inTransit",
  DELIVERED: "delivered", DistributedNormally: "delivered",
  DistributedAfterBTS: "delivered", DistributedAbroad: "delivered",
  PICKED_UP_IN_POST_POINT: "delivered", PICKED_UP_IN_POST_OFFICE: "delivered",
  IN_PREPARATION: "preparing", PREPARATION: "preparing", PROCESSING: "preparing",
  AnnouncementReceived: "announced",
  DELIVERY_FAILED: "failed", FAILED: "failed",
  DELIVERED_TO_SENDER: "returning", RETURNED_TO_SENDER: "returning",
  ON_THE_WAY_TO_SENDER: "returning",
};

function lang(hass) {
  const code = (hass?.locale?.language || hass?.language || "en").slice(0, 2);
  return T[code] ? code : "en";
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function statusKey(state, listStatus) {
  return STATUS_LABEL[state] || STATUS_LABEL[listStatus] || null;
}

function statusTone(state, listStatus) {
  const key = statusKey(state, listStatus);
  if (key === "inTransit") return "warn";
  if (key === "delivered") return "ok";
  if (key === "failed") return "bad";
  return "info";
}

function statusLabel(state, listStatus, code) {
  const key = statusKey(state, listStatus);
  if (key) return T[code][key];
  const raw = String(state && state !== "unknown" ? state : (listStatus || ""));
  if (!raw) return T[code].announced;
  const pretty = raw.replace(/_/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase();
  return pretty.charAt(0).toUpperCase() + pretty.slice(1);
}

function parcelIcon(state, listStatus) {
  const key = statusKey(state, listStatus);
  if (key === "inTransit") return "mdi:truck-delivery";
  if (key === "delivered") return "mdi:package-variant-closed-check";
  return "mdi:package-variant";
}

function etaLine(attrs) {
  if (!attrs.delivery_date) return "";
  const window = [attrs.delivery_window_start, attrs.delivery_window_end]
    .filter(Boolean).join(" – ");
  return `${attrs.delivery_date}${window ? ` (${window})` : ""}`;
}

const CSS = `
.bpost-wrap{display:grid;gap:4px;padding:4px 0}
.bpost-row{display:grid;grid-template-columns:40px minmax(0,1fr) auto;gap:12px;
  align-items:start;padding:12px 16px;border-bottom:1px solid var(--divider-color,#e0e0e0)}
.bpost-row:last-child{border-bottom:0}
.bpost-ico{width:40px;height:40px;border-radius:12px;display:grid;place-items:center;
  background:var(--secondary-background-color,var(--divider-color,#e0e0e0));
  color:var(--primary-color,var(--primary-text-color,#212121))}
.bpost-ico ha-icon{--mdc-icon-size:22px}
.bpost-name{font-weight:600;font-size:14px;line-height:1.35;overflow-wrap:anywhere}
.bpost-sub{font-size:12px;line-height:1.5;color:var(--secondary-text-color,#727272);
  margin-top:2px;overflow-wrap:anywhere}
.bpost-badge{font-size:11px;font-weight:600;white-space:nowrap;padding:5px 10px;
  border-radius:20px;margin-top:2px}
.bpost-badge.warn{color:var(--warning-color,#e65100);
  background:color-mix(in srgb,var(--warning-color,#e65100) 14%,transparent)}
.bpost-badge.ok{color:var(--success-color,#2e7d32);
  background:color-mix(in srgb,var(--success-color,#2e7d32) 14%,transparent)}
.bpost-badge.bad{color:var(--error-color,#c62828);
  background:color-mix(in srgb,var(--error-color,#c62828) 14%,transparent)}
.bpost-badge.info{color:var(--info-color,var(--primary-color,#0288d1));
  background:color-mix(in srgb,var(--info-color,var(--primary-color,#0288d1)) 14%,transparent)}
.bpost-detail{grid-column:2 / -1;margin:2px 0 0}
.bpost-detail summary{cursor:pointer;font-size:12px;font-weight:600;min-height:32px;
  display:flex;align-items:center;color:var(--primary-color,var(--primary-text-color,#212121))}
.bpost-pickup{display:flex;gap:8px;align-items:flex-start;font-size:12px;line-height:1.5;
  margin:8px 0 2px;padding:8px 10px;border-radius:8px;
  background:var(--secondary-background-color,var(--divider-color,#e0e0e0))}
.bpost-pickup ha-icon{--mdc-icon-size:16px;flex:none;margin-top:1px;
  color:var(--primary-color,var(--primary-text-color,#212121))}
.bpost-pickup small{display:block;color:var(--secondary-text-color,#727272)}
.bpost-tl{list-style:none;margin:8px 0 4px;padding:0 0 0 4px;position:relative}
.bpost-tl::before{content:"";position:absolute;left:8px;top:8px;bottom:8px;width:2px;
  border-radius:2px;background:var(--divider-color,#e0e0e0)}
.bpost-tl li{position:relative;padding:5px 0 5px 24px;font-size:12px;line-height:1.5}
.bpost-tl li::before{content:"";position:absolute;left:3px;top:10px;width:8px;height:8px;
  border-radius:50%;background:var(--card-background-color,#fff);
  border:2px solid var(--secondary-text-color,#727272)}
.bpost-tl li:first-child::before{border-color:var(--primary-color,#0288d1);
  background:var(--primary-color,#0288d1)}
.bpost-tl time{display:block;font-size:11px;color:var(--secondary-text-color,#727272)}
.bpost-tl small{display:block;color:var(--secondary-text-color,#727272)}
.bpost-sec{font-size:11px;font-weight:700;letter-spacing:.6px;
  color:var(--secondary-text-color,#727272);padding:12px 16px 0}
.bpost-empty{padding:20px 16px;text-align:center;font-size:13px;
  color:var(--secondary-text-color,#727272)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
`;

class BpostParcelsCard extends HTMLElement {
  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = { show_history: false, ...config };
    if (!this._root) {
      this.attachShadow({ mode: "open" });
      this._root = this.shadowRoot;
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    const n = this._count || 0;
    return 1 + Math.ceil(n / 2) + (this._history ? 1 : 0);
  }

  static getStubConfig() {
    return { show_history: false };
  }

  _sensors() {
    const states = this._hass?.states || {};
    return Object.values(states)
      .filter((e) => e.entity_id?.startsWith("sensor.my_bpost_")
        && e.entity_id !== "sensor.my_bpost_packages"
        && e.attributes?.tracking_number);
  }

  _row(e, code) {
    const a = e.attributes || {};
    const name = a.friendly_name || `Parcel ${String(a.tracking_number).slice(-6)}`;
    const tone = statusTone(e.state, a.list_status);
    const badge = statusLabel(e.state, a.list_status, code);
    const eta = etaLine(a);
    const sub = [a.last_event, eta ? `${T[code].expected} ${eta}` : ""]
      .filter(Boolean).join(" · ") || badge;
    const events = Array.isArray(a.events) ? a.events : [];
    const pickup = a.pickup_name ? `
      <p class="bpost-pickup"><ha-icon icon="mdi:store"></ha-icon><span>
        ${esc(T[code].pickup)}: <strong>${esc(a.pickup_name)}</strong>
        ${a.pickup_address ? `<small>${esc(a.pickup_address)}</small>` : ""}
      </span></p>` : "";
    const timeline = events.length ? `
      <ol class="bpost-tl">${events.map((ev) => `
        <li><time>${esc([ev.date, ev.time].filter(Boolean).join(" · "))}</time>
        <span>${esc(ev.description || "")}</span>
        ${ev.location ? `<small>${esc(ev.location)}</small>` : ""}</li>`).join("")}
      </ol>` : "";
    return `
      <div class="bpost-row">
        <span class="bpost-ico"><ha-icon icon="${parcelIcon(e.state, a.list_status)}"></ha-icon></span>
        <div><div class="bpost-name">${esc(name)}</div><div class="bpost-sub">${esc(sub)}</div></div>
        <span class="bpost-badge ${tone}">${esc(badge)}</span>
        ${(pickup || timeline) ? `
        <details class="bpost-detail">
          <summary>${esc(T[code].tracking)}${events.length ? ` · ${events.length}` : ""}</summary>
          ${pickup}${timeline}
        </details>` : ""}
      </div>`;
  }

  _render() {
    if (!this._root) return;
    const code = lang(this._hass);
    const all = this._sensors();
    const active = all.filter((e) => e.attributes?.active !== false);
    const history = all.filter((e) => e.attributes?.active === false);
    const showHistory = !!this._config?.show_history && history.length > 0;
    this._count = active.length;
    this._history = showHistory;
    const title = this._config?.title || T[code].parcels;
    const head = active.length ? `${title} · ${active.length}` : title;
    let body;
    if (!active.length && !showHistory) {
      body = `<div class="bpost-empty">${esc(T[code].empty)}</div>`;
    } else {
      body = `<div class="bpost-wrap">`
        + active.map((e) => this._row(e, code)).join("")
        + (showHistory
          ? `<div class="bpost-sec">${esc(T[code].history)}</div>`
            + history.map((e) => this._row(e, code)).join("")
          : "")
        + `</div>`;
    }
    this._root.innerHTML = `<style>${CSS}</style><ha-card header="${esc(head)}">${body}</ha-card>`;
  }
}

if (!customElements.get("bpost-parcels-card")) {
  customElements.define("bpost-parcels-card", BpostParcelsCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "bpost-parcels-card")) {
  window.customCards.push({
    type: "bpost-parcels-card",
    name: "Bpost Parcels",
    description: "Parcels linked to your My bpost account, with tracking timelines.",
    preview: true,
  });
}
