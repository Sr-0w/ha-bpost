"""Constants for the My bpost integration."""

DOMAIN = "my_bpost"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_APP_LANG = "app_lang"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"

DEFAULT_SCAN_MINUTES = 10
DEFAULT_RETENTION_DAYS = 7

EVENT_NEW_PACKAGE = "my_bpost_new_package"
EVENT_STATUS_CHANGED = "my_bpost_status_changed"
EVENT_DELIVERED = "my_bpost_delivered"
EVENT_OUT_FOR_DELIVERY = "my_bpost_out_for_delivery"
EVENT_AT_PICKUP_POINT = "my_bpost_at_pickup_point"
EVENT_RETURNED = "my_bpost_returned"
EVENT_PROBLEM = "my_bpost_problem"
EVENT_ETA_CHANGED = "my_bpost_eta_changed"
EVENT_LETTER_ANNOUNCED = "my_bpost_letter_announced"
