"""Shared constants for the My bpost API client.

Reverse-engineered from the official My bpost Android app
(be.bpost.mybpost 3.45.1). See the project report for provenance.
"""

BASE_URL = "https://mybpost.bpost.cloud/prod_v2/"
PUBLIC_TRACKING_URL = "https://track.bpost.cloud/track/items"

# Sent as the ``appVersion`` header. The backend rejects unknown values
# with ``APPVERSION_NOT_SUPPORTED``: bump on each official app release.
APP_VERSION = "3.45.1"
OS_NAME = "android"
OS_VERSION = "14"

# Client key for the AWS API Gateway usage plan (``x-api-key`` header).
# This is bpost's proprietary client credential, obfuscated inside the
# official app (native lib, see scripts/extract_key.py). It is deliberately
# NOT stored here: inject it at build/deploy time. The client refuses to
# run with the placeholder value.
X_API_KEY = "REPLACE_ME_AT_DEPLOY_TIME"

#: List ``Status`` values considered terminal (parcel journey finished).
#: Best effort from live data + app resources; refine with live traffic.
TERMINAL_LIST_STATUSES = frozenset(
    {
        "DistributedNormally",
        "DistributedAfterBTS",
        "DistributedAbroad",
        "ReturnedToSender",
        "DeliveredToSender",
    }
)

#: Detail ``currentStatus`` values considered terminal.
TERMINAL_DETAIL_STATUSES = frozenset(
    {
        "DELIVERED",
        "DELIVERED_TO_SENDER",
        "PICKED_UP_IN_POST_POINT",
        "PICKED_UP_IN_POST_OFFICE",
        "RETURNED_TO_SENDER",
    }
)
