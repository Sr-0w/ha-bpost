"""Diagnostics for the My bpost integration (personal data redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import CONF_ACCESS_TOKEN, CONF_PASSWORD, CONF_REFRESH_TOKEN, CONF_USERNAME, DOMAIN
from .coordinator import BpostData, BpostDataUpdateCoordinator


def _redact_person(person: Any) -> dict[str, Any]:
    return {
        "city": "**REDACTED**",
        "country": "**REDACTED**",
        "postcode": "**REDACTED**",
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: BpostDataUpdateCoordinator = entry.runtime_data
    data: BpostData = coordinator.data or BpostData()
    aliases = {code: f"parcel_{i}" for i, code in enumerate(
        sorted(data.summaries.keys() | data.details.keys()), start=1)}
    details: dict[str, Any] = {}
    for code, detail in data.details.items():
        details[aliases[code]] = {
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
            "unique_id": "**REDACTED**",
            "app_lang": entry.data.get("app_lang"),
            "source": entry.data.get("source", "account"),
            "barcode": "**REDACTED**",
            "postal_code": "**REDACTED**",
            "label": "**REDACTED**",
            "group": "**REDACTED**",
            CONF_USERNAME: "**REDACTED**",
            CONF_PASSWORD: "**REDACTED**",
            CONF_ACCESS_TOKEN: "**REDACTED**",
            CONF_REFRESH_TOKEN: "**REDACTED**",
            "options": {key: entry.options[key] for key in (
                "retention_days", "scan_interval_minutes", "enable_mail", "enable_mail_images", "eta_change_minutes") if key in entry.options},
        },
        "devices": [
            {"identifiers": "**REDACTED**", "name": "**REDACTED**"}
            for d in device_registry.devices.values()
            if entry.entry_id in d.config_entries
        ],
        "entities": [
            {"entity_id": "**REDACTED**", "unique_id": "**REDACTED**",
             "disabled": e.disabled}
            for e in entity_registry.entities.values()
            if e.config_entry_id == entry.entry_id
        ],
        "coordinator": {
            "health": coordinator.health,
            "last_attempt": coordinator.last_attempt.isoformat() if coordinator.last_attempt else None,
            "retry_at": coordinator.retry_at.isoformat() if coordinator.retry_at else None,
            "last_fetch": data.last_fetch.isoformat() if data.last_fetch else None,
            "summaries": {
                aliases[code]: {
                    "status": s.status,
                    "latest_event_ts": s.latest_event_ts,
                }
                for code, s in data.summaries.items()
            },
            "details": details,
        },
        "domain": DOMAIN,
        "mail": {
            "last_update_success": coordinator.mail.last_update_success,
            "capability": coordinator.mail.data.capability.value,
            "count": len(coordinator.mail.data.letters) if coordinator.mail.mailbox_available else None,
        },
    }
