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
