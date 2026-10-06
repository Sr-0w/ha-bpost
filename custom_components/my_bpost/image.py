"""Opt-in Mail Ahead scans, fetched on demand through Home Assistant's image proxy."""

import asyncio
from time import monotonic

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import unique_id
from .mail import BpostMailCoordinator
from .pybpost.exceptions import BpostError, BpostRateLimitError
from .pybpost.mail import MailItem


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                           async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data.mail
    known: set[str] = set()

    @callback
    def sync_images() -> None:
        if not coordinator.last_update_success:
            return
        keys = {key for key, item in coordinator.data.letters.items() if item.image_url}
        if not entry.options.get("enable_mail_images", False):
            keys = set()
        fresh = keys - known
        known.intersection_update(keys)
        known.update(fresh)
        if fresh:
            async_add_entities([BpostMailImage(hass, coordinator, entry, key) for key in sorted(fresh)])

    sync_images()
    entry.async_on_unload(coordinator.async_add_listener(sync_images))


class BpostMailImage(CoordinatorEntity[BpostMailCoordinator], ImageEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "mail_image"
    _attr_image_url = None

    def __init__(self, hass: HomeAssistant, coordinator: BpostMailCoordinator,
                 entry: ConfigEntry, key: str) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass, verify_ssl=True)
        self._key = key
        self._entry = entry
        self._attr_unique_id = unique_id(entry, f"mail_image_{key}")
        item = self._item
        self._attr_translation_placeholders = {"date": item.day.isoformat() if item else ""}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="My bpost",
            manufacturer="bpost", model="My bpost account")
        self._attr_image_last_updated = dt_util.utcnow()
        self._fingerprint = self._current_fingerprint()
        self._bytes: bytes | None = None
        self._expires_at = self._retry_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def _item(self) -> MailItem | None:
        return self.coordinator.data.letters.get(self._key)

    def _current_fingerprint(self) -> tuple[str | None, str | None]:
        item = self._item
        return (item.image_ref, item.image_url) if item else (None, None)

    @property
    def available(self) -> bool:
        return (self.coordinator.mailbox_available and self._entry.options.get("enable_mail_images", False)
                and self._item is not None and bool(self._item.image_url))

    @property
    def extra_state_attributes(self) -> dict:
        item = self._item
        return {"integration": DOMAIN, "account_id": self._entry.entry_id,
                "mail_id": self._key, "date": item.day.isoformat() if item else None}

    @callback
    def _handle_coordinator_update(self) -> None:
        fingerprint = self._current_fingerprint()
        if fingerprint != self._fingerprint or not self.available:
            self._bytes = None
            self._expires_at = self._retry_at = 0.0
        if fingerprint != self._fingerprint:
            self._fingerprint = fingerprint
            self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        async with self._lock:
            if not self.available:
                self._bytes = None
                return None
            fingerprint = self._current_fingerprint()
            now = monotonic()
            if self._bytes is not None and now < self._expires_at and fingerprint == self._fingerprint:
                return self._bytes
            if now < self._retry_at:
                return None
            try:
                content, content_type = await self.coordinator.parent.client.get_mail_image(self._item.image_url)
            except BpostRateLimitError as err:
                self._retry_at = monotonic() + max(60, err.retry_after)
                self._bytes = None
                return None
            except BpostError:
                self._retry_at = monotonic() + 60
                self._bytes = None
                return None
            # A refresh/disable/removal may have happened during the request.
            if not self.available or fingerprint != self._current_fingerprint():
                return None
            self._fingerprint = fingerprint
            self._attr_content_type = content_type
            self._bytes = content
            self._expires_at = monotonic() + 900
            return content

    async def async_will_remove_from_hass(self) -> None:
        self._bytes = None
        await super().async_will_remove_from_hass()
