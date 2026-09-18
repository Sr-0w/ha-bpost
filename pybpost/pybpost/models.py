"""Typed models for the My bpost API (tolerant to missing keys)."""

from __future__ import annotations

from dataclasses import dataclass, field


def _str(value: object) -> str | None:
    return str(value) if value is not None else None


@dataclass
class ParcelSummary:
    """Lightweight entry from ``parcel/getparcelslist``."""

    item_code: str
    status: str | None = None
    latest_event_ts: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "ParcelSummary":
        return cls(
            item_code=str(data.get("itemCode", "")),
            status=_str(data.get("Status")),
            latest_event_ts=_str(data.get("LatestEventTimestamp")),
        )


@dataclass
class Person:
    name: str | None = None
    street: str | None = None
    number: str | None = None
    box: str | None = None
    postcode: str | None = None
    city: str | None = None
    country: str | None = None
    email: str | None = None
    phone: str | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> "Person":
        data = data or {}
        return cls(
            name=_str(data.get("name")),
            street=_str(data.get("street")),
            number=_str(data.get("number")),
            box=_str(data.get("box")),
            postcode=_str(data.get("postcode")),
            city=_str(data.get("city")),
            country=_str(data.get("country")),
            email=_str(data.get("email")),
            phone=_str(data.get("phone")),
        )


@dataclass
class ParcelEvent:
    date: str | None = None
    time: str | None = None
    description: str | None = None
    key: str | None = None
    location: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "ParcelEvent":
        return cls(
            date=_str(data.get("date")),
            time=_str(data.get("time")),
            description=_str(data.get("description")),
            key=_str(data.get("key")),
            location=_str(data.get("location")),
        )


@dataclass
class Eta:
    day: str | None = None
    time1: str | None = None
    time2: str | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> "Eta":
        data = data or {}
        return cls(day=_str(data.get("day")), time1=_str(data.get("time1")),
                   time2=_str(data.get("time2")))

    @property
    def is_empty(self) -> bool:
        return not (self.day or self.time1 or self.time2)


@dataclass
class DeliveryPoint:
    """Pickup/delivery point (post office, postal point, locker...)."""

    name: str | None = None
    street: str | None = None
    number: str | None = None
    postcode: str | None = None
    city: str | None = None
    kind: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> "DeliveryPoint | None":
        if not isinstance(data, dict):
            return None

        def _coord(value: object) -> float | None:
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        point = cls(
            name=_str(data.get("name")),
            street=_str(data.get("street")),
            number=_str(data.get("streetNumber")),
            postcode=_str(data.get("postcode")),
            city=_str(data.get("municipality")),
            kind=_str(data.get("type")),
            latitude=_coord(data.get("latitude")),
            longitude=_coord(data.get("longitude")),
        )
        if not any((point.name, point.city, point.latitude, point.longitude)):
            return None
        return point

    @property
    def has_coords(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def address(self) -> str | None:
        parts = [
            " ".join(p for p in (self.street, self.number) if p) or None,
            " ".join(p for p in (self.postcode, self.city) if p) or None,
        ]
        text = ", ".join(p for p in parts if p)
        return text or None


@dataclass
class ParcelDetail:
    """Rich parcel entry from ``parcel/getparcelsv3``."""

    item_code: str
    item_id: str | None = None
    sender_barcode: str | None = None
    current_status: str | None = None
    parcel_main_status: str | None = None
    user_type: str | None = None
    parcel_type: str | None = None
    product_type: str | None = None
    title: str | None = None
    sender: Person = field(default_factory=Person)
    receiver: Person = field(default_factory=Person)
    eta: Eta = field(default_factory=Eta)
    events: list[ParcelEvent] = field(default_factory=list)
    delivery_steps: list[dict] = field(default_factory=list)
    delivery_point: DeliveryPoint | None = None
    delivered_day: str | None = None
    delivered_time: str | None = None
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "ParcelDetail":
        events = [ParcelEvent.from_dict(e) for e in data.get("events") or []
                  if isinstance(e, dict)]
        code = str(data.get("itemCode") or data.get("itemId")
                   or data.get("senderBarcode") or "")
        actual = data.get("actualDeliveryTime") or {}
        return cls(
            item_code=code,
            item_id=_str(data.get("itemId")),
            sender_barcode=_str(data.get("senderBarcode")),
            current_status=_str(data.get("currentStatus")),
            parcel_main_status=_str(data.get("parcelMainStatus")),
            user_type=_str(data.get("userType")),
            parcel_type=_str(data.get("parcelType")),
            product_type=_str(data.get("productType")),
            title=_str(data.get("parcelTitle")),
            sender=Person.from_dict(data.get("sender")),
            receiver=Person.from_dict(data.get("receiver")),
            eta=Eta.from_dict(data.get("eta")),
            events=events,
            delivery_steps=list(data.get("deliverySteps") or []),
            delivery_point=DeliveryPoint.from_dict(data.get("deliveryPoint")),
            delivered_day=_str(actual.get("day")),
            delivered_time=_str(actual.get("time")),
            raw=data,
        )

    @property
    def last_event(self) -> ParcelEvent | None:
        # API order is newest-first.
        return self.events[0] if self.events else None


@dataclass
class LiveRoundStatus:
    """Live courier-round info from ``parcel/getparcelchunks``."""

    stops_until_target: int | None = None
    progress_until_target: float | None = None
    eta_window: str | None = None
    last_known_lat: float | None = None
    last_known_lon: float | None = None
    auto_refresh_s: int = 60

    @classmethod
    def from_chunk(cls, payload: dict) -> "LiveRoundStatus | None":
        data = (payload.get("response") or {}).get("data") or {}
        if not isinstance(data, dict):
            return None
        round_info = data.get("itemOnRoundStatus") or {}
        last = round_info.get("lastKnownLocation") or {}

        def _num(value: object) -> float | None:
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        stops = _num(round_info.get("nrOfStopsUntilTarget"))
        try:
            auto_refresh = int(data.get("autoRefreshTimeInSeconds") or 60)
        except (TypeError, ValueError):
            auto_refresh = 60
        return cls(
            stops_until_target=int(stops) if stops is not None else None,
            progress_until_target=_num(round_info.get("progressUntilTarget")),
            eta_window=_str(round_info.get("estimatedDeliveryTimeWindow")),
            last_known_lat=_num(last.get("latitude")),
            last_known_lon=_num(last.get("longitude")),
            auto_refresh_s=max(auto_refresh, 30),
        )


@dataclass
class AuthTokens:
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    token_type: str | None = None
