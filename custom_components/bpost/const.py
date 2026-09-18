"""Constants for the bpost integration."""

DOMAIN = "bpost"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_APP_LANG = "app_lang"

DEFAULT_SCAN_MINUTES = 10
DEFAULT_RETENTION_DAYS = 7

EVENT_NEW_PACKAGE = "bpost_new_package"
EVENT_STATUS_CHANGED = "bpost_status_changed"
EVENT_DELIVERED = "bpost_delivered"
EVENT_OUT_FOR_DELIVERY = "bpost_out_for_delivery"
