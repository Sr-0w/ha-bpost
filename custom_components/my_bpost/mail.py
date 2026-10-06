"""Independent Mail Ahead polling and persistent, private announcement baseline."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_LETTER_ANNOUNCED
from .entity import unique_id
from .pybpost.exceptions import BpostAuthError, BpostError, BpostRateLimitError
from .pybpost.mail import MailCapability, MailItem, mail_capability

if TYPE_CHECKING:
    from .coordinator import BpostDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)
MAIL_WINDOW_DAYS = 30


@dataclass
class MailData:
    capability: MailCapability = MailCapability.UNKNOWN
    letters: dict[str, MailItem] = field(default_factory=dict, repr=False)
    last_fetch: datetime | None = None


class BpostMailCoordinator(DataUpdateCoordinator[MailData]):
    def __init__(self, parent: "BpostDataUpdateCoordinator") -> None:
        super().__init__(parent.hass, _LOGGER, name="My bpost Mail Ahead",
                         config_entry=parent.config_entry, update_interval=timedelta(minutes=30))
        self.parent = parent
        self.data = MailData()
        self._seen: dict[str, float] | None = None
        self._store = Store(self.hass, 1, f"{DOMAIN}.{self.config_entry.entry_id}.mail")

    async def _async_setup(self) -> None:
        stored = await self._store.async_load()
        if isinstance(stored, dict) and isinstance(stored.get("seen"), dict):
            self._seen = {key: ts for key, ts in stored["seen"].items()
                          if isinstance(key, str) and isinstance(ts, (int, float))}

    @property
    def mailbox_available(self) -> bool:
        return self.last_update_success and self.data.capability == MailCapability.AVAILABLE

    async def _async_update_data(self) -> MailData:
        self.update_interval = timedelta(minutes=30)
        now = dt_util.utcnow()
        if (self.config_entry.data.get("source") == "public"
                or not self.config_entry.options.get("enable_mail", True)):
            self.update_interval = None
            self._purge_images(set())
            return MailData(MailCapability.DISABLED, last_fetch=now)
        try:
            summary = await self.parent.client.get_mail_summary()
            capability = mail_capability(summary)
            if capability != MailCapability.AVAILABLE:
                self.update_interval = timedelta(hours=12)
                self._purge_images(set())
                return MailData(capability, last_fetch=now)
            today = now.astimezone(ZoneInfo("Europe/Brussels")).date()
            first_day = today - timedelta(days=MAIL_WINDOW_DAYS - 1)
            letters = {item.key: item for item in await self.parent.client.get_letters(first_day, today)
                       if first_day <= item.day <= today}
        except BpostAuthError as err:
            raise ConfigEntryAuthFailed("My bpost Mail Ahead session expired.") from err
        except BpostRateLimitError as err:
            self.update_interval = timedelta(seconds=max(1800, err.retry_after))
            raise UpdateFailed("My bpost requested a Mail Ahead polling pause.") from err
        except BpostError as err:
            raise UpdateFailed("Unable to update My bpost Mail Ahead.") from err

        previous = self._seen
        seen = {key: ts for key, ts in (previous or {}).items() if now.timestamp() - ts < 60 * 86400}
        seen.update({key: now.timestamp() for key in letters})
        # Persist before announcing, and never persist names, signed links or scans.
        await self._store.async_save({"seen": seen})
        self._seen = seen
        if previous is not None:
            for key in letters.keys() - previous.keys():
                item = letters[key]
                self.hass.bus.async_fire(EVENT_LETTER_ANNOUNCED, {
                    "entry_id": self.config_entry.entry_id, "mail_id": key,
                    "date": item.day.isoformat(),
                    "planned_delivery": item.planned_delivery.isoformat() if item.planned_delivery else None,
                })
        image_keys = {key for key, item in letters.items() if item.image_url}
        self._purge_images(image_keys if self.config_entry.options.get("enable_mail_images", False) else set())
        return MailData(capability, letters, now)

    def _purge_images(self, keys: set[str]) -> None:
        registry = er.async_get(self.hass)
        prefix = unique_id(self.config_entry, "mail_image_")
        for entity in er.async_entries_for_config_entry(registry, self.config_entry.entry_id):
            if (entity.domain == "image" and entity.platform == DOMAIN
                    and entity.unique_id.startswith(prefix)
                    and entity.unique_id.removeprefix(prefix) not in keys):
                registry.async_remove(entity.entity_id)
