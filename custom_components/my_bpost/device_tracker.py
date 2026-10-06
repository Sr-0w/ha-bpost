"""Device tracker platform for the My bpost integration.

Separate pickup and courier trackers; expired courier coordinates are unavailable.
"""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BpostDataUpdateCoordinator = entry.runtime_data
    known: set[tuple[str, bool]] = set()

    @callback
    def _async_add_new() -> None:
        data = coordinator.data or BpostData()
        known.difference_update({key for key in known if key[0] in coordinator.expired_codes})
        fresh = []
        for code, detail in data.details.items():
            for courier in (False, True):
                live = coordinator.live.current(code)
                has_coords = (live is not None and live.status.has_coords) if courier else (
                    detail.delivery_point is not None and detail.delivery_point.has_coords)
                if (code, courier) not in known and has_coords:
                    fresh.append(BpostParcelTracker(coordinator, entry, code, courier=courier))
                    known.add((code, courier))
        if not fresh:
            return
        async_add_entities(fresh)

    _async_add_new()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new))
    entry.async_on_unload(coordinator.live.async_add_listener(_async_add_new))


class BpostParcelTracker(
    CoordinatorEntity[BpostDataUpdateCoordinator], TrackerEntity
):
    """HA-native location with an explicit coordinate source."""

    _attr_icon = "mdi:package-variant-closed"

    def __init__(self, coordinator: BpostDataUpdateCoordinator,
                 entry: ConfigEntry, item_code: str, *, courier: bool = False) -> None:
        super().__init__(coordinator)
        self.item_code = item_code
        self.courier = courier
        self._entry_id = entry.entry_id
        self._attr_unique_id = unique_id(entry, f"{item_code}_{'courier' if courier else 'tracker'}")
        if courier:
            self._attr_icon = "mdi:truck-delivery"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title if entry.data.get("source") == "public" else "My bpost",
            manufacturer="bpost",
            model="Public parcel tracking" if entry.data.get("source") == "public" else "My bpost account",
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
        return f"Parcel {label or suffix} {'courier' if self.courier else 'pickup'} location"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.live.async_add_listener(self._handle_coordinator_update))

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        if self.courier:
            live = self.coordinator.live.current(self.item_code)
            return live is not None and live.status.has_coords
        detail = self._detail
        return detail is not None and detail.delivery_point is not None and detail.delivery_point.has_coords

    @property
    def latitude(self) -> float | None:
        if self.courier:
            live = self.coordinator.live.current(self.item_code)
            return live.status.last_known_lat if live else None
        detail = self._detail
        if detail and detail.delivery_point and detail.delivery_point.has_coords:
            return detail.delivery_point.latitude
        return None

    @property
    def longitude(self) -> float | None:
        if self.courier:
            live = self.coordinator.live.current(self.item_code)
            return live.status.last_known_lon if live else None
        detail = self._detail
        if detail and detail.delivery_point and detail.delivery_point.has_coords:
            return detail.delivery_point.longitude
        return None

    @property
    def location_name(self) -> str | None:
        if self.courier:
            return None
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
            "integration": DOMAIN,
            "account_id": self._entry_id,
            "tracking_number": self.item_code,
            "location_kind": "courier" if self.courier else "pickup",
            "active": is_parcel_active(self.item_code, data),
        }
        if not detail:
            return attrs
        point = detail.delivery_point
        attrs["status"] = parcel_status(self.item_code, data).value
        if self.courier:
            live = self.coordinator.live.current(self.item_code)
            attrs["live_updated_at"] = live.observed_at.isoformat() if live else None
        elif point is not None:
            attrs.update({
                "pickup_name": point.name,
                "pickup_address": point.address,
                "pickup_city": point.city,
                "pickup_type": point.kind,
            })
        return attrs
