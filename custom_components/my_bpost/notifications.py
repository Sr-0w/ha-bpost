"""Coalesce parcel updates and persist notification baselines across sources."""

import asyncio
from datetime import datetime
from hashlib import sha256

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .selection import parcel_states, select_parcels, parcel_day

KEY = "my_bpost_notifications"
WINDOW_SECONDS = 30
EVENT = "my_bpost_notification"
RAW_EVENTS = ("new_package", "status_changed", "out_for_delivery", "at_pickup_point",
              "delivered", "returned", "problem", "eta_changed")


def identity(code):
    return sha256(code.encode()).hexdigest()


def eta_shift(old, new):
    if (not isinstance(old,(list,tuple)) or not isinstance(new,(list,tuple))
            or len(old)!=3 or len(new)!=3):
        return 0
    old_day, new_day = parcel_day(old[0]), parcel_day(new[0])
    if old_day is None or new_day is None:
        return 0
    if old_day != new_day:
        return abs((new_day-old_day).days)*1440
    shifts = []
    for left, right in zip(old[1:], new[1:]):
        try:
            a, b = datetime.strptime(left, "%H:%M"), datetime.strptime(right, "%H:%M")
            shifts.append(abs((a-b).total_seconds())/60)
        except (TypeError, ValueError):
            pass
    return max(shifts, default=0)


def observation(state):
    a = state.attributes
    return {"status": state.state,
            "eta": [a.get("delivery_date"), a.get("delivery_window_start"), a.get("delivery_window_end")]
                   if a.get("delivery_date") else None,
            "updated_at": dt_util.utcnow().timestamp()}


def seed_eta(record, current):
    """Fill missing ETA fields without advancing an existing change baseline."""
    eta = current["eta"]
    previous = record.get("eta")
    if previous is None:
        record["eta"] = eta
    elif isinstance(previous, (list, tuple)) and len(previous) == 3 and eta and previous[0] == eta[0]:
        record["eta"] = [old if old is not None else new for old, new in zip(previous, eta)]


class NotificationHub:
    def __init__(self, hass):
        self.hass = hass
        self.store = Store(hass, 1, KEY)
        self.records = {}
        self.pending = {}
        self.timer = None
        self.lock = asyncio.Lock()
        self.unsubs = []
        self.stopped = False

    async def async_setup(self):
        stored = await self.store.async_load()
        if isinstance(stored, dict):
            cutoff = dt_util.utcnow().timestamp()-60*86400
            self.records = {key: value for key, value in stored.items()
                            if isinstance(value, dict) and isinstance(value.get("updated_at"), (int,float))
                            and value["updated_at"] > cutoff}
        for kind in RAW_EVENTS:
            self.unsubs.append(self.hass.bus.async_listen(f"my_bpost_{kind}", self.enqueue))
        self.unsubs.append(self.hass.bus.async_listen("state_changed", self.observe))
        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.stop)

    @callback
    def enqueue(self, event):
        code = event.data.get("item_code")
        if not isinstance(code, str) or not code:
            return
        self.pending[identity(code)] = code
        if self.timer is None:
            self.timer = self.hass.loop.call_later(WINDOW_SECONDS, self.schedule)

    @callback
    def schedule(self):
        self.timer = None
        self.hass.async_create_task(self.async_flush())

    @callback
    def observe(self, event):
        state = event.data.get("new_state")
        if not state or state.state in ("unavailable", "unknown"):
            return
        a = state.attributes
        if a.get("integration") != "my_bpost" or not a.get("tracking_number") or state.domain != "sensor":
            return
        key = identity(a["tracking_number"])
        if key not in self.records and key not in self.pending:
            self.records[key] = observation(state)
            self.store.async_delay_save(lambda: self.records, 5)
        elif key in self.records and key not in self.pending:
            chosen = select_parcels(parcel_states(self.hass)).get(a["tracking_number"])
            record = self.records[key]
            if chosen and record.get("status") == chosen.state:
                previous_eta = record.get("eta")
                seed_eta(record, observation(chosen))
                if previous_eta != record.get("eta"):
                    self.store.async_delay_save(lambda: self.records, 5)

    async def async_flush(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        async with self.lock:
            pending, self.pending = self.pending, {}
            chosen = select_parcels(parcel_states(self.hass))
            messages = []
            now = dt_util.utcnow().timestamp()
            self.records = {k:v for k,v in self.records.items() if now-v.get("updated_at",now) < 60*86400}
            for key, code in pending.items():
                state = chosen.get(code)
                if state is None or state.state in ("unavailable", "unknown"):
                    continue
                old = self.records.get(key)
                current = observation(state)
                entry = self.hass.config_entries.async_get_entry(state.attributes.get("account_id"))
                threshold = entry.options.get("eta_change_minutes",30) if entry else 30
                shift = eta_shift(old.get("eta") if old else None, current["eta"])
                kind = None
                if old is None:
                    kind = "new_package"
                elif old.get("status") != current["status"]:
                    kind = current["status"] if current["status"] in RAW_EVENTS else "status_changed"
                elif shift >= threshold:
                    kind = "eta_changed"
                if kind is None:
                    # Keep the last notified ETA, so small shifts can accumulate.
                    if old:
                        old["updated_at"] = now
                        seed_eta(old, current)
                    continue
                if current["eta"] is None and old:
                    current["eta"] = old.get("eta")
                self.records[key] = current
                messages.append({"parcel_id": key, "entry_id": state.attributes.get("account_id"),
                    "event_type": f"my_bpost_{kind}", "status": state.state,
                    "item_code": code, "new_eta": current["eta"], "eta_shift_minutes": shift,
                    "direction": {"SENDER":"outgoing", "RECEIVER":"incoming"}.get(state.attributes.get("user_type"),"unknown")})
            # No codes, names or postcodes in the persisted cross-source baseline.
            await self.store.async_save(self.records)
            for payload in messages:
                self.hass.bus.async_fire(EVENT, payload)

    async def stop(self, event):
        if self.stopped:
            return
        self.stopped = True
        if self.timer:
            self.timer.cancel()
            self.timer = None
        for unsub in self.unsubs:
            unsub()
        self.pending.clear()
        async with self.lock:
            await self.store.async_save(self.records)
