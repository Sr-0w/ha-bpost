"""Data coordinator for the My bpost integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    EVENT_DELIVERED,
    EVENT_NEW_PACKAGE,
    EVENT_OUT_FOR_DELIVERY,
    EVENT_STATUS_CHANGED,
)
from .pybpost.client import BpostClient
from .pybpost.exceptions import BpostAuthError
from .pybpost.models import ParcelDetail, ParcelSummary

_LOGGER = logging.getLogger(__name__)

OUT_FOR_DELIVERY_MARKERS = ("OUT_FOR_DELIVERY", "OutForDelivery", "AROUND")


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
    detail = data.details.get(code)
    status = ""
    if detail:
        status = f"{detail_status(detail)}"
    summary = data.summaries.get(code)
    if summary and summary.status:
        status += f" {summary.status}"
    upper = status.upper()
    return any(marker in upper for marker in OUT_FOR_DELIVERY_MARKERS)


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
            name=f"{DOMAIN} ({entry.unique_id})",
            update_interval=timedelta(minutes=scan_minutes),
            config_entry=entry,
        )
        self.client = client
        self._previous: dict[str, tuple[str | None, str | None]] = {}

    async def _async_update_data(self) -> BpostData:
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
        self._detect_changes(data)
        return data

    def _detect_changes(self, data: BpostData) -> None:
        current = {
            code: (
                (data.details[code].current_status
                 if code in data.details else None),
                (data.summaries[code].status
                 if code in data.summaries else None),
            )
            for code in data.summaries
        }
        for code, (detail_status_value, summary_status) in current.items():
            previous = self._previous.get(code)
            if previous is None:
                self._fire(EVENT_NEW_PACKAGE, code, data)
                continue
            if (detail_status_value, summary_status) == previous:
                continue
            self._fire(EVENT_STATUS_CHANGED, code, data, previous=previous)
            if not is_parcel_active(code, data):
                self._fire(EVENT_DELIVERED, code, data)
            elif _is_out_for_delivery(code, data):
                self._fire(EVENT_OUT_FOR_DELIVERY, code, data)
        self._previous = current

    def _fire(self, event: str, code: str, data: BpostData,
              **extra: Any) -> None:
        detail = data.details.get(code)
        summary = data.summaries.get(code)
        self.hass.bus.async_fire(event, {
            "item_code": code,
            "status": detail_status(detail) if detail else None,
            "list_status": summary.status if summary else None,
            "sender": detail.sender.name if detail else None,
            **extra,
        })

    async def async_shutdown(self) -> None:
        try:
            await self.client.close()
        except BpostAuthError:
            pass
