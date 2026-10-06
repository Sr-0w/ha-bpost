/* Rendering and interaction contracts; no browser or bpost account required. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function card(states, config = {}) {
  const elements = new Map();
  class HTMLElement {
    attachShadow() {
      this.shadowRoot = {
        innerHTML: '', listeners: {},
        addEventListener(type, fn) { this.listeners[type] = fn; },
        querySelectorAll() { return []; },
      };
    }
    dispatchEvent(event) { this.event = event; }
  }
  const context = vm.createContext({ HTMLElement, window: {}, Date,
    document: { createElement: (tag) => new (elements.get(tag))() },
    CustomEvent: class { constructor(type, options) { this.type = type; Object.assign(this, options); } },
    customElements: { get: (key) => elements.get(key), define: (key, cls) => elements.set(key, cls) },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname,
    '../../custom_components/my_bpost/frontend/my-bpost-parcels-card.js'), 'utf8'), context);
  const result = new (elements.get('my-bpost-parcels-card'))();
  result.setConfig(config);
  result.hass = { language: 'fr', states };
  return result;
}

function parcel(attributes = {}, state = 'out_for_delivery') {
  return { entity_id: 'sensor.renamed_parcel', state, attributes: {
    integration: 'my_bpost', account_id: 'account-a', tracking_number: 'fiction',
    friendly_name: 'Synthetic parcel', active: true, user_type: 'RECEIVER', ...attributes,
  } };
}

function tracker(attributes = {}, state = 'not_home') {
  return { entity_id: 'device_tracker.courier', state, attributes: {
    integration: 'my_bpost', account_id: 'account-a', tracking_number: 'fiction',
    location_kind: 'courier', latitude: 50.85, longitude: 4.35, ...attributes,
  } };
}

test('renamed entity is discovered by integration marker', () => {
  assert.match(card({ p: parcel() }).shadowRoot.innerHTML, /Synthetic parcel/);
});

test('zero remaining stops is shown; absent stops are not invented', () => {
  const live = card({ p: parcel({ live_available: true, stops_remaining: 0 }) });
  assert.match(live.shadowRoot.innerHTML, /<dd>0<\/dd>/);
  const missing = card({ p: parcel({ live_available: true }) });
  assert.match(missing.shadowRoot.innerHTML, /<dd>—<\/dd>/);
});

test('stale live data cannot expose map or stops', () => {
  const html = card({ p: parcel({ live_available: false, stops_remaining: 7 }), t: tracker() }).shadowRoot.innerHTML;
  assert.match(html, /Suivi en direct indisponible/);
  assert.doesNotMatch(html, /data-courier=|<dd>7<\/dd>/);
});

test('courier map uses matching account and never pickup coordinates', () => {
  const p = parcel({ live_available: true, stops_remaining: 7 });
  assert.doesNotMatch(card({ p, t: tracker({ account_id: 'other' }) }).shadowRoot.innerHTML, /data-courier=/);
  assert.doesNotMatch(card({ p, t: tracker({ location_kind: 'pickup' }) }).shadowRoot.innerHTML, /data-courier=/);
  assert.doesNotMatch(card({ p, t: tracker({}, 'unavailable') }).shadowRoot.innerHTML, /data-courier=/);
  assert.match(card({ p, t: tracker() }).shadowRoot.innerHTML, /data-courier="device_tracker.courier"/);
});

test('map button opens HA entity details', () => {
  const result = card({ p: parcel({ live_available: true }), t: tracker() });
  result.shadowRoot.listeners.click({ target: { closest: () => ({ dataset: { courier: 'device_tracker.courier' } }) } });
  assert.equal(result.event.type, 'hass-more-info');
  assert.equal(result.event.detail.entityId, 'device_tracker.courier');
  assert.equal(result.event.composed, true);
});

test('API text is escaped in ETA, sender and history', () => {
  const html = card({ p: parcel({ live_available: true, live_eta: '<img src=x onerror=alert(1)>',
    friendly_name: '<script>bad()</script>', events: [{ description: '<iframe src=x>', date: 'today' }],
  }) }).shadowRoot.innerHTML;
  assert.doesNotMatch(html, /<img|<script|<iframe/);
  assert.match(html, /&lt;img/);
});

test('account and direction filters isolate the requested inbox', () => {
  assert.match(card({ p: parcel() }, { account_id: 'other' }).shadowRoot.innerHTML, /Aucun colis/);
  assert.match(card({ p: parcel() }, { direction: 'outgoing' }).shadowRoot.innerHTML, /Aucun colis/);
  assert.match(card({ p: parcel({ user_type: 'SENDER' }) }, { direction: 'outgoing' }).shadowRoot.innerHTML, /Synthetic parcel/);
});

test('returned parcels are not labelled delivered', () => {
  const html = card({ p: parcel({}, 'returned') }).shadowRoot.innerHTML;
  assert.match(html, /Retourné à l’expéditeur/);
  assert.doesNotMatch(html, /Livré/);
});

test('discreet mode removes personal details from DOM, including map targets', () => {
  const html = card({ p: parcel({ friendly_name: 'private-name', tracking_number: 'private-code',
    last_event: 'private-description', pickup_name: 'private-pickup', pickup_address: 'private-address',
    live_available: true, live_eta: 'private-eta', events: [{ description: 'private-history' }],
  }), t: tracker() }, { privacy_mode: true }).shadowRoot.innerHTML;
  assert.doesNotMatch(html, /private-|data-entity|data-courier|sensor\.renamed_parcel/);
  assert.match(html, /Colis 1/);
  assert.match(html, /En tournée/);
  const unknown = card({ p: parcel({ list_status: 'private-raw-code' }, 'unknown') }, { privacy_mode: true });
  assert.match(unknown.shadowRoot.innerHTML, /Inconnu/);
  assert.doesNotMatch(unknown.shadowRoot.innerHTML, /private-raw/);
});

test('live section can be hidden independently of normal details', () => {
  const html = card({ p: parcel({ live_available: true, stops_remaining: 8 }) }, { show_live: false }).shadowRoot.innerHTML;
  assert.match(html, /Synthetic parcel/);
  assert.doesNotMatch(html, /<dd>8|Livraison en direct|data-courier=/);
});

test('sorting is deterministic and invalid delivery dates come last', () => {
  const make = (id, date, state = 'in_transit') => ({ ...parcel({ friendly_name: id, tracking_number: id, delivery_date: date }, state), entity_id: `sensor.${id}` });
  const states = { a: make('Later', '2026-10-08'), b: make('Invalid', '2026-02-31'), c: make('Sooner', '07/10/2026', 'problem') };
  const html = card(states, { sort_by: 'delivery_date' }).shadowRoot.innerHTML;
  assert.ok(html.indexOf('Sooner') < html.indexOf('Later'));
  assert.ok(html.indexOf('Later') < html.indexOf('Invalid'));
  const priority = card(states).shadowRoot.innerHTML;
  assert.ok(priority.indexOf('Sooner') < priority.indexOf('Later'));
  const name = card(states, { sort_by: 'name' }).shadowRoot.innerHTML;
  assert.ok(name.indexOf('Invalid') < name.indexOf('Later'));
  states.a.attributes.last_event_ts = '2026-10-06T10:00:00Z';
  states.c.attributes.last_event_ts = '2026-10-06T11:00:00Z';
  const updated = card(states, { sort_by: 'updated' }).shadowRoot.innerHTML;
  assert.ok(updated.indexOf('Sooner') < updated.indexOf('Later'));
  assert.ok(updated.indexOf('Later') < updated.indexOf('Invalid'));
});

test('YAML configuration rejects invalid options without coercing string booleans', () => {
  for (const config of [{ show_history: 'false' }, { privacy_mode: 1 }, { direction: 'other' }, { sort_by: 'invalid' }, {view:'invalid'}, {deduplicate:'false'}, {group:3}]) {
    assert.throws(() => card({}, config));
  }
});

test('deduplication prefers available, newest source and account on ties', () => {
  const account = parcel({friendly_name:'Account source',last_fetch:'2026-10-06T10:00:00Z'});
  const manual = {...parcel({friendly_name:'Manual source',tracking_source:'public',account_id:'manual',last_fetch:'2026-10-06T10:00:00Z'}),entity_id:'sensor.manual'};
  let html=card({a:account,b:manual}).shadowRoot.innerHTML;
  assert.match(html,/Account source/);assert.doesNotMatch(html,/Manual source/);
  manual.attributes.last_fetch='2026-10-06T11:00:00Z';
  html=card({a:account,b:manual}).shadowRoot.innerHTML;
  assert.match(html,/Manual source/);assert.doesNotMatch(html,/Account source/);
  manual.state='unavailable';
  assert.match(card({a:account,b:manual}).shadowRoot.innerHTML,/Account source/);
  html=card({a:account,b:manual},{deduplicate:false}).shadowRoot.innerHTML;
  assert.match(html,/Account source/);assert.match(html,/Manual source/);
  assert.match(card({a:account,b:manual},{account_id:'manual'}).shadowRoot.innerHTML,/Manual source/);
});

test('today view groups actions, filters inactive parcels and uses HA timezone', () => {
  const result=card({}, {view:'today'});
  const make=(id,state,attrs={})=>({...parcel({tracking_number:id,friendly_name:id,...attrs},state),entity_id:`sensor.${id}`});
  const local=new Intl.DateTimeFormat('en-CA',{timeZone:'Pacific/Kiritimati',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const states={a:make('ExpectedToday','in_transit',{delivery_date:local}),b:make('CollectMe','at_pickup_point'),c:make('FixMe','problem'),d:make('Tomorrow','in_transit',{delivery_date:'2999-01-01'}),e:make('Finished','delivered',{active:false,delivery_date:local})};
  result.hass={language:'fr',config:{time_zone:'Pacific/Kiritimati'},states};
  const html=result.shadowRoot.innerHTML;
  for(const label of ['ExpectedToday','CollectMe','FixMe','À retirer','À résoudre'])assert.match(html,new RegExp(label));
  assert.doesNotMatch(html,/Tomorrow|Finished/);
  assert.equal(result._count,3);
});

test('group selection and health warnings preserve discreet mode', () => {
  const states={p:parcel({parcel_group:'Home'}),health:{entity_id:'sensor.health',state:'auth_required',attributes:{integration:'my_bpost',health_sensor:true,account_id:'account-a',friendly_name:'Private account'}}};
  assert.doesNotMatch(card(states,{group:'Work'}).shadowRoot.innerHTML,/Synthetic parcel/);
  const html=card(states,{privacy_mode:true,view:'today'}).shadowRoot.innerHTML;
  assert.match(html,/Connexion à renouveler/);
  assert.doesNotMatch(html,/Private account|Synthetic parcel|fiction|data-courier/);
});

test('editor is discoverable, preserves unknown fields and emits config-changed', () => {
  const editor = card({}).constructor.getConfigElement();
  editor.setConfig({ type: 'custom:my-bpost-parcels-card', custom_future_option: 42, account_id: 'missing-account' });
  editor.hass = { language: 'fr', states: {} };
  assert.match(editor.shadowRoot.innerHTML, /Compte indisponible/);
  editor.shadowRoot.listeners.change({ target: { name: 'privacy_mode', type: 'checkbox', checked: true } });
  assert.equal(editor.event.type, 'config-changed');
  assert.equal(editor.event.composed, true);
  assert.equal(editor.event.detail.config.privacy_mode, true);
  assert.equal(editor.event.detail.config.custom_future_option, 42);
  assert.equal(editor.event.detail.config.account_id, 'missing-account');
  editor.shadowRoot.listeners.change({ target: { name: 'account_id', type: 'select-one', value: '' } });
  assert.equal(editor.event.detail.config.account_id, undefined);
});

test('editor fetches account labels once and escapes their text', async () => {
  const editor = card({}).constructor.getConfigElement();
  editor.setConfig({});
  let calls = 0;
  const hass = { language: 'fr', states: { p: parcel() }, callWS: async (request) => {
    calls++;
    assert.equal(request.domain, 'my_bpost');
    return [{ domain: 'my_bpost', entry_id: 'account-a', title: '<script>private label</script>' }];
  } };
  editor.hass = hass;
  editor.hass = hass;
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls, 1);
  assert.match(editor.shadowRoot.innerHTML, /&lt;script&gt;/);
  assert.doesNotMatch(editor.shadowRoot.innerHTML, /<script>/);
});

test('editor still lists accounts when config-entry access fails', async () => {
  const editor = card({}).constructor.getConfigElement();
  editor.setConfig({ account_id: 'account-a' });
  editor.hass = { language: 'fr', states: { p: parcel() }, callWS: async () => { throw new Error('not allowed'); } };
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(editor.shadowRoot.innerHTML, /value="account-a" selected/);
});
