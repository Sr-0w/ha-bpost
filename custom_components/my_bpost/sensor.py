"""Sensor platform for the My bpost integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_RETENTION_DAYS, DOMAIN
from .coordinator import (
    BpostData,
    BpostDataUpdateCoordinator,
    detail_status,
    is_parcel_active,
)
from .pybpost.models import ParcelDetail


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BpostDataUpdateCoordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _async_add_new() -> None:
        data = coordinator.data or BpostData()
        codes = [c for c in data.summaries if c not in known]
        if not codes:
            return
        entities = [BpostParcelSensor(coordinator, entry, code) for code in codes]
        known.update(codes)
        async_add_entities(entities)

    _async_add_new()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new))
    async_add_entities([BpostPackagesSensor(coordinator, entry)])
    hass.async_create_task(_async_purge_stale(hass, entry, coordinator))


async def _async_purge_stale(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: BpostDataUpdateCoordinator,
) -> None:
    """Remove entities for parcels long gone from the account list."""
    from datetime import timedelta

    from homeassistant.helpers import entity_registry as er

    from homeassistant.util import dt as dt_util

    retention = timedelta(
        days=entry.options.get("retention_days", DEFAULT_RETENTION_DAYS))
    data = coordinator.data or BpostData()
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        code = entity.unique_id
        if code in ("packages", "", None) or code in data.summaries:
            continue
        # Unknown parcels: drop when the entry data is older than retention.
        # (Creation time is the only reliable local signal at this stage.)
        created = entity.created_at if hasattr(entity, "created_at") else None
        _ = (retention, created, dt_util.utcnow())
        # Conservative v0: keep entities; purge wired in a later version
        # once last-seen timestamps are persisted.


class BpostPackagesSensor(
    CoordinatorEntity[BpostDataUpdateCoordinator], SensorEntity
):
    """Global sensor: number of active parcels."""

    _attr_has_entity_name = True
    _attr_name = "Packages"
    _attr_icon = "mdi:package-variant"

    def __init__(self, coordinator: BpostDataUpdateCoordinator,
                 entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = "packages"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="My bpost",
            manufacturer="bpost",
            model="My bpost account",
        )

    @property
    def native_value(self) -> int:
        data = self.coordinator.data or BpostData()
        return sum(1 for code in data.summaries if is_parcel_active(code, data))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or BpostData()
        codes = sorted(data.summaries)
        return {
            "total": len(codes),
            "active_codes": [c for c in codes if is_parcel_active(c, data)],
            "last_fetch": data.last_fetch.isoformat() if data.last_fetch else None,
        }


class BpostParcelSensor(
    CoordinatorEntity[BpostDataUpdateCoordinator], SensorEntity
):
    """One sensor per parcel."""

    _attr_icon = "mdi:package"

    def __init__(self, coordinator: BpostDataUpdateCoordinator,
                 entry: ConfigEntry, item_code: str) -> None:
        super().__init__(coordinator)
        self._item_code = item_code
        self._attr_unique_id = item_code
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="My bpost",
            manufacturer="bpost",
            model="My bpost account",
        )

    @property
    def _detail(self) -> ParcelDetail | None:
        data = self.coordinator.data or BpostData()
        return data.details.get(self._item_code)

    @property
    def name(self) -> str:
        detail = self._detail
        label = None
        if detail:
            if detail.user_type == "SENDER":
                label = detail.receiver.name or detail.title
            else:
                label = detail.sender.name or detail.title
        suffix = self._item_code[-6:] if len(self._item_code) > 6 else self._item_code
        return f"Parcel {label}" if label else f"Parcel {suffix}"

    @property
    def native_value(self) -> str:
        detail = self._detail
        if detail:
            return detail_status(detail)
        data = self.coordinator.data or BpostData()
        summary = data.summaries.get(self._item_code)
        return summary.status if summary and summary.status else "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        detail = self._detail
        data = self.coordinator.data or BpostData()
        summary = data.summaries.get(self._item_code)
        attrs: dict[str, Any] = {
            "tracking_number": self._item_code,
            "list_status": summary.status if summary else None,
            "last_event_ts": summary.latest_event_ts if summary else None,
            "active": is_parcel_active(self._item_code, data),
        }
        if not detail:
            return attrs
        last = detail.last_event
        point = detail.delivery_point
        if point is not None:
            attrs.update({
                "pickup_name": point.name,
                "pickup_address": point.address,
                "pickup_city": point.city,
                "pickup_postcode": point.postcode,
                "pickup_type": point.kind,
                "pickup_latitude": point.latitude,
                "pickup_longitude": point.longitude,
            })
        if detail.delivered_day or detail.delivered_time:
            attrs["delivered_at"] = " ".join(
                p for p in (detail.delivered_day, detail.delivered_time) if p)
        attrs.update({
            "sender": detail.sender.name,
            "sender_city": detail.sender.city,
            "receiver_city": detail.receiver.city,
            "user_type": detail.user_type,
            "parcel_type": detail.parcel_type,
            "product_type": detail.product_type,
            "delivery_date": detail.eta.day or None,
            "delivery_window_start": detail.eta.time1 or None,
            "delivery_window_end": detail.eta.time2 or None,
            "last_event": last.description if last else None,
            "last_event_location": last.location if last else None,
            "events_count": len(detail.events),
            "events": [
                {
                    "date": event.date,
                    "time": event.time,
                    "description": event.description,
                    "location": event.location or None,
                }
                for event in detail.events
            ],
        })
        return attrs
