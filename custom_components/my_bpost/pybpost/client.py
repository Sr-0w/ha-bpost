"""Async client for the My bpost account API."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
import math
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import Any

import aiohttp
from yarl import URL

from .const import APP_VERSION, BASE_URL, OS_NAME, OS_VERSION, X_API_KEY
from .exceptions import (
    BpostApiError,
    BpostAuthError,
    BpostError,
    BpostForceUpdateError,
    BpostMaintenanceError,
    BpostRateLimitError,
)
from .models import AuthTokens, LiveRoundStatus, ParcelDetail, ParcelSummary
from .mail import MailItem, parse_mail_items

_LOGGER = logging.getLogger(__name__)

_SUCCESS = {"success", "SUCCESS"}
MAX_MAIL_IMAGE_BYTES = 5 * 1024 * 1024


def _mail_image_url(value: str) -> str:
    """Only fetch HTTPS scans on bpost or Azure Blob Storage hosts."""
    try:
        url = URL(value, encoded=True)
        host = url.host or ""
        allowed = any(host == domain or host.endswith("." + domain)
                      for domain in ("bpost.be", "bpost.cloud", "blob.core.windows.net"))
        if (url.scheme != "https" or not allowed or url.port != 443
                or url.user is not None or url.password is not None or url.fragment):
            raise ValueError
    except (TypeError, ValueError):
        raise BpostApiError("Unsupported Mail Ahead image address.") from None
    return str(url)


def _retry_after(value: str | None) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return 300
    return max(60, seconds) if math.isfinite(seconds) else 300


def _response(data: dict[str, Any]) -> dict[str, Any]:
    body = data.get("response")
    if data.get("status") not in _SUCCESS or not isinstance(body, dict):
        raise BpostApiError("Unexpected My bpost response envelope.")
    return body


class BpostClient:
    """Minimal async client: login, parcels list/details, live chunks.

    Credentials supplied to the constructor are consumed by the first login.
    Subsequent authentication uses rotating tokens only. A rejected refresh
    requires an explicit login; a service outage never triggers a login.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession | None = None,
        *,
        app_lang: str = "fr",
        api_key: str = X_API_KEY,
        email: str | None = None,
        password: str | None = None,
        tokens: AuthTokens | None = None,
        on_tokens_updated: Callable[[AuthTokens], Awaitable[None]] | None = None,
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
        self._tokens = tokens
        self._on_tokens_updated = on_tokens_updated
        self._auth_lock = asyncio.Lock()
        self._retry_at = 0.0
        self._image_session: aiohttp.ClientSession | None = None

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
        if self._image_session is not None:
            await self._image_session.close()
            self._image_session = None
        if self._own_session and self._session is not None:
            await self._session.close()
            self._session = None

    # -- authentication -------------------------------------------------

    async def login(self, email: str | None = None,
                    password: str | None = None) -> AuthTokens:
        async with self._auth_lock:
            return await self._login(email, password)

    async def _login(self, email: str | None = None,
                     password: str | None = None) -> AuthTokens:
        email = email or self._email
        password = password or self._password
        self._email = self._password = None
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
        body = data.get("response")
        if data.get("status") not in _SUCCESS:
            raise BpostAuthError("Login rejected by My bpost.")
        if not isinstance(body, dict) or not isinstance(body.get("accessToken"), str) or not body["accessToken"]:
            raise BpostApiError("Invalid login response from My bpost.")
        tokens = AuthTokens(
            access_token=body["accessToken"],
            refresh_token=body.get("refreshToken"),
            expires_in=body.get("expiresIn"),
            token_type=body.get("tokenType"),
        )
        await self._set_tokens(tokens)
        return tokens

    async def _set_tokens(self, tokens: AuthTokens) -> None:
        if (not isinstance(tokens.access_token, str) or not tokens.access_token
                or (tokens.refresh_token is not None
                    and (not isinstance(tokens.refresh_token, str) or not tokens.refresh_token))):
            raise BpostApiError("Invalid token pair from My bpost.")
        self._tokens = tokens
        if self._on_tokens_updated is not None:
            await self._on_tokens_updated(tokens)

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
        except BpostAuthError:
            return False
        body = data.get("response")
        if data.get("status") not in _SUCCESS:
            return False
        if not isinstance(body, dict):
            raise BpostApiError("Invalid refresh response from My bpost.")
        access = body.get("access_token") or body.get("accessToken")
        new_refresh = body.get("refresh_token") or body.get("refreshToken")
        if not isinstance(access, str) or not access:
            raise BpostApiError("Missing access token in refresh response.")
        await self._set_tokens(AuthTokens(
            access_token=access,
            refresh_token=new_refresh or refresh,
            expires_in=body.get("expiresIn"),
            token_type=body.get("tokenType"),
        ))
        return True

    async def _reauth(self, rejected: AuthTokens) -> None:
        async with self._auth_lock:
            # Another request may already have rotated this exact token pair.
            if self._tokens is not rejected:
                return
            if await self._try_refresh():
                return
            raise BpostAuthError("Session expired; sign in to My bpost again.")

    # -- low level ------------------------------------------------------

    async def _post_raw(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        token: str | None,
        with_static: bool = True,
    ) -> dict[str, Any]:
        remaining = self._retry_at - monotonic()
        if remaining > 0:
            raise BpostRateLimitError(remaining)
        session = await self._ensure_session()
        headers = self._base_headers(with_static=with_static)
        if token:
            # NOTE: raw token, no "Bearer" prefix (as the official app does).
            headers["Authorization"] = token
        try:
            async with session.post(
                BASE_URL + path, json=payload, headers=headers,
                timeout=self._timeout,
            ) as resp:
                if resp.status == 429:
                    delay = _retry_after(resp.headers.get("Retry-After"))
                    self._retry_at = monotonic() + delay
                    raise BpostRateLimitError(delay)
                if resp.status == 503:
                    raise BpostMaintenanceError("My bpost backend in maintenance.")
                try:
                    data = await resp.json()
                except (ValueError, aiohttp.ContentTypeError):
                    if resp.status in (401, 403):
                        raise BpostAuthError("My bpost rejected the session.") from None
                    raise BpostApiError(f"{path}: invalid JSON (HTTP {resp.status}).") from None
                code = data.get("code") if isinstance(data, dict) else None
                if code == "APP_IN_MAINTENANCE":
                    raise BpostMaintenanceError("My bpost backend in maintenance.")
                if code == "APPVERSION_NOT_SUPPORTED" and resp.status in (401, 403) and token is None:
                    raise BpostForceUpdateError("Backend rejected the client (app version or key).")
                if resp.status in (401, 403):
                    raise BpostAuthError("My bpost rejected the session.")
                if resp.status >= 400:
                    raise BpostApiError(f"{path}: HTTP {resp.status}.")
                if not isinstance(data, dict):
                    raise BpostApiError(f"{path}: unexpected payload.")
                return data
        except (aiohttp.ClientError, TimeoutError):
            raise BpostApiError(f"{path}: unable to reach My bpost.") from None

    async def _post_authed(self, path: str,
                           payload: dict[str, Any]) -> dict[str, Any]:
        if not self._tokens:
            async with self._auth_lock:
                if not self._tokens:
                    await self._login()
        assert self._tokens is not None
        tokens = self._tokens
        try:
            return await self._post_raw(
                path, payload, token=tokens.access_token)
        except BpostAuthError:
            _LOGGER.debug("Token rejected, re-authenticating for %s", path)
            await self._reauth(tokens)
            assert self._tokens is not None
            return await self._post_raw(
                path, payload, token=self._tokens.access_token)

    # -- parcels --------------------------------------------------------

    async def get_parcels_list(self) -> list[ParcelSummary]:
        data = await self._post_authed(
            "parcel/getparcelslist", {"appLang": self._app_lang})
        items = _response(data).get("items", [])
        if not isinstance(items, list):
            raise BpostApiError("Unexpected My bpost parcel list.")
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
        response = _response(data)
        sections = response.get("active") or {}
        history_items = response.get("history") or []
        if not isinstance(sections, dict) or not isinstance(history_items, list):
            raise BpostApiError("Unexpected My bpost parcel details.")
        active: list[ParcelDetail] = []
        for section in sections.values():
            if isinstance(section, list):
                active.extend(ParcelDetail.from_dict(p) for p in section
                              if isinstance(p, dict))
        history = [ParcelDetail.from_dict(p)
                   for p in history_items
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
        except (BpostAuthError, BpostRateLimitError):
            raise
        except BpostError:
            return None
        if data.get("status") not in _SUCCESS:
            return None
        return LiveRoundStatus.from_chunk(data)

    async def get_mail_summary(self) -> dict[str, Any]:
        data = await self._post_authed(
            "mails/getmailsummary", {"appLang": self._app_lang})
        return _response(data)

    async def get_letters(self, from_date: date, to_date: date) -> list[MailItem]:
        if not 0 <= (to_date - from_date).days <= 30:
            raise ValueError("Mail Ahead date range must span at most 31 days.")
        data = await self._post_authed("mmt/retrieveImages", {
            "appLang": self._app_lang, "fromDate": from_date.isoformat(), "toDate": to_date.isoformat(),
        })
        return parse_mail_items(_response(data).get("images"))

    async def get_mail_image(self, image_url: str) -> tuple[bytes, str]:
        """Fetch on demand without account headers, cookies, redirects or disk writes."""
        url = _mail_image_url(image_url)
        remaining = self._retry_at - monotonic()
        if remaining > 0:
            raise BpostRateLimitError(remaining)
        if self._image_session is None or self._image_session.closed:
            self._image_session = aiohttp.ClientSession(
                cookie_jar=aiohttp.DummyCookieJar(),
                trust_env=self._session.trust_env if self._session else False,
            )
        try:
            async with self._image_session.get(url, timeout=self._timeout, allow_redirects=False) as response:
                if response.status == 429:
                    delay = _retry_after(response.headers.get("Retry-After"))
                    self._retry_at = monotonic() + delay
                    raise BpostRateLimitError(delay)
                if response.status != 200:
                    raise BpostApiError("Mail Ahead image unavailable.")
                content_type = response.content_type
                if content_type not in {"image/jpeg", "image/png", "image/webp"}:
                    raise BpostApiError("Unsupported Mail Ahead image type.")
                if response.content_length is not None and response.content_length > MAX_MAIL_IMAGE_BYTES:
                    raise BpostApiError("Mail Ahead image exceeds size limit.")
                content = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    content.extend(chunk)
                    if len(content) > MAX_MAIL_IMAGE_BYTES:
                        raise BpostApiError("Mail Ahead image exceeds size limit.")
                signatures = {
                    "image/jpeg": content.startswith(b"\xff\xd8\xff"),
                    "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
                    "image/webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
                }
                if not signatures[content_type]:
                    raise BpostApiError("Invalid Mail Ahead image content.")
                return bytes(content), content_type
        except (aiohttp.ClientError, TimeoutError):
            raise BpostApiError("Unable to fetch Mail Ahead image.") from None
