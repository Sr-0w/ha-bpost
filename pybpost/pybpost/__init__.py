"""pybpost: async client for the My bpost account API."""

from .client import BpostClient
from .const import APP_VERSION, BASE_URL
from .exceptions import (
    BpostApiError,
    BpostAuthError,
    BpostError,
    BpostForceUpdateError,
    BpostMaintenanceError,
    BpostRateLimitError,
)
from .models import (
    AuthTokens,
    DeliveryPoint,
    Eta,
    LiveRoundStatus,
    ParcelDetail,
    ParcelEvent,
    ParcelSummary,
    Person,
)
from .status import ParcelStatus, normalize_status
from .mail import MailCapability, MailItem, mail_capability

__all__ = [
    "APP_VERSION",
    "BASE_URL",
    "AuthTokens",
    "BpostApiError",
    "BpostAuthError",
    "BpostClient",
    "BpostError",
    "BpostForceUpdateError",
    "BpostMaintenanceError",
    "BpostRateLimitError",
    "DeliveryPoint",
    "Eta",
    "LiveRoundStatus",
    "ParcelDetail",
    "ParcelEvent",
    "ParcelSummary",
    "Person",
    "ParcelStatus",
    "normalize_status",
    "MailCapability",
    "MailItem",
    "mail_capability",
]

__version__ = "0.8.0b2"
