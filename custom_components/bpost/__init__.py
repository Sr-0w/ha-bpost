"""My bpost integration: parcels linked to your bpost account."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType

from .const import CONF_APP_LANG, CONF_PASSWORD, CONF_USERNAME, DEFAULT_SCAN_MINUTES, DOMAIN
from .coordinator import BpostDataUpdateCoordinator
from .pybpost.client import BpostClient
from .pybpost.exceptions import BpostAuthError, BpostError
from .pybpost.const import X_API_KEY

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.DEVICE_TRACKER]

CARD_URL = "/bpost_card/bpost-parcels-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the bpost integration (serve the Lovelace card)."""
    try:
        from homeassistant.components import frontend
        from homeassistant.components.http import StaticPathConfig

        base = Path(__file__).parent
        version = json.loads((base / "manifest.json").read_text())["version"]
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL.rsplit("/", 1)[0], str(base / "frontend"), True)]
        )
        frontend.add_extra_js_url(hass, f"{CARD_URL}?v={version}")
    except Exception as err:  # never break setup for the card
        _LOGGER.warning("Bpost parcels card not registered: %s", err)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up bpost from a config entry."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    client = BpostClient(
        async_get_clientsession(hass),
        app_lang=entry.data.get(CONF_APP_LANG, "fr"),
        api_key=X_API_KEY,
        email=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )
    coordinator = BpostDataUpdateCoordinator(
        hass, client, entry,
        scan_minutes=entry.options.get("scan_interval_minutes", DEFAULT_SCAN_MINUTES),
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except BpostAuthError as err:
        raise ConfigEntryAuthFailed(f"My bpost login failed: {err}") from err
    except BpostError as err:
        raise ConfigEntryNotReady(f"My bpost unavailable: {err}") from err

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
