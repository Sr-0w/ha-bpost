"""Stable, conservative parcel states independent of API spelling/language."""

from enum import StrEnum
import re


class ParcelStatus(StrEnum):
    UNKNOWN = "unknown"
    REGISTERED = "registered"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    AT_PICKUP_POINT = "at_pickup_point"
    DELIVERED = "delivered"
    RETURNING = "returning"
    RETURNED = "returned"
    PROBLEM = "problem"


_ALIASES = {
    ParcelStatus.REGISTERED: ("AnnouncementReceived", "IN_PREPARATION", "PREPARATION", "REGISTERED"),
    ParcelStatus.IN_TRANSIT: ("IN_TRANSIT", "IN_TRANSPORT", "ON_THE_WAY"),
    ParcelStatus.OUT_FOR_DELIVERY: ("OUT_FOR_DELIVERY", "OutForDelivery", "AROUND"),
    ParcelStatus.AT_PICKUP_POINT: ("AT_PICKUP_POINT", "READY_FOR_PICKUP", "AVAILABLE_FOR_PICKUP"),
    ParcelStatus.DELIVERED: ("DELIVERED", "DistributedNormally", "DistributedAfterBTS",
                             "DistributedAbroad", "PICKED_UP_IN_POST_POINT", "PICKED_UP_IN_POST_OFFICE"),
    ParcelStatus.RETURNING: ("RETURNING", "ON_THE_WAY_TO_SENDER"),
    ParcelStatus.RETURNED: ("RETURNED", "DELIVERED_TO_SENDER", "RETURNED_TO_SENDER"),
    ParcelStatus.PROBLEM: ("PROBLEM", "DELIVERY_FAILED", "FAILED"),
}


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


_LOOKUP = {_key(alias): status for status, aliases in _ALIASES.items() for alias in aliases}

# Explicit public tracker variants. Unknown suffixes remain unknown; don't infer
# final delivery from a broad substring such as "available" or "delivered".
for _status, _codes in (
    (ParcelStatus.REGISTERED, ("STATUS_PENDING", "PENDING_APPROVAL", "IN_PREPARATION_AWAITING_DROPOFF", "IN_PREPARATION_AWAITING_PICKUP")),
    (ParcelStatus.IN_TRANSIT, ("PROCESSING", "PROCESSING_HOME", "PROCESSING_INTERNATIONAL", "CUSTOMS", "CUSTOMS_PAYMENT_SUCCESSFUL", "CUSTOMS_PAYMENT_NOT_REQUIRED")),
    (ParcelStatus.OUT_FOR_DELIVERY, ("ON_THE_WAY_TO_YOU", "OUT_FOR_DELIVERY_HOME", "out_for_delivery_onFoot", "out_for_delivery_byBike", "out_for_delivery_byCar", "out_for_delivery_byEbike", "out_for_delivery_byECar")),
    (ParcelStatus.AT_PICKUP_POINT, ("AVAILABLE", "AVAILABLE_IN_POST_POINT", "AVAILABLE_IN_POST_OFFICE", "AVAILABLE_IN_PARCEL_LOCKER", "AVAILABLE_POST_POINT", "AVAILABLE_POST_OFFICE", "AVAILABLE_PARCEL_LOCKER", "REDELIVERY_CAN_PICKUP_POST_POINT")),
    (ParcelStatus.DELIVERED, ("delivered_kariboo_point",)),
):
    _LOOKUP.update({_key(code): _status for code in _codes})


def normalize_status(*values: str | None) -> ParcelStatus:
    """Use the most specific recognized code; never guess from activity/text."""
    for value in values:
        if isinstance(value, str) and (status := _LOOKUP.get(_key(value))) is not None:
            return status
    return ParcelStatus.UNKNOWN
