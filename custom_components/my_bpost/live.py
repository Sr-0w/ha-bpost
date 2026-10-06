"""Independent, bounded live polling: missing GPS never breaks parcel tracking."""

from dataclasses import dataclass
from collections import deque
from datetime import datetime, timedelta
import logging
from time import monotonic
from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .pybpost.exceptions import BpostAuthError, BpostError, BpostRateLimitError
from .pybpost.models import LiveRoundStatus

if TYPE_CHECKING:
    from .coordinator import BpostDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)
MIN_INTERVAL = 60
MAX_REQUESTS_PER_TICK = 2


@dataclass
class LiveObservation:
    status: LiveRoundStatus
    observed_at: datetime
    expires_at: float


class BpostLiveCoordinator(DataUpdateCoordinator[dict[str, LiveObservation]]):
    def __init__(self, parent: "BpostDataUpdateCoordinator") -> None:
        super().__init__(parent.hass, _LOGGER, name="My bpost live",
                         config_entry=parent.config_entry, update_interval=None)
        self.parent = parent
        self.data = {}
        self._next: dict[str, float] = {}
        self._failures: dict[str, int] = {}
        self._account_retry_at = 0.0
        self._requests: deque[float] = deque()

    def current(self, code: str) -> LiveObservation | None:
        observation = self.data.get(code)
        if (observation is not None and self.last_update_success
                and self.parent.last_update_success and code in self.parent.live_targets()
                and monotonic() < observation.expires_at):
            return observation
        return None

    async def _async_update_data(self) -> dict[str, LiveObservation]:
        targets = self.parent.live_targets() if self.parent.last_update_success else {}
        self.update_interval = timedelta(seconds=MIN_INTERVAL) if targets else None
        now = monotonic()
        result = {code: value for code, value in self.data.items()
                  if code in targets and now < value.expires_at}
        self._next = {code: due for code, due in self._next.items() if code in targets}
        self._failures = {code: count for code, count in self._failures.items() if code in targets}
        if now < self._account_retry_at:
            return result
        while self._requests and self._requests[0] <= now - MIN_INTERVAL:
            self._requests.popleft()
        # Oldest deadline first ensures fairness when more parcels are eligible.
        due = sorted((code for code in targets if self._next.get(code, 0) <= now),
                     key=lambda code: self._next.get(code, 0))
        budget = MAX_REQUESTS_PER_TICK - len(self._requests)
        for code in due[:max(0, budget)]:
            self._requests.append(monotonic())
            try:
                status = await self.parent.client.get_live_status(code, targets[code])
            except BpostAuthError as err:
                self.data = {}
                raise ConfigEntryAuthFailed("My bpost live session expired.") from err
            except BpostRateLimitError as err:
                self._account_retry_at = now + err.retry_after
                return {}  # No courier location is presented as current during backoff.
            except BpostError:
                status = None
            if status is None:
                result.pop(code, None)
                failures = self._failures.get(code, 0) + 1
                self._failures[code] = min(failures, 4)
                self._next[code] = now + min(300 * 2 ** (min(failures, 4) - 1), 1800)
                continue
            observed = monotonic()
            interval = max(MIN_INTERVAL, status.auto_refresh_s)
            self._next[code] = observed + interval
            self._failures.pop(code, None)
            result[code] = LiveObservation(status, dt_util.utcnow(),
                                           observed + min(600, max(120, interval * 2)))
        return result
