"""Public barcode tracking, isolated from account credentials and cookies."""

from datetime import datetime
import json
import re
from time import monotonic
from zoneinfo import ZoneInfo

import aiohttp

from .client import _retry_after
from .const import PUBLIC_TRACKING_URL
from .exceptions import BpostApiError, BpostRateLimitError
from .models import DeliveryPoint, Eta, ParcelDetail, ParcelEvent, Person
from .status import ParcelStatus, normalize_status

MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class BpostTrackingNotFound(BpostApiError):
    """The public tracker found no parcel for the supplied pair."""


def tracking_inputs(barcode: str, postal_code: str) -> tuple[str, str]:
    """Trim input without changing a carrier identifier or guessing a checksum."""
    if not isinstance(barcode, str) or not isinstance(postal_code, str):
        raise ValueError("Invalid tracking input")
    barcode, postal_code = barcode.strip(), postal_code.strip().upper()
    if not 1 <= len(barcode) <= 128 or any(c.isspace() or not c.isprintable() for c in barcode):
        raise ValueError("Invalid barcode")
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9 -]{0,15}", postal_code):
        raise ValueError("Invalid postal code")
    return barcode, postal_code


def _text(value) -> str | None:
    return value if isinstance(value, str) and value else None


def _object(value) -> dict:
    return value if isinstance(value, dict) else {}


def _localized(value, lang: str) -> str | None:
    value = _object(value)
    translated = value.get(lang.upper()) or value.get("EN")
    if isinstance(translated, dict):
        translated = translated.get("description")
    return _text(translated)


def _instant(value) -> datetime | None:
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value / 1000, ZoneInfo("Europe/Brussels"))
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is not None:
                return parsed.astimezone(ZoneInfo("Europe/Brussels"))
    except (ValueError, OverflowError, OSError):
        pass
    return None


def _day(value) -> str | None:
    if isinstance(value, str):
        for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(value, pattern).date().isoformat()
            except ValueError:
                pass
    return None


def parse_tracking(payload, barcode: str, lang: str = "fr") -> ParcelDetail:
    if not isinstance(payload, dict) or "error" in payload:
        raise BpostApiError("Unexpected public tracking response.")
    items = payload.get("items")
    if items == []:
        raise BpostTrackingNotFound("No parcel found for this tracking pair.")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise BpostApiError("Unexpected public tracking items.")
    raw = items[0]
    # A relabelled item may echo the requested code as searchCode instead.
    if barcode not in (raw.get("itemCode"), raw.get("searchCode")):
        raise BpostApiError("Public tracking identity mismatch.")
    step = _object(raw.get("activeStep"))
    code = _text(step.get("knownProcessStep")) or _text(step.get("name"))
    actual = _object(_object(raw.get("actualDeliveryInformation")).get("actualDeliveryTime"))
    delivered_day = _day(actual.get("day"))
    status = normalize_status(code)
    if delivered_day and status != ParcelStatus.RETURNED:
        status = ParcelStatus.DELIVERED
    detail = ParcelDetail(barcode, current_status=code, parcel_main_status=status.value,
                          delivered_day=delivered_day, delivered_time=_text(actual.get("time")))
    # Explicit delivery evidence outranks an older process step. Keep raw_status
    # separately without persisting the API response or private receiver fields.
    detail.canonical_status = status.value
    detail.sender = Person(name=_text(raw.get("senderCommercialName")) or _text(_object(raw.get("sender")).get("name")))
    detail.parcel_type = _text(raw.get("shipmentType"))
    detail.product_type = _text(raw.get("productCategory"))
    detail.delivery_point = DeliveryPoint.from_dict(raw.get("deliveryPoint"))
    events = raw.get("events", [])
    if not isinstance(events, list) or any(not isinstance(e, dict) for e in events):
        raise BpostApiError("Unexpected public tracking events.")
    detail.events = [ParcelEvent(date=_day(e.get("date")), time=_text(e.get("time")),
        description=_localized(e.get("key"), lang),
        location=_text(_object(e.get("location")).get("locationName"))) for e in events[:100]]
    eta = _object(raw.get("expectedDeliveryTimeRange"))
    start, end = _instant(eta.get("time1")), _instant(eta.get("time2"))
    if start and end and start.date() == end.date() and end > start:
        detail.eta = Eta(start.date().isoformat(), start.strftime("%H:%M"), end.strftime("%H:%M"))
    return detail


class PublicTrackingClient:
    """One bounded public lookup; never uses login, account headers or cookies."""

    def __init__(self, *, trust_env: bool = False, app_lang: str = "fr") -> None:
        self._trust_env = trust_env
        self._lang = app_lang
        self._session: aiohttp.ClientSession | None = None
        self._retry_at = 0.0

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def get_parcel(self, barcode: str, postal_code: str) -> ParcelDetail:
        barcode, postal_code = tracking_inputs(barcode, postal_code)
        remaining = self._retry_at - monotonic()
        if remaining > 0:
            raise BpostRateLimitError(remaining)
        if self._session is None:
            self._session = aiohttp.ClientSession(trust_env=self._trust_env,
                cookie_jar=aiohttp.DummyCookieJar(), timeout=aiohttp.ClientTimeout(total=20))
        try:
            async with self._session.get(PUBLIC_TRACKING_URL,
                params={"itemIdentifier": barcode, "postalCode": postal_code}, allow_redirects=False) as response:
                if response.status == 429:
                    delay = _retry_after(response.headers.get("Retry-After"))
                    self._retry_at = monotonic() + delay
                    raise BpostRateLimitError(delay)
                if response.status != 200:
                    raise BpostApiError("Public tracking service unavailable.")
                content = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    content.extend(chunk)
                    if len(content) > MAX_RESPONSE_BYTES:
                        raise BpostApiError("Public tracking response exceeds size limit.")
                payload = json.loads(content)
        except (aiohttp.ClientError, TimeoutError, ValueError):
            raise BpostApiError("Unable to read public tracking response.") from None
        return parse_tracking(payload, barcode, self._lang)
