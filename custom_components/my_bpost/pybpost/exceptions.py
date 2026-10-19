"""Exception hierarchy for pybpost."""


class BpostError(Exception):
    """Base class for all pybpost errors."""


class BpostAuthError(BpostError):
    """Login failed (bad credentials) or re-authentication impossible."""


class BpostApiError(BpostError):
    """The backend returned an error envelope or unexpected payload."""


class BpostMaintenanceError(BpostApiError):
    """Backend signals maintenance (APP_IN_MAINTENANCE / HTTP 503)."""


class BpostForceUpdateError(BpostApiError):
    """Backend rejects our app version (APPVERSION_NOT_SUPPORTED)."""


class BpostRateLimitError(BpostApiError):
    """The server requests a pause before another request."""

    def __init__(self, retry_after: float = 300) -> None:
        super().__init__("My bpost request limit reached.")
        self.retry_after = retry_after
