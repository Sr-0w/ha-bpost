"""Translate persisted session data without retaining login credentials."""

from collections.abc import Mapping
from typing import Any

from .const import CONF_ACCESS_TOKEN, CONF_PASSWORD, CONF_REFRESH_TOKEN
from .pybpost.models import AuthTokens


def session_data(data: Mapping[str, Any], tokens: AuthTokens) -> dict[str, Any]:
    result = dict(data)
    result.pop(CONF_PASSWORD, None)
    result.update({
        CONF_ACCESS_TOKEN: tokens.access_token,
        CONF_REFRESH_TOKEN: tokens.refresh_token,
    })
    return result


def stored_tokens(data: Mapping[str, Any]) -> AuthTokens | None:
    access = data.get(CONF_ACCESS_TOKEN)
    refresh = data.get(CONF_REFRESH_TOKEN)
    if not isinstance(access, str) or not access:
        return None
    return AuthTokens(access, refresh if isinstance(refresh, str) else None)
