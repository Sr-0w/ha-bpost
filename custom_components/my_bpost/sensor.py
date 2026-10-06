"""Sensor platform for the My bpost integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .entity import unique_id
from .coordinator import (
    BpostData,
    BpostDataUpdateCoordinator,
    detail_status,
    is_parcel_active,
    parcel_status,
)
from .pybpost.models import ParcelDetail
from .pybpost.status import ParcelStatus
from .pybpost.mail import MailCapability
from .mail import BpostMailCoordinator


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
        known.difference_update(coordinator.expired_codes)
        codes = [c for c in data.summaries if c not in known]
        if not codes:
            return
        entities = [BpostParcelSensor(coordinator, entry, code) for code in codes]
        known.update(codes)
        async_add_entities(entities)

    _async_add_new()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new))
    async_add_entities([BpostPackagesSensor(coordinator, entry, direction)
                        for direction in (None, "incoming", "outgoing")])
    async_add_entities([BpostHealthSensor(coordinator, entry)])
    if entry.data.get("source") != "public":
        async_add_entities([BpostMailSensor(coordinator.mail, entry, status=status) for status in (False, True)])


class BpostHealthSensor(CoordinatorEntity[BpostDataUpdateCoordinator], SensorEntity):
    """Stay readable during a failed refresh, instead of becoming unavailable."""

    _attr_has_entity_name = True
    _attr_translation_key = "health"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_options = ["starting","ok","auth_required","rate_limited","maintenance",
                     "outdated_client","not_found","service_unavailable"]

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = unique_id(entry,"health")
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN,entry.entry_id)})

    @property
    def available(self):
        return True

    @property
    def native_value(self):
        return self.coordinator.health

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.mail.async_add_listener(self.async_write_ha_state))
        self.async_on_remove(self.coordinator.live.async_add_listener(self.async_write_ha_state))

    @property
    def extra_state_attributes(self):
        c = self.coordinator
        public = self._entry.data.get("source") == "public"
        return {"integration":DOMAIN,"account_id":self._entry.entry_id,"health_sensor":True,
            "parcel_group":self._entry.options.get("group",self._entry.data.get("group","")),
            "last_success":c.data.last_fetch.isoformat() if c.data and c.data.last_fetch else None,
            "last_attempt":c.last_attempt.isoformat() if c.last_attempt else None,
            "retry_at":c.retry_at.isoformat() if c.retry_at else None,
            "mail_capability":"unsupported" if public else c.mail.data.capability.value,
            "mail_health":"unsupported" if public else "ok" if c.mail.last_update_success else "service_unavailable",
            "courier_capability":"unsupported" if public else "disabled" if not self._entry.options.get("enable_live_tracking",True)
                else "available" if any(c.live.current(code) for code in c.live_targets()) else "not_available"}


class BpostMailSensor(CoordinatorEntity[BpostMailCoordinator], SensorEntity):
    """Capability is distinct from the count in the rolling 30-day mail window."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:email-outline"

    def __init__(self, coordinator: BpostMailCoordinator, entry: ConfigEntry, *, status: bool) -> None:
        super().__init__(coordinator)
        self._status = status
        self._entry_id = entry.entry_id
        key = "mail_status" if status else "mail_count"
        self._attr_unique_id = unique_id(entry, key)
        self._attr_translation_key = key
        if status:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = [capability.value for capability in MailCapability]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name=entry.title if entry.data.get("source") == "public" else "My bpost",
            manufacturer="bpost", model="Public parcel tracking" if entry.data.get("source") == "public" else "My bpost account")

    @property
    def available(self) -> bool:
        return super().available and (self._status or self.coordinator.mailbox_available)

    @property
    def native_value(self) -> str | int:
        return self.coordinator.data.capability.value if self._status else len(self.coordinator.data.letters)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"integration": DOMAIN, "account_id": self._entry_id,
                "mail_window_days": 30, "last_fetch": (
                    self.coordinator.data.last_fetch.isoformat() if self.coordinator.data.last_fetch else None)}


