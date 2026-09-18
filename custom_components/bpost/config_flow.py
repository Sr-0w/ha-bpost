"""Config flow for the bpost integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_APP_LANG, CONF_PASSWORD, CONF_USERNAME, DOMAIN
from .pybpost.client import BpostClient
from .pybpost.const import X_API_KEY
from .pybpost.exceptions import BpostAuthError, BpostError

_LANGUAGES = ["fr", "nl", "en", "de"]


class BpostConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for bpost."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_USERNAME].strip()
            await self.async_set_unique_id(email.lower())
            self._abort_if_unique_id_configured()
            try:
                client = BpostClient(
                    async_get_clientsession(self.hass),
                    app_lang=user_input.get(CONF_APP_LANG, "fr"),
                    api_key=X_API_KEY,
                )
                await client.login(email, user_input[CONF_PASSWORD])
            except BpostAuthError:
                errors["base"] = "invalid_auth"
            except BpostError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"bpost ({email})",
                    data={
                        CONF_USERNAME: email,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_APP_LANG: user_input.get(CONF_APP_LANG, "fr"),
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_APP_LANG, default="fr"): vol.In(_LANGUAGES),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                client = BpostClient(
                    async_get_clientsession(self.hass),
                    app_lang=entry.data.get(CONF_APP_LANG, "fr"),
                    api_key=X_API_KEY,
                )
                await client.login(
                    entry.data[CONF_USERNAME], user_input[CONF_PASSWORD])
            except BpostAuthError:
                errors["base"] = "invalid_auth"
            except BpostError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )
