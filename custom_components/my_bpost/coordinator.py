"""Data coordinator for the My bpost integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from hashlib import sha256
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    EVENT_DELIVERED,
    EVENT_NEW_PACKAGE,
    EVENT_OUT_FOR_DELIVERY,
    EVENT_STATUS_CHANGED,
    EVENT_AT_PICKUP_POINT,
    EVENT_RETURNED,
    EVENT_PROBLEM,
    EVENT_ETA_CHANGED,
)
from .pybpost.client import BpostClient
from .pybpost.exceptions import BpostAuthError, BpostError, BpostRateLimitError, BpostMaintenanceError, BpostForceUpdateError
from .pybpost.tracking import BpostTrackingNotFound
from .pybpost.models import ParcelDetail, ParcelSummary
from .pybpost.status import ParcelStatus, normalize_status
from .live import BpostLiveCoordinator
from .retention import apply_retention
from .mail import BpostMailCoordinator

_LOGGER = logging.getLogger(__name__)

@dataclass
class BpostData:
    summaries: dict[str, ParcelSummary] = field(default_factory=dict)
    details: dict[str, ParcelDetail] = field(default_factory=dict)
    # Item codes the backend itself places in the v3 "active" sections.
    # This mirrors the official app (SendReceiveRepository.addAllParcels
    # renders getActive(); history is stored separately). Never guess from
    # status strings: e.g. AnnouncementReceived is NOT active per the app.
    active_codes: set[str] = field(default_factory=set)
    last_fetch: datetime | None = None


def is_parcel_active(code: str, data: BpostData) -> bool:
    return code in data.active_codes


def _is_out_for_delivery(code: str, data: BpostData) -> bool:
    return parcel_status(code, data) == ParcelStatus.OUT_FOR_DELIVERY


def parcel_status(code: str, data: BpostData) -> ParcelStatus:
    detail = data.details.get(code)
    summary = data.summaries.get(code)
    if detail and detail.canonical_status is not None:
        return ParcelStatus(detail.canonical_status)
    return normalize_status(detail.current_status if detail else None,
                            detail.parcel_main_status if detail else None,
                            summary.status if summary else None)


def detail_status(detail: ParcelDetail) -> str:
    return detail.current_status or detail.parcel_main_status or "unknown"


class BpostDataUpdateCoordinator(DataUpdateCoordinator[BpostData]):
    """Fetch parcel list + details, detect changes, fire events."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: BpostClient,
        entry: ConfigEntry,
        *,
        scan_minutes: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="My bpost public tracking" if entry.data.get("source") == "public" else f"{DOMAIN} ({entry.unique_id})",
            update_interval=timedelta(minutes=scan_minutes),
            config_entry=entry,
        )
        self.client = client
        self.health = "starting"
        self.last_attempt = None
        self.retry_at = None
        self._scan_minutes = max(5, scan_minutes)
        self._previous: dict[str, dict[str, Any]] | None = None
        self._inactive_since: dict[str, float] = {}
        self.expired_codes: set[str] = set()
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.parcels")
        self.live = BpostLiveCoordinator(self)
        self.mail = BpostMailCoordinator(self)
        self._unsub_mail = None
        self._unsub_live = None
        self._unsub_targets = None

    async def _async_setup(self) -> None:
        stored = await self._store.async_load()
        self._previous = stored.get("parcels") if isinstance(stored, dict) else None
        if not isinstance(self._previous, dict):
            self._previous = None
        inactivity = stored.get("inactive_since", {}) if isinstance(stored, dict) else {}
        if isinstance(inactivity, dict):
            self._inactive_since = {code: since for code, since in inactivity.items()
                                    if isinstance(since, (int, float))}

    def live_targets(self) -> dict[str, str]:
        if (self.config_entry.data.get("source") == "public" or not self.data
                or not self.config_entry.options.get("enable_live_tracking", True)):
            return {}
        return {code: detail.receiver.postcode for code, detail in self.data.details.items()
                if code in self.data.active_codes and _is_out_for_delivery(code, self.data)
                and detail.receiver.postcode}

    async def async_start_live(self) -> None:
        # Keep polling for HA automations, independently of an open dashboard.
        self._unsub_live = self.live.async_add_listener(lambda: None)
        await self.live.async_refresh()

        def refresh_targets() -> None:
            self.hass.async_create_task(self.live.async_request_refresh())

        self._unsub_targets = self.async_add_listener(refresh_targets)

    async def async_start_mail(self) -> None:
        self._unsub_mail = self.mail.async_add_listener(lambda: None)
        # Optional mail failures must not prevent the parcel platforms loading.
        await self.mail.async_refresh()

    async def _async_update_data(self) -> BpostData:
        self.last_attempt = dt_util.utcnow()
        self.retry_at = None
        try:
            data = await self._async_fetch_data()
            self.health, self.retry_at = "ok", None
            return data
        except BpostAuthError as err:
            self.health = "auth_required"
            raise ConfigEntryAuthFailed("My bpost session expired; sign in again.") from err
        except BpostRateLimitError as err:
            self.health = "rate_limited"
            self.retry_at = dt_util.utcnow()+timedelta(seconds=err.retry_after)
            self.update_interval = timedelta(seconds=err.retry_after)
            raise UpdateFailed("My bpost requested a polling pause.") from err
        except BpostError as err:
            self.health = ("maintenance" if isinstance(err,BpostMaintenanceError) else
                           "outdated_client" if isinstance(err,BpostForceUpdateError) else
                           "not_found" if isinstance(err,BpostTrackingNotFound) else "service_unavailable")
            raise UpdateFailed("Unable to update My bpost parcels.") from err

    async def _async_fetch_data(self) -> BpostData:
        summaries = await self.client.get_parcels_list()
        data = BpostData(last_fetch=dt_util.utcnow())
        for summary in summaries:
            data.summaries[summary.item_code] = summary
        if summaries:
            active, history = await self.client.get_parcels_details(summaries)
            for detail in (*active, *history):
                if detail.item_code:
                    data.details[detail.item_code] = detail
            data.active_codes = {d.item_code for d in active if d.item_code}
        return await self._async_finish_fetch(data)

    async def _async_finish_fetch(self, data: BpostData) -> BpostData:
        self._detect_changes(data)
        apply_retention(self, data, dt_util.utcnow().timestamp())
        await self._store.async_save({"parcels": self._previous, "inactive_since": self._inactive_since})
        minutes = (5 if any(_is_out_for_delivery(code, data) for code in data.active_codes)
                   else self._scan_minutes if data.active_codes else max(30, self._scan_minutes))
        self.update_interval = timedelta(minutes=minutes)
        return data



    def _detect_changes(self, data: BpostData) -> None:
        now = dt_util.utcnow()
        first_fetch = self._previous is None
        previous_records = self._previous or {}
        # Remember temporarily missing parcels; don't reannounce them on return.
        current = {code: record for code, record in previous_records.items()
                   if isinstance(record, dict) and isinstance(record.get("last_seen"), (int, float))
                   and now.timestamp() - record["last_seen"] < 30 * 86400}
        for code in data.summaries:
            status = parcel_status(code, data)
            previous = previous_records.get(code)
            if not isinstance(previous, dict):
                previous = None
            detail = data.details.get(code)
            eta = ([detail.eta.day, detail.eta.time1, detail.eta.time2]
                   if detail and detail.eta.day else None)
            # Missing ETA is a data gap, not a rescheduling notification.
            current[code] = {"status": status.value, "last_seen": now.timestamp(),
                             "eta": eta or (previous.get("eta") if previous else None)}
            if first_fetch:
                continue  # Existing inbox/history is the baseline, not new mail.
            if previous is None:
                if code in data.active_codes:
                    self._fire(EVENT_NEW_PACKAGE, code, data)
                continue
            old = previous.get("status", "unknown")
            if (code in data.active_codes and eta and previous.get("eta")
                    and eta != previous["eta"]):
                self._fire(EVENT_ETA_CHANGED, code, data, old_eta=previous["eta"], new_eta=eta)
            if status == old:
                continue
            self._fire(EVENT_STATUS_CHANGED, code, data, old_status=old, new_status=status.value)
            if status == ParcelStatus.DELIVERED:
                self._fire(EVENT_DELIVERED, code, data)
            elif status == ParcelStatus.OUT_FOR_DELIVERY:
                self._fire(EVENT_OUT_FOR_DELIVERY, code, data)
            elif status == ParcelStatus.AT_PICKUP_POINT:
                self._fire(EVENT_AT_PICKUP_POINT, code, data)
            elif status == ParcelStatus.RETURNED:
                self._fire(EVENT_RETURNED, code, data)
            elif status == ParcelStatus.PROBLEM:
                self._fire(EVENT_PROBLEM, code, data)
        self._previous = current

    def _fire(self, event: str, code: str, data: BpostData,
              **extra: Any) -> None:
        detail = data.details.get(code)
        summary = data.summaries.get(code)
        self.hass.bus.async_fire(event, {
            "item_code": code,
            "parcel_id": sha256(code.encode()).hexdigest(),
            "entry_id": self.config_entry.entry_id,
            "status": parcel_status(code, data).value,
            "raw_status": detail_status(detail) if detail else None,
            "list_status": summary.status if summary else None,
            "direction": ({"SENDER": "outgoing", "RECEIVER": "incoming"}.get(detail.user_type, "unknown")
                          if detail else "unknown"),
            "sender": detail.sender.name if detail else None,
            **extra,
        })

    async def async_shutdown(self) -> None:
        if self._unsub_mail:
            self._unsub_mail()
            self._unsub_mail = None
        await self.mail.async_shutdown()
        if self._unsub_live:
            self._unsub_live()
            self._unsub_live = None
        if self._unsub_targets:
            self._unsub_targets()
            self._unsub_targets = None
        await self.live.async_shutdown()
        await super().async_shutdown()
        try:
            await self.client.close()
        except BpostAuthError:
            pass
