"""Expire inactive parcel entities only after successful account refreshes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers import entity_registry as er

from .const import DEFAULT_RETENTION_DAYS, DOMAIN
from .entity import unique_id

if TYPE_CHECKING:
    from .coordinator import BpostData, BpostDataUpdateCoordinator


def apply_retention(coordinator: BpostDataUpdateCoordinator, data: BpostData, now: float) -> None:
    """Persist inactivity age, filter history and remove only owned parcel entities.

    Start the clock when inactivity is first observed, never from an ambiguous
    backend event date. A renewed active parcel resets its inactivity clock.
    """
    entry = coordinator.config_entry
    registry = er.async_get(coordinator.hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    codes = set(data.summaries) | set(data.details) | set(coordinator._inactive_since)
    # Also retire entities left by earlier versions or absent from the API.
    prefix = f"{entry.entry_id}_"
    for entity in entities:
        if entity.platform != DOMAIN or entity.domain != "sensor":
            continue
        key = entity.unique_id.removeprefix(prefix)
        if key not in {"packages", "incoming_packages", "outgoing_packages", "mail_count", "mail_status", "health"}:
            codes.add(key)
    age_limit = entry.options.get("retention_days", DEFAULT_RETENTION_DAYS) * 86400
    expired = set()
    for code in codes:
        if code in data.active_codes:
            coordinator._inactive_since.pop(code, None)
            continue
        since = coordinator._inactive_since.setdefault(code, now)
        if now - since >= age_limit:
            expired.add(code)
    # Keep the expiration marker while the API still returns historical parcels,
    # so they cannot be recreated on the next refresh or restart.
    coordinator._inactive_since = {
        code: since for code, since in coordinator._inactive_since.items()
        if code not in expired or code in data.summaries or code in data.details
    }
    coordinator.expired_codes = expired
    identities = {
        "sensor": {identity for code in expired for identity in (code, unique_id(entry, code))},
        "device_tracker": {identity for code in expired for key in (f"{code}_tracker", f"{code}_courier")
                           for identity in (key, unique_id(entry, key))},
    }
    for entity in entities:
        if (entity.platform == DOMAIN and entity.domain in {"sensor", "device_tracker"}
                and entity.unique_id in identities[entity.domain]):
            registry.async_remove(entity.entity_id)
    for code in expired:
        data.summaries.pop(code, None)
        data.details.pop(code, None)
