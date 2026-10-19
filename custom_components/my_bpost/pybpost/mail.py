"""Mail Ahead protocol models; image links and personal fields stay private."""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from hashlib import sha256
from typing import Any

from .exceptions import BpostApiError


class MailCapability(StrEnum):
    AVAILABLE = "available"
    NOT_SUBSCRIBED = "not_subscribed"
    NOT_ELIGIBLE = "not_eligible"
    UNKNOWN = "unknown"
    DISABLED = "disabled"


def mail_capability(summary: dict[str, Any]) -> MailCapability:
    if summary.get("isMMTSubscribed") is True:
        return MailCapability.AVAILABLE
    if summary.get("isMMTEligible") is False:
        return MailCapability.NOT_ELIGIBLE
    if summary.get("isMMTSubscribed") is False:
        return MailCapability.NOT_SUBSCRIBED
    return MailCapability.UNKNOWN


@dataclass(frozen=True)
class MailItem:
    item_id: str = field(repr=False)
    day: date
    planned_delivery: date | None = None
    sender: str | None = field(default=None, repr=False)
    image_url: str | None = field(default=None, repr=False)
    image_ref: str | None = field(default=None, repr=False)

    @property
    def key(self) -> str:
        """Stable opaque identity; raw bpost identifiers need not leave memory."""
        return sha256(self.item_id.encode()).hexdigest()


def parse_mail_items(images: Any) -> list[MailItem]:
    """Parse the date-keyed map atomically: malformed data is not an empty inbox."""
    if not isinstance(images, dict):
        raise BpostApiError("Unexpected Mail Ahead image list.")
    items: dict[str, MailItem] = {}
    for day, records in images.items():
        try:
            group_date = date.fromisoformat(day)
        except (TypeError, ValueError):
            raise BpostApiError("Invalid Mail Ahead group date.") from None
        if not isinstance(records, list):
            raise BpostApiError("Unexpected Mail Ahead letter group.")
        for raw in records:
            if not isinstance(raw, dict) or not isinstance(raw.get("itemId"), str) or not raw["itemId"]:
                raise BpostApiError("Invalid Mail Ahead letter identity.")
            planned = raw.get("plannedDistributionDate")
            try:
                planned = date.fromisoformat(planned) if planned else None
            except (TypeError, ValueError):
                planned = None
            sender = raw.get("sender")
            name = sender.get("name") if isinstance(sender, dict) else None
            item = MailItem(
                item_id=raw["itemId"], day=group_date, planned_delivery=planned,
                sender=name if isinstance(name, str) else None,
                image_url=raw.get("imageUrl") if isinstance(raw.get("imageUrl"), str) else None,
                image_ref=raw.get("imageRefId") if isinstance(raw.get("imageRefId"), str) else None,
            )
            if item.key not in items or item.day >= items[item.key].day:
                items[item.key] = item
    return sorted(items.values(), key=lambda item: (item.day, item.key), reverse=True)
