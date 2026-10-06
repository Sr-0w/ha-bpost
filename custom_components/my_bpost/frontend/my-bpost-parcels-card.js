/* Bpost Parcels — generic Lovelace card for the My bpost integration.
 *
 * Type: custom:my-bpost-parcels-card
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
    live: "Live delivery", stops: "Stops remaining", updated: "Updated", map: "Show courier on map",
    noLive: "Live tracking unavailable", returned: "Returned to sender", transit: "In transit", collect: "Ready to collect",
    parcels: "Parcels", empty: "No parcels", history: "History",
    tracking: "Tracking", pickup: "Pickup point", expected: "Expected",
    inTransit: "Out for delivery", delivered: "Delivered", preparing: "In preparation",
    failed: "Delivery failed", announced: "Announced", returning: "Returning",
  },
  fr: {
    live: "Livraison en direct", stops: "Arrêts restants", updated: "Actualisé", map: "Voir le livreur sur la carte",
    noLive: "Suivi en direct indisponible", returned: "Retourné à l’expéditeur", transit: "En transit", collect: "À retirer",
    parcels: "Colis", empty: "Aucun colis", history: "Historique",
    tracking: "Suivi", pickup: "Point de retrait", expected: "Prévu",
    inTransit: "En tournée", delivered: "Livré", preparing: "En préparation",
    failed: "Échec de livraison", announced: "Annoncé", returning: "En retour",
  },
  nl: {
    live: "Live levering", stops: "Resterende stops", updated: "Bijgewerkt", map: "Toon bezorger op kaart",
    noLive: "Live volgen niet beschikbaar", returned: "Terug bij afzender", transit: "Onderweg", collect: "Klaar om af te halen",
    parcels: "Pakketten", empty: "Geen pakketten", history: "Geschiedenis",
    tracking: "Tracering", pickup: "Afhaalpunt", expected: "Verwacht",
    inTransit: "Onderweg", delivered: "Bezorgd", preparing: "In voorbereiding",
    failed: "Bezorging mislukt", announced: "Aangekondigd", returning: "Retour",
  },
  de: {
    live: "Live-Zustellung", stops: "Verbleibende Stopps", updated: "Aktualisiert", map: "Zusteller auf Karte anzeigen",
    noLive: "Live-Verfolgung nicht verfügbar", returned: "An Absender zurückgesendet", transit: "Unterwegs", collect: "Abholbereit",
    parcels: "Pakete", empty: "Keine Pakete", history: "Verlauf",
    tracking: "Sendungsverfolgung", pickup: "Abholstation", expected: "Erwartet",
    inTransit: "In Zustellung", delivered: "Zugestellt", preparing: "In Vorbereitung",
    failed: "Zustellung fehlgeschlagen", announced: "Angekündigt", returning: "Rücksendung",
  },
};

const STATUS_LABEL = {
  registered: "announced", in_transit: "transit", out_for_delivery: "inTransit",
  at_pickup_point: "collect", delivered: "delivered", returning: "returning", returned: "returned", problem: "failed",
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

const N = {
  fr: { view: "Vue", all: "Tous les colis", today: "Aujourd’hui", pickup: "À retirer", problem: "À résoudre", empty: "Rien à signaler aujourd’hui", group: "Groupe", dedup: "Masquer les doublons", sources: "sources à vérifier", ok: "À jour", starting: "Démarrage", auth_required: "Connexion à renouveler", rate_limited: "Limite API : nouvelle tentative différée", maintenance: "Maintenance bpost", outdated_client: "Mise à jour de l’intégration nécessaire", not_found: "Colis temporairement introuvable", service_unavailable: "Service indisponible" },
  en: { view: "View", all: "All parcels", today: "Today", pickup: "Ready to collect", problem: "Needs attention", empty: "Nothing to report today", group: "Group", dedup: "Hide duplicates", sources: "sources need attention", ok: "Up to date", starting: "Starting", auth_required: "Sign in again", rate_limited: "API limit: retry delayed", maintenance: "bpost maintenance", outdated_client: "Integration update required", not_found: "Parcel temporarily not found", service_unavailable: "Service unavailable" },
  nl: { view: "Weergave", all: "Alle pakketten", today: "Vandaag", pickup: "Af te halen", problem: "Aandacht nodig", empty: "Vandaag niets te melden", group: "Groep", dedup: "Duplicaten verbergen", sources: "bronnen vereisen aandacht", ok: "Bijgewerkt", starting: "Starten", auth_required: "Opnieuw aanmelden", rate_limited: "API-limiet: nieuwe poging uitgesteld", maintenance: "bpost-onderhoud", outdated_client: "Integratie-update vereist", not_found: "Pakket tijdelijk niet gevonden", service_unavailable: "Dienst niet beschikbaar" },
  de: { view: "Ansicht", all: "Alle Pakete", today: "Heute", pickup: "Abzuholen", problem: "Handlungsbedarf", empty: "Heute nichts zu melden", group: "Gruppe", dedup: "Duplikate ausblenden", sources: "Quellen benötigen Aufmerksamkeit", ok: "Aktuell", starting: "Wird gestartet", auth_required: "Erneut anmelden", rate_limited: "API-Limit: Versuch verschoben", maintenance: "bpost-Wartung", outdated_client: "Integrationsupdate erforderlich", not_found: "Paket vorübergehend nicht gefunden", service_unavailable: "Dienst nicht verfügbar" },
};

function selectParcels(states) {
  const selected = new Map();
  const rank = (state) => [!["unavailable", "unknown"].includes(state.state) ? 1 : 0,
    Date.parse(state.attributes.last_fetch || "") || 0, state.attributes.tracking_source !== "public" ? 1 : 0];
  const newer = (a, b) => { const x = rank(a), y = rank(b); for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] > y[i]; return false; };
  for (const state of [...states].sort((a, b) => a.entity_id.localeCompare(b.entity_id))) {
    const key = state.attributes.tracking_number;
    if (!selected.has(key) || newer(state, selected.get(key))) selected.set(key, state);
  }
  return [...selected.values()];
}

function todayTime(hass) {
  const parts = new Intl.DateTimeFormat("en", { timeZone: hass?.config?.time_zone || "Europe/Brussels", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
  const part = (key) => parts.find((p) => p.type === key).value;
  return deliveryTime(`${part("year")}-${part("month")}-${part("day")}`);
}

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

function deliveryTime(value) {
  const text = String(value || "");
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  const eu = text.match(/^(\d{2})[/-](\d{2})[/-](\d{4})$/);
  if (!iso && !eu) return Infinity;
  const [y, m, d] = iso ? iso.slice(1).map(Number) : [Number(eu[3]), Number(eu[2]), Number(eu[1])];
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d
    ? date.getTime() : Infinity;
}

function validateConfig(config) {
  if (!config || typeof config !== "object" || Array.isArray(config)) throw new Error("Invalid card configuration");
  for (const key of ["show_history", "show_live", "privacy_mode", "deduplicate"]) {
    if (config[key] !== undefined && typeof config[key] !== "boolean") throw new Error(`${key} must be a boolean`);
  }
  for (const key of ["title", "account_id", "group"]) {
    if (config[key] !== undefined && typeof config[key] !== "string") throw new Error(`${key} must be text`);
  }
  if (config.direction !== undefined && !["all", "incoming", "outgoing"].includes(config.direction)) throw new Error("Invalid direction");
  if (config.sort_by !== undefined && !["priority", "delivery_date", "updated", "name"].includes(config.sort_by)) throw new Error("Invalid sort_by");
  if (config.view !== undefined && !["all", "today"].includes(config.view)) throw new Error("Invalid view");
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
.bpost-live{grid-column:2 / -1;border-inline-start:3px solid var(--primary-color);
  padding:8px 12px;background:var(--secondary-background-color);border-radius:6px;font-size:13px}
.bpost-live dl{display:grid;grid-template-columns:1fr auto;gap:6px;margin:8px 0}
.bpost-live dd{margin:0;font-weight:600}.bpost-live small{color:var(--secondary-text-color)}
.bpost-map{display:block;margin-top:8px;min-height:44px;border:1px solid var(--divider-color);
  border-radius:8px;padding:8px 12px;background:var(--card-background-color);color:var(--primary-color);cursor:pointer}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
`;

class MyBpostParcelsCard extends HTMLElement {
  setConfig(config) {
    validateConfig(config);
    this._config = { show_history: false, show_live: true, privacy_mode: false, sort_by: "priority", deduplicate: true, view: "all", ...config };
    if (!this._root) {
      this.attachShadow({ mode: "open" });
      this._root = this.shadowRoot;
      this._root.addEventListener("click", (event) => {
        const button = event.target.closest?.("button[data-courier]");
        if (button) this.dispatchEvent(new CustomEvent("hass-more-info", {
          detail: { entityId: button.dataset.courier }, bubbles: true, composed: true,
        }));
      });
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

  connectedCallback() {
    this._dayTimer ||= window.setInterval(() => { if (this._config?.view === "today") this._render(); }, 60000);
  }

  disconnectedCallback() {
    window.clearInterval(this._dayTimer);
    this._dayTimer = null;
  }

  static getStubConfig() {
    return { show_history: false };
  }

  static getConfigElement() {
    return document.createElement("my-bpost-parcels-card-editor");
  }

  _sensors() {
    const states = this._hass?.states || {};
    const parcels = Object.values(states)
      .filter((e) => e.entity_id?.startsWith("sensor.")
        && (e.attributes?.integration === "my_bpost" || e.entity_id.startsWith("sensor.my_bpost_"))
        && e.attributes?.tracking_number
        && (!this._config?.group || e.attributes.parcel_group === this._config.group)
        && (!this._config?.account_id || e.attributes.account_id === this._config.account_id)
        && (!this._config?.direction || this._config.direction === "all"
          || e.attributes.user_type === (this._config.direction === "outgoing" ? "SENDER" : "RECEIVER")));
    return this._config?.deduplicate === false ? parcels : selectParcels(parcels);
  }

  _live(e, code) {
    if (!this._config.show_live || this._config.privacy_mode) return "";
    const a = e.attributes || {};
    if (e.state !== "out_for_delivery" || a.active === false) return "";
    if (!a.live_available) return `<div class="bpost-live"><small>${esc(T[code].noLive)}</small></div>`;
    const stops = Number.isInteger(a.stops_remaining) && a.stops_remaining >= 0 ? a.stops_remaining : "—";
    const observed = new Date(a.live_updated_at || NaN);
    const updated = Number.isNaN(observed.getTime()) ? "" : observed.toLocaleTimeString(code);
    const tracker = Object.values(this._hass?.states || {}).find((t) => (
      t.entity_id?.startsWith("device_tracker.") && t.attributes?.integration === "my_bpost"
      && t.attributes.location_kind === "courier" && t.attributes.account_id === a.account_id
      && t.attributes.tracking_number === a.tracking_number
      && !["unavailable", "unknown"].includes(t.state)
      && Number.isFinite(t.attributes.latitude) && Number.isFinite(t.attributes.longitude)));
    return `<div class="bpost-live"><strong>${esc(T[code].live)}</strong><dl>
      <dt>${esc(T[code].stops)}</dt><dd>${esc(stops)}</dd>
      <dt>${esc(T[code].expected)}</dt><dd>${esc(a.live_eta || "—")}</dd></dl>
      ${updated ? `<small>${esc(T[code].updated)} ${esc(updated)}</small>` : ""}
      ${tracker ? `<button class="bpost-map" data-courier="${esc(tracker.entity_id)}">${esc(T[code].map)}</button>` : ""}</div>`;
  }

  _row(e, code, index) {
    const a = e.attributes || {};
    if (this._config.privacy_mode) {
      const safe = ["registered", "in_transit", "out_for_delivery", "at_pickup_point", "delivered", "returning", "returned", "problem"].includes(e.state);
      const badge = safe ? statusLabel(e.state, null, code) : E[code].unknown;
      return `<div class="bpost-row"><span class="bpost-ico"><ha-icon icon="mdi:package-variant"></ha-icon></span>
        <div class="bpost-name">${esc(E[code].parcel)} ${index + 1}</div>
        <span class="bpost-badge ${safe ? statusTone(e.state, null) : "info"}">${esc(badge)}</span></div>`;
    }
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
        ${this._live(e, code)}
        ${(pickup || timeline) ? `
        <details class="bpost-detail" data-entity="${esc(e.entity_id)}">
          <summary>${esc(T[code].tracking)}${events.length ? ` · ${events.length}` : ""}</summary>
          ${pickup}${timeline}
        </details>` : ""}
      </div>`;
  }

  _render() {
    if (!this._root) return;
    const code = lang(this._hass);
    const priority = { failed: 0, collect: 1, inTransit: 2, transit: 3, returning: 4, announced: 5, delivered: 6, returned: 7 };
    const timestamp = (e) => {
      const value = Date.parse(e.attributes?.last_event_ts || "");
      return Number.isFinite(value) ? value : -Infinity;
    };
    const all = this._sensors().sort((a, b) => {
      let difference = 0;
      if (this._config.sort_by === "delivery_date") difference = deliveryTime(a.attributes.delivery_date) - deliveryTime(b.attributes.delivery_date);
      else if (this._config.sort_by === "updated") difference = timestamp(b) - timestamp(a);
      else if (this._config.sort_by === "name") difference = String(a.attributes.friendly_name || "").localeCompare(String(b.attributes.friendly_name || ""), code);
      else difference = (priority[statusKey(a.state, a.attributes.list_status)] ?? 8) - (priority[statusKey(b.state, b.attributes.list_status)] ?? 8);
      return difference || a.entity_id.localeCompare(b.entity_id);
    });
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
        + active.map((e, i) => this._row(e, code, i)).join("")
        + (showHistory
          ? `<div class="bpost-sec">${esc(T[code].history)}</div>`
            + history.map((e, i) => this._row(e, code, active.length + i)).join("")
          : "")
        + `</div>`;
    }
    let header = head;
    if (this._config.view === "today") {
      const healthy = active.filter((e) => !["unknown", "unavailable"].includes(e.state));
      const today = todayTime(this._hass);
      const groups = [
        [N[code].problem, healthy.filter((e) => e.state === "problem")],
        [N[code].pickup, healthy.filter((e) => e.state === "at_pickup_point")],
        [N[code].today, healthy.filter((e) => !["problem", "at_pickup_point"].includes(e.state) && (e.state === "out_for_delivery" || deliveryTime(e.attributes.delivery_date) === today))],
      ];
      let index = 0;
      this._count = groups.reduce((sum, [, rows]) => sum + rows.length, 0);
      this._history = false;
      header = this._config.title || N[code].today;
      body = groups.filter(([, rows]) => rows.length).map(([label, rows]) => `<div class="bpost-sec">${esc(label)} · ${rows.length}</div>${rows.map((e) => this._row(e, code, index++)).join("")}`).join("") || `<div class="bpost-empty">${esc(N[code].empty)}</div>`;
    }
    const health = Object.values(this._hass?.states || {}).filter((e) => e.attributes?.integration === "my_bpost" && e.attributes.health_sensor
      && e.state !== "ok" && (!this._config.account_id || e.attributes.account_id === this._config.account_id)
      && (!this._config.group || e.attributes.parcel_group === this._config.group));
    const warning = health.length ? `<div class="bpost-sec" role="status">${health.length} ${esc(N[code].sources)}: ${esc([...new Set(health.map((e) => N[code][e.state] || N[code].service_unavailable))].join(" · "))}</div>` : "";
    const expanded = new Set([...this._root.querySelectorAll("details[open]")].map((el) => el.dataset.entity));
    this._root.innerHTML = `<style>${CSS}</style><ha-card header="${esc(header)}">${warning}${body}</ha-card>`;
    for (const el of this._root.querySelectorAll("details")) el.open = expanded.has(el.dataset.entity);
  }
}

const E = {
  en: { title: "Title", account: "Account", allAccounts: "All accounts", direction: "Parcels", all: "All", incoming: "Incoming", outgoing: "Outgoing", sort: "Sort by", priority: "Delivery priority", delivery_date: "Delivery date", updated: "Latest update", name: "Name", history: "Show inactive parcels", live: "Show live delivery", privacy: "Discreet mode", privacyHelp: "Show only numbered parcels and statuses. Names, addresses, tracking details and maps are hidden on this card.", parcel: "Parcel", unknown: "Unknown", missing: "Unavailable account" },
  fr: { title: "Titre", account: "Compte", allAccounts: "Tous les comptes", direction: "Colis", all: "Tous", incoming: "Entrants", outgoing: "Sortants", sort: "Trier par", priority: "Priorité de livraison", delivery_date: "Date de livraison", updated: "Dernière actualisation", name: "Nom", history: "Afficher les colis inactifs", live: "Afficher le suivi en direct", privacy: "Mode discret", privacyHelp: "Afficher seulement le numéro d’ordre et le statut des colis. Les noms, adresses, détails de suivi et cartes sont masqués sur cette carte.", parcel: "Colis", unknown: "Inconnu", missing: "Compte indisponible" },
  nl: { title: "Titel", account: "Account", allAccounts: "Alle accounts", direction: "Pakketten", all: "Alle", incoming: "Inkomend", outgoing: "Uitgaand", sort: "Sorteren op", priority: "Bezorgprioriteit", delivery_date: "Leverdatum", updated: "Laatste update", name: "Naam", history: "Inactieve pakketten tonen", live: "Live levering tonen", privacy: "Discrete modus", privacyHelp: "Toon alleen nummers in deze lijst en statussen. Namen, adressen, trackingdetails en kaarten worden op deze kaart verborgen.", parcel: "Pakket", unknown: "Onbekend", missing: "Account niet beschikbaar" },
  de: { title: "Titel", account: "Konto", allAccounts: "Alle Konten", direction: "Pakete", all: "Alle", incoming: "Eingehend", outgoing: "Ausgehend", sort: "Sortieren nach", priority: "Zustellpriorität", delivery_date: "Lieferdatum", updated: "Letzte Aktualisierung", name: "Name", history: "Inaktive Pakete anzeigen", live: "Live-Zustellung anzeigen", privacy: "Diskreter Modus", privacyHelp: "Nur laufende Nummern und Status anzeigen. Namen, Adressen, Sendungsdetails und Karten werden auf dieser Karte ausgeblendet.", parcel: "Paket", unknown: "Unbekannt", missing: "Konto nicht verfügbar" },
};

class MyBpostParcelsCardEditor extends HTMLElement {
  setConfig(config) {
    validateConfig(config);
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
    if (!this._accountsRequested && hass.callWS) {
      this._accountsRequested = true;
      // This endpoint returns entry titles, never their stored credentials.
      Promise.resolve().then(() => hass.callWS({ type: "config_entries/get", domain: "my_bpost" }))
        .then((entries) => {
          this._accounts = Array.isArray(entries) ? entries.filter((entry) => entry.domain === "my_bpost") : [];
          this._render();
        }).catch(() => { /* State markers also work without config-entry access. */ });
    }
  }

  _accountOptions(t) {
    const accounts = new Map((this._accounts || []).map((entry) => [entry.entry_id, entry.title]));
    for (const state of Object.values(this._hass?.states || {})) {
      const id = state.attributes?.account_id;
      if (state.attributes?.integration === "my_bpost" && id && !accounts.has(id)) accounts.set(id, `${t.account} · ${id.slice(-8)}`);
    }
    const selected = this._config?.account_id;
    if (selected && !accounts.has(selected)) accounts.set(selected, `${t.missing} · ${selected.slice(-8)}`);
    return [["", t.allAccounts], ...[...accounts].sort((a, b) => a[1].localeCompare(b[1]))];
  }

  _change(event) {
    const field = event.target;
    if (!["title", "account_id", "direction", "sort_by", "show_history", "show_live", "privacy_mode", "view", "group", "deduplicate"].includes(field.name)) return;
    const value = field.type === "checkbox" ? field.checked : field.value;
    const config = { ...this._config, [field.name]: value };
    if ((field.name === "title" || field.name === "account_id") && !value) delete config[field.name];
    this._config = config;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
  }

  _render() {
    if (!this._config) return;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("change", (event) => this._change(event));
      this.shadowRoot.addEventListener("input", (event) => { if (["title", "group"].includes(event.target.name)) this._change(event); });
    }
    const t = E[lang(this._hass)];
    const accounts = this._accountOptions(t);
    const signature = JSON.stringify([this._config, accounts, lang(this._hass)]);
    if (signature === this._renderSignature) return;
    this._renderSignature = signature;
    const focus = this.shadowRoot.activeElement;
    const focusedName = focus?.name;
    const selection = focus?.type === "text" ? [focus.selectionStart, focus.selectionEnd] : null;
    const select = (key, label, options, value) => `<label>${esc(label)}<select name="${key}" aria-label="${esc(label)}">${options.map(([id, name]) => `<option value="${esc(id)}"${id === value ? " selected" : ""}>${esc(name)}</option>`).join("")}</select></label>`;
    const check = (key, label, checked) => `<label class="toggle"><input type="checkbox" name="${key}"${checked ? " checked" : ""}>${esc(label)}</label>`;
    const config = this._config;
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;color:var(--primary-text-color)}.fields{display:grid;gap:16px;padding:8px 0}
      label{display:grid;gap:6px;font-size:14px}input[type=text],select{box-sizing:border-box;width:100%;min-height:44px;border:1px solid var(--divider-color);border-radius:8px;padding:8px 12px;background:var(--card-background-color);color:var(--primary-text-color);font:inherit}
      .toggle{display:flex;align-items:center;gap:10px;min-height:36px}input[type=checkbox]{width:20px;height:20px;accent-color:var(--primary-color)}p{margin:0;font-size:12px;color:var(--secondary-text-color);line-height:1.5}
      input:focus-visible,select:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}
      </style><div class="fields">
      <label>${esc(t.title)}<input type="text" name="title" value="${esc(config.title || "")}" placeholder="${esc(T[lang(this._hass)].parcels)}"></label>
      ${select("account_id", t.account, accounts, config.account_id || "")}
      ${select("view", N[lang(this._hass)].view, ["all", "today"].map((key) => [key, N[lang(this._hass)][key]]), config.view || "all")}
      <label>${esc(N[lang(this._hass)].group)}<input type="text" name="group" value="${esc(config.group || "")}"></label>
      ${check("deduplicate", N[lang(this._hass)].dedup, config.deduplicate !== false)}
      ${select("direction", t.direction, ["all", "incoming", "outgoing"].map((key) => [key, t[key]]), config.direction || "all")}
      ${select("sort_by", t.sort, ["priority", "delivery_date", "updated", "name"].map((key) => [key, t[key]]), config.sort_by || "priority")}
      ${check("show_history", t.history, config.show_history === true)}
      ${check("show_live", t.live, config.show_live !== false)}
      ${check("privacy_mode", t.privacy, config.privacy_mode === true)}<p>${esc(t.privacyHelp)}</p></div>`;
    if (focusedName) {
      const control = this.shadowRoot.querySelector(`[name="${focusedName}"]`);
      control?.focus();
      if (selection && control?.type === "text") control.setSelectionRange(...selection);
    }
  }
}

if (!customElements.get("my-bpost-parcels-card-editor")) {
  customElements.define("my-bpost-parcels-card-editor", MyBpostParcelsCardEditor);
}

if (!customElements.get("my-bpost-parcels-card")) {
  customElements.define("my-bpost-parcels-card", MyBpostParcelsCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "my-bpost-parcels-card")) {
  window.customCards.push({
    type: "my-bpost-parcels-card",
    name: "Bpost Parcels",
    description: "Parcels linked to your My bpost account, with tracking timelines.",
    preview: true,
  });
}