class BpostPackagesSensor(
    CoordinatorEntity[BpostDataUpdateCoordinator], SensorEntity
):
    """Global sensor: number of active parcels."""

    _attr_has_entity_name = True
    _attr_name = "Packages"
    _attr_icon = "mdi:package-variant"

    def __init__(self, coordinator: BpostDataUpdateCoordinator,
                 entry: ConfigEntry, direction: str | None = None) -> None:
        super().__init__(coordinator)
        self._direction = direction
        self._entry_id = entry.entry_id
        self._attr_unique_id = unique_id(entry, f"{direction}_packages" if direction else "packages")
        if direction:
            self._attr_name = f"{direction.title()} packages"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title if entry.data.get("source") == "public" else "My bpost",
            manufacturer="bpost",
            model="Public parcel tracking" if entry.data.get("source") == "public" else "My bpost account",
        )

    @property
    def native_value(self) -> int:
        data = self.coordinator.data or BpostData()
        return sum(1 for code in data.summaries if is_parcel_active(code, data) and self._matches(code, data))

    def _matches(self, code: str, data: BpostData) -> bool:
        if self._direction is None:
            return True
        detail = data.details.get(code)
        # Missing account-role data is not silently classified as incoming.
        if detail is None or detail.user_type not in ("SENDER", "RECEIVER"):
            return False
        return (detail.user_type == "SENDER") == (self._direction == "outgoing")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or BpostData()
        codes = sorted(code for code in data.summaries if self._matches(code, data))
        return {
            "integration": DOMAIN,
            "account_id": self._entry_id,
            "total": len(codes),
            "active_codes": [c for c in codes if is_parcel_active(c, data)],
            "last_fetch": data.last_fetch.isoformat() if data.last_fetch else None,
        }


class BpostParcelSensor(
    CoordinatorEntity[BpostDataUpdateCoordinator], SensorEntity
):
    """One sensor per parcel."""

    _attr_icon = "mdi:package"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [status.value for status in ParcelStatus]
    _attr_translation_key = "parcel"

    def __init__(self, coordinator: BpostDataUpdateCoordinator,
                 entry: ConfigEntry, item_code: str) -> None:
        super().__init__(coordinator)
        self._item_code = item_code
        self._entry_id = entry.entry_id
        self._attr_unique_id = unique_id(entry, item_code)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title if entry.data.get("source") == "public" else "My bpost",
            manufacturer="bpost",
            model="Public parcel tracking" if entry.data.get("source") == "public" else "My bpost account",
        )

    @property
    def _detail(self) -> ParcelDetail | None:
        data = self.coordinator.data or BpostData()
        return data.details.get(self._item_code)

    @property
    def name(self) -> str:
        detail = self._detail
        if (detail and detail.title and
                self.coordinator.config_entry.data.get("source") == "public"):
            return detail.title
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
        data = self.coordinator.data or BpostData()
        return parcel_status(self._item_code, data).value

    @property
    def available(self) -> bool:
        return super().available and self._item_code in (self.coordinator.data or BpostData()).summaries

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.live.async_add_listener(self._handle_coordinator_update))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        detail = self._detail
        data = self.coordinator.data or BpostData()
        summary = data.summaries.get(self._item_code)
        attrs: dict[str, Any] = {
            "integration": DOMAIN,
            "account_id": self._entry_id,
            "tracking_number": self._item_code,
            "tracking_source": self.coordinator.config_entry.data.get("source", "account"),
            "last_fetch": data.last_fetch.isoformat() if data.last_fetch else None,
            "parcel_group": self.coordinator.config_entry.options.get("group", self.coordinator.config_entry.data.get("group", "")),
            "raw_status": detail_status(detail) if detail else summary.status if summary else None,
            "list_status": summary.status if summary else None,
            "last_event_ts": summary.latest_event_ts if summary else None,
            "active": is_parcel_active(self._item_code, data),
        }
        observation = self.coordinator.live.current(self._item_code)
        attrs["live_available"] = observation is not None
        if observation is not None:
            live = observation.status
            attrs.update({
                "stops_remaining": live.stops_until_target,
                "live_eta": live.eta_window,
                # Backend units are not yet proven: never advertise this as a percentage.
                "live_progress_raw": live.progress_until_target,
                "live_updated_at": observation.observed_at.isoformat(),
            })
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
