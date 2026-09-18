"""Device tracker platform for the My bpost integration.

One tracker per parcel that has coordinates (pickup/delivery point today,
live courier position once the live-tracking poll is wired). The native map
card can plot these trackers.
"""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
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
        fresh = [
            BpostParcelTracker(coordinator, entry, code)
            for code, detail in data.details.items()
            if code not in known
            and detail.delivery_point is not None
            and detail.delivery_point.has_coords
        ]
        if not fresh:
            return
        known.update(t.item_code for t in fresh)
        async_add_entities(fresh)

    _async_add_new()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new))


class BpostParcelTracker(
    CoordinatorEntity[BpostDataUpdateCoordinator], RestoreEntity
):
    """Parcel location tracker (pickup point, later live courier GPS)."""

    _attr_icon = "mdi:package-variant-closed"

    def __init__(self, coordinator: BpostDataUpdateCoordinator,
                 entry: ConfigEntry, item_code: str) -> None:
        super().__init__(coordinator)
        self.item_code = item_code
        self._attr_unique_id = f"{item_code}_tracker"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="My bpost",
            manufacturer="bpost",
            model="My bpost account",
        )

    @property
    def _detail(self) -> ParcelDetail | None:
        data = self.coordinator.data or BpostData()
        return data.details.get(self.item_code)

    @property
    def name(self) -> str:
        detail = self._detail
        label = None
        if detail:
            if detail.user_type == "SENDER":
                label = detail.receiver.name or detail.title
            else:
                label = detail.sender.name or detail.title
        suffix = self.item_code[-6:] if len(self.item_code) > 6 else self.item_code
        return f"Parcel {label or suffix} location"

    @property
    def latitude(self) -> float | None:
        detail = self._detail
        if detail and detail.delivery_point:
            return detail.delivery_point.latitude
        return None

    @property
    def longitude(self) -> float | None:
        detail = self._detail
        if detail and detail.delivery_point:
            return detail.delivery_point.longitude
        return None

    @property
    def location_name(self) -> str | None:
        detail = self._detail
        if detail and detail.delivery_point:
            return detail.delivery_point.name or detail.delivery_point.city
        return None

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def extra_state_attributes(self) -> dict:
        detail = self._detail
        data = self.coordinator.data or BpostData()
        attrs: dict = {
            "tracking_number": self.item_code,
            "active": is_parcel_active(self.item_code, data),
        }
        if not detail:
            return attrs
        point = detail.delivery_point
        attrs["status"] = detail_status(detail)
        if point is not None:
            attrs.update({
                "pickup_name": point.name,
                "pickup_address": point.address,
                "pickup_city": point.city,
                "pickup_type": point.kind,
            })
        return attrs
