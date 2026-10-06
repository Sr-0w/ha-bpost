"""My bpost integration: parcels linked to your bpost account."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import config_validation as cv

from .auth import session_data, stored_tokens
from .const import CONF_APP_LANG, CONF_PASSWORD, DEFAULT_SCAN_MINUTES
from .coordinator import BpostDataUpdateCoordinator
from .entity import async_migrate_entity_ids
from .pybpost.client import BpostClient
from .pybpost.const import X_API_KEY
from .pybpost.models import AuthTokens
from .pybpost.tracking import PublicTrackingClient
from .tracking import PublicTrackingCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.empty_config_schema("my_bpost")

PLATFORMS = [Platform.SENSOR, Platform.DEVICE_TRACKER, Platform.CALENDAR, Platform.IMAGE]

CARD_URL = "/my_bpost_card/my-bpost-parcels-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the My bpost integration (serve the Lovelace card)."""
    from .notifications import KEY, NotificationHub
    from .services import async_register_services

    if KEY not in hass.data:
        hub = NotificationHub(hass)
        await hub.async_setup()
        hass.data[KEY] = hub
        async_register_services(hass)
    try:
        from homeassistant.components import frontend
        from homeassistant.components.http import StaticPathConfig

        base = Path(__file__).parent
        manifest = await hass.async_add_executor_job((base / "manifest.json").read_text)
        version = json.loads(manifest)["version"]
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL.rsplit("/", 1)[0], str(base / "frontend"), True)]
        )
        frontend.add_extra_js_url(hass, f"{CARD_URL}?v={version}")
    except Exception as err:  # never break setup for the card
        _LOGGER.warning("Bpost parcels card not registered: %s", err)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up My bpost from a config entry."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    tokens = stored_tokens(entry.data)
    public = entry.data.get("source") == "public"
    if tokens is None and not public:
        raise ConfigEntryAuthFailed("Sign in to My bpost to create a renewable session.")

    async def async_persist_tokens(updated: AuthTokens) -> None:
        hass.config_entries.async_update_entry(entry, data=session_data(entry.data, updated))

    client = PublicTrackingClient(
        trust_env=async_get_clientsession(hass).trust_env,
        app_lang=entry.data.get(CONF_APP_LANG, "fr"),
    ) if public else BpostClient(
        async_get_clientsession(hass),
        app_lang=entry.data.get(CONF_APP_LANG, "fr"),
        api_key=X_API_KEY,
        tokens=tokens,
        on_tokens_updated=async_persist_tokens,
    )
    coordinator_class = PublicTrackingCoordinator if public else BpostDataUpdateCoordinator
    coordinator = coordinator_class(
        hass, client, entry,
        scan_minutes=entry.options.get("scan_interval_minutes", DEFAULT_SCAN_MINUTES),
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        # The public client owns a separate session, including failed setup.
        await client.close()
        raise

    entry.runtime_data = coordinator
    async_migrate_entity_ids(hass, entry)
    await coordinator.async_start_live()
    await coordinator.async_start_mail()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    options = dict(entry.options)

    async def async_options_updated(hass: HomeAssistant, updated: ConfigEntry) -> None:
        if dict(updated.options) != options:
            await hass.config_entries.async_reload(updated.entry_id)

    entry.async_on_unload(entry.add_update_listener(async_options_updated))
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Drop legacy passwords locally; HA will request a one-time sign-in.

    Migration is independent of API availability. Entity IDs are untouched.
    """
    if entry.version > 2:
        return False
    if entry.version == 1:
        data = dict(entry.data)
        data.pop(CONF_PASSWORD, None)
        hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the account's persisted parcel baseline when its entry is deleted."""
    from homeassistant.helpers.storage import Store

    await Store(hass, 1, f"my_bpost.{entry.entry_id}.parcels").async_remove()
    await Store(hass, 1, f"my_bpost.{entry.entry_id}.mail").async_remove()
