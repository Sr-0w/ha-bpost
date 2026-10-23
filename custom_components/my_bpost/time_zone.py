"""Europe/Brussels, loaded once off Home Assistant's event loop.

``ZoneInfo`` reads tzdata from disk. Constructing it inside a coordinator
update or while importing a platform blocks the event loop, so setup awaits
Home Assistant's async loader and every later caller reuses that object.
"""

from zoneinfo import ZoneInfo

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

BPOST_TIME_ZONE = "Europe/Brussels"

_zone: ZoneInfo | None = None


async def async_get_bpost_time_zone() -> ZoneInfo:
    """Return the Brussels zone, reading tzdata at most once."""
    global _zone
    if _zone is None:
        loaded = await dt_util.async_get_time_zone(BPOST_TIME_ZONE)
        if loaded is None:
            raise HomeAssistantError(f"Time zone {BPOST_TIME_ZONE} is not available")
        _zone = loaded
    return _zone
