"""Shared parcel selection for summaries and grouped notifications."""

from datetime import datetime

from homeassistant.util import dt as dt_util


def parcel_states(hass, *, entry_id=None, group=None):
    return [state for state in hass.states.async_all("sensor")
            if state.attributes.get("integration") == "my_bpost"
            and state.attributes.get("tracking_number")
            and (entry_id is None or state.attributes.get("account_id") == entry_id)
            and (group is None or state.attributes.get("parcel_group", "") == group)]


def source_rank(state):
    fetched = state.attributes.get("last_fetch")
    timestamp = dt_util.parse_datetime(fetched) if isinstance(fetched, str) else None
    return (state.state not in ("unavailable", "unknown"),
            timestamp.timestamp() if timestamp else 0,
            state.attributes.get("tracking_source", "account") == "account")


def select_parcels(states):
    """Exact carrier IDs only. Never merge fields from different observations."""
    selected = {}
    for state in sorted(states, key=lambda item: item.entity_id):
        key = state.attributes["tracking_number"]
        if key not in selected or source_rank(state) > source_rank(selected[key]):
            selected[key] = state
    return selected


def parcel_day(value):
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass
    return None


def summary(hass, *, entry_id=None, group=None):
    states = parcel_states(hass, entry_id=entry_id, group=group)
    chosen = select_parcels(states).values()
    today = dt_util.now().date()
    result = dict(today=0, pickup=0, problem=0, active=0, unavailable=0,
                  duplicates=len(states)-len(chosen), parcels=len(chosen))
    for state in chosen:
        if state.state in ("unavailable", "unknown"):
            result["unavailable"] += 1
            continue
        if state.attributes.get("active") is False:
            continue
        result["active"] += 1
        if state.state == "problem":
            result["problem"] += 1
        elif state.state == "at_pickup_point":
            result["pickup"] += 1
        elif state.state == "out_for_delivery" or parcel_day(state.attributes.get("delivery_date")) == today:
            result["today"] += 1
    result["as_of"] = dt_util.utcnow().isoformat()
    return result
