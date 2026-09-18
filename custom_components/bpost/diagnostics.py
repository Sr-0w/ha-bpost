"""Diagnostics for the bpost integration (personal data redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import CONF_PASSWORD, CONF_USERNAME, DOMAIN
from .coordinator import BpostData, BpostDataUpdateCoordinator


def _redact_person(person: Any) -> dict[str, Any]:
    return {
        "city": person.city,
        "country": person.country,
        "postcode": person.postcode,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: BpostDataUpdateCoordinator = entry.runtime_data
    data: BpostData = coordinator.data or BpostData()
    details: dict[str, Any] = {}
    for code, detail in data.details.items():
        details[code[-6:]] = {
            "current_status": detail.current_status,
            "parcel_main_status": detail.parcel_main_status,
            "user_type": detail.user_type,
            "parcel_type": detail.parcel_type,
            "eta": {
                "day": detail.eta.day,
                "time1": detail.eta.time1,
                "time2": detail.eta.time2,
            },
            "events": len(detail.events),
            "sender": _redact_person(detail.sender),
            "receiver": _redact_person(detail.receiver),
        }
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    return {
        "entry": {
            "unique_id": entry.unique_id,
            "app_lang": entry.data.get("app_lang"),
            CONF_USERNAME: "**REDACTED**",
            CONF_PASSWORD: "**REDACTED**",
            "options": dict(entry.options),
        },
        "devices": [
            {"identifiers": list(d.identifiers), "name": d.name}
            for d in device_registry.devices.values()
            if entry.entry_id in d.config_entries
        ],
        "entities": [
            {"entity_id": e.entity_id, "unique_id": e.unique_id,
             "disabled": e.disabled}
            for e in entity_registry.entities.values()
            if e.config_entry_id == entry.entry_id
        ],
        "coordinator": {
            "last_fetch": data.last_fetch.isoformat() if data.last_fetch else None,
            "summaries": {
                code[-6:]: {
                    "status": s.status,
                    "latest_event_ts": s.latest_event_ts,
                }
                for code, s in data.summaries.items()
            },
            "details": details,
        },
        "domain": DOMAIN,
    }
