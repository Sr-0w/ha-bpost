"""Read-only delivery estimates, one Home Assistant calendar per account."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import BpostData, BpostDataUpdateCoordinator, parcel_status
from .entity import unique_id
from .pybpost.status import ParcelStatus

BPOST_TIME_ZONE = ZoneInfo("Europe/Brussels")


def _date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    return None


def _time(value: str | None) -> time | None:
    if not value:
        return None
    try:
        parsed = time.fromisoformat(value.strip())
        return parsed if parsed.tzinfo is None else None
    except ValueError:
        return None


def delivery_events(data: BpostData, account_id: str) -> list[CalendarEvent]:
    events = []
    for code, detail in data.details.items():
        # Completed/history parcels must not retain a misleading future ETA.
        if (code not in data.active_codes
                or parcel_status(code, data) in {ParcelStatus.DELIVERED, ParcelStatus.RETURNED}):
            continue
        day = _date(detail.eta.day)
        if day is None:
            continue
        start_time, end_time = _time(detail.eta.time1), _time(detail.eta.time2)
        start, end = day, day + timedelta(days=1)
        if start_time is not None and end_time is not None and end_time > start_time:
            start = datetime.combine(day, start_time, BPOST_TIME_ZONE)
            end = datetime.combine(day, end_time, BPOST_TIME_ZONE)
        label = (detail.receiver.name if detail.user_type == "SENDER" else detail.sender.name)
        label = label or detail.title or code
        point = detail.delivery_point
        events.append(CalendarEvent(
            start=start, end=end, summary=f"bpost · {label}",
            description=f"{code}\n{parcel_status(code, data).value}",
            location=point.address if point else None,
            uid=f"{account_id}_{code}",
        ))
    return sorted(events, key=lambda event: (event.start_datetime_local, event.uid))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                           async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([BpostDeliveryCalendar(entry.runtime_data, entry)])


class BpostDeliveryCalendar(CoordinatorEntity[BpostDataUpdateCoordinator], CalendarEntity):
    """Estimated windows only; missing times fall back to an all-day event."""

    _attr_has_entity_name = True
    _attr_translation_key = "deliveries"
    _attr_icon = "mdi:calendar-truck"

    def __init__(self, coordinator: BpostDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_unique_id = unique_id(entry, "deliveries")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name=entry.title if entry.data.get("source") == "public" else "My bpost",
            manufacturer="bpost", model="Public parcel tracking" if entry.data.get("source") == "public" else "My bpost account")

    @property
    def _events(self) -> list[CalendarEvent]:
        return delivery_events(self.coordinator.data or BpostData(), self._entry_id)

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.utcnow()
        return next((event for event in self._events if event.end_datetime_local > now), None)

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime,
                               end_date: datetime) -> list[CalendarEvent]:
        return [event for event in self._events
                if event.start_datetime_local < end_date and event.end_datetime_local > start_date]
