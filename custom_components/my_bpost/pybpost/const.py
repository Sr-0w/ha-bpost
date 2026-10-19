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
# This is bpost's generic application key, identical in every install of
# the official app (shipped, obfuscated, inside its native lib — see
# scripts/extract_key.py). It identifies the app, not the user. If bpost
# rotates it, re-extract from the current app release and cut a new release.
X_API_KEY = "iBLz8oTy8K1KAnPZJLltU527bWmLt6XQ6y8RF5hT"

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
