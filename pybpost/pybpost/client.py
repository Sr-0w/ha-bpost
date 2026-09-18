"""Async client for the My bpost account API."""

from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp

from .const import APP_VERSION, BASE_URL, OS_NAME, OS_VERSION, X_API_KEY
from .exceptions import (
    BpostApiError,
    BpostAuthError,
    BpostForceUpdateError,
    BpostMaintenanceError,
)
from .models import AuthTokens, LiveRoundStatus, ParcelDetail, ParcelSummary

_LOGGER = logging.getLogger(__name__)

_SUCCESS = {"success", "SUCCESS"}


class BpostClient:
    """Minimal async client: login, parcels list/details, live chunks.

    The client keeps ``email``/``password`` (when provided) to re-login
    transparently when tokens expire. ``users/refreshtoken`` is attempted
    first on 401/403, then a full login, then the call is retried once.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession | None = None,
        *,
        app_lang: str = "fr",
        api_key: str = X_API_KEY,
        email: str | None = None,
        password: str | None = None,
        timeout: int = 30,
    ) -> None:
        if not api_key or api_key.startswith("REPLACE_ME"):
            raise BpostAuthError(
                "Missing x-api-key: inject the client key (see scripts/extract_key.py)."
            )
        self._session = session
        self._own_session = session is None
        self._app_lang = app_lang
        self._api_key = api_key
        self._email = email
        self._password = password
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._tokens: AuthTokens | None = None
        self._token_acquired_at: float = 0.0

    @property
    def tokens(self) -> AuthTokens | None:
        return self._tokens

    def _base_headers(self, *, with_static: bool = True) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "os": OS_NAME,
            "osVersion": OS_VERSION,
            "x-api-key": self._api_key,
        }
        if with_static:
            headers["appVersion"] = APP_VERSION
            headers["appLang"] = self._app_lang
        return headers

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._own_session = True
        return self._session

    async def close(self) -> None:
        if self._own_session and self._session is not None:
            await self._session.close()
            self._session = None

    # -- authentication -------------------------------------------------

    async def login(self, email: str | None = None,
                    password: str | None = None) -> AuthTokens:
        email = email or self._email
        password = password or self._password
        if not email or not password:
            raise BpostAuthError("Email and password are required to log in.")
        payload = {
            "appLang": self._app_lang,
            "userName": email,
            "password": password,
            "mandatoryConsent": True,
            "optionalConsent": False,
        }
        data = await self._post_raw("users/login", payload, token=None)
        body = data.get("response") or {}
        if data.get("status") not in _SUCCESS or not body.get("accessToken"):
            raise BpostAuthError(
                body.get("errorMsg") or body.get("errorCode")
                or "Login rejected by My bpost."
            )
        self._email, self._password = email, password
        self._tokens = AuthTokens(
            access_token=body["accessToken"],
            refresh_token=body.get("refreshToken"),
            expires_in=body.get("expiresIn"),
            token_type=body.get("tokenType"),
        )
        self._token_acquired_at = time.monotonic()
        return self._tokens

    async def _try_refresh(self) -> bool:
        """Attempt a token refresh. Returns True when new tokens were stored."""
        refresh = self._tokens.refresh_token if self._tokens else None
        if not refresh:
            return False
        try:
            data = await self._post_raw(
                "users/refreshtoken", {"refreshToken": refresh},
                token=None, with_static=False,
            )
        except BpostError:
            return False
        body = data.get("response") or {}
        access = body.get("access_token") or body.get("accessToken")
        new_refresh = body.get("refresh_token") or body.get("refreshToken")
        if data.get("status") not in _SUCCESS or not access:
            return False
        self._tokens = AuthTokens(
            access_token=access,
            refresh_token=new_refresh or refresh,
            expires_in=body.get("expiresIn"),
            token_type=body.get("tokenType"),
        )
        self._token_acquired_at = time.monotonic()
        return True

    async def _reauth(self) -> None:
        if await self._try_refresh():
            return
        if self._email and self._password:
            await self.login()
            return
        raise BpostAuthError("Session expired and no credentials to renew it.")

    # -- low level ------------------------------------------------------

    async def _post_raw(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        token: str | None,
        with_static: bool = True,
    ) -> dict[str, Any]:
        session = await self._ensure_session()
        headers = self._base_headers(with_static=with_static)
        if token:
            # NOTE: raw token, no "Bearer" prefix (as the official app does).
            headers["Authorization"] = token
        async with session.post(
            BASE_URL + path, json=payload, headers=headers,
            timeout=self._timeout,
        ) as resp:
            try:
                data = await resp.json()
            except aiohttp.ContentTypeError:
                text = (await resp.text())[:200]
                raise BpostApiError(f"{path}: HTTP {resp.status}: {text}")
            if resp.status == 503 or data.get("code") == "APP_IN_MAINTENANCE":
                raise BpostMaintenanceError("My bpost backend in maintenance.")
            if data.get("code") == "APPVERSION_NOT_SUPPORTED" and resp.status in (401, 403):
                # Raised without auth context; with a token this code means
                # "invalid/missing user token" (backend quirk).
                if token is None:
                    raise BpostForceUpdateError(
                        "Backend rejected the client (app version or key).")
                raise BpostAuthError("Invalid or expired access token.")
            if resp.status in (401, 403):
                raise BpostAuthError(
                    f"Unauthorized ({data.get('code') or resp.status}).")
            if resp.status >= 400:
                raise BpostApiError(f"{path}: HTTP {resp.status}: {data}")
            if not isinstance(data, dict):
                raise BpostApiError(f"{path}: unexpected payload.")
            return data

    async def _post_authed(self, path: str,
                           payload: dict[str, Any]) -> dict[str, Any]:
        if not self._tokens:
            await self.login()
        assert self._tokens is not None
        try:
            return await self._post_raw(
                path, payload, token=self._tokens.access_token)
        except BpostAuthError:
            _LOGGER.debug("Token rejected, re-authenticating for %s", path)
            await self._reauth()
            assert self._tokens is not None
            return await self._post_raw(
                path, payload, token=self._tokens.access_token)

    # -- parcels --------------------------------------------------------

    async def get_parcels_list(self) -> list[ParcelSummary]:
        data = await self._post_authed(
            "parcel/getparcelslist", {"appLang": self._app_lang})
        items = (data.get("response") or {}).get("items") or []
        return [ParcelSummary.from_dict(i) for i in items
                if isinstance(i, dict) and i.get("itemCode")]

    async def get_parcels_details(
        self, items: list[ParcelSummary],
        *, is_first_page_call: bool = True,
    ) -> tuple[list[ParcelDetail], list[ParcelDetail]]:
        """Returns ``(active, history)`` parcel details for the given items."""
        payload = {
            "appLang": self._app_lang,
            "isFirstPageCall": is_first_page_call,
            "items": [
                {"itemCode": i.item_code, "Status": i.status,
                 "LatestEventTimestamp": i.latest_event_ts}
                for i in items
            ],
        }
        data = await self._post_authed("parcel/getparcelsv3", payload)
        response = data.get("response") or {}
        active: list[ParcelDetail] = []
        for section in (response.get("active") or {}).values():
            if isinstance(section, list):
                active.extend(ParcelDetail.from_dict(p) for p in section
                              if isinstance(p, dict))
        history = [ParcelDetail.from_dict(p)
                   for p in response.get("history") or []
                   if isinstance(p, dict)]
        return active, history

    async def get_live_status(self, item_code: str,
                              postal_code: str) -> LiveRoundStatus | None:
        payload = {
            "appLang": self._app_lang,
            "itemCode": item_code,
            "data": {"postalCode": postal_code},
            "type": "LOCATION_INFO",
        }
        try:
            data = await self._post_authed("parcel/getparcelchunks", payload)
        except BpostAuthError:
            raise
        except BpostError:
            return None
        if data.get("status") not in _SUCCESS:
            return None
        return LiveRoundStatus.from_chunk(data)

    async def get_mail_summary(self) -> dict[str, Any]:
        data = await self._post_authed(
            "mails/getmailsummary", {"appLang": self._app_lang})
        response = data.get("response")
        return response if isinstance(response, dict) else {}
