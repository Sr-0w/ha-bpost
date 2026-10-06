"""Config flow for the My bpost integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .auth import session_data
from .const import CONF_APP_LANG, CONF_PASSWORD, CONF_USERNAME, DEFAULT_RETENTION_DAYS, DOMAIN
from .pybpost.client import BpostClient
from .pybpost.const import X_API_KEY
from .pybpost.exceptions import BpostAuthError, BpostError, BpostRateLimitError
from .pybpost.tracking import PublicTrackingClient, BpostTrackingNotFound, tracking_inputs

_LANGUAGES = ["fr", "nl", "en", "de"]


class BpostConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for My bpost."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "BpostOptionsFlow":
        return BpostOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # Keep programmatic account setup compatible with existing callers.
        if user_input is not None:
            return await self.async_step_account(user_input)
        return self.async_show_menu(step_id="user", menu_options=["account", "tracking", "bulk"])

    async def async_step_bulk(self, user_input=None):
        errors = {}
        if user_input is not None:
            codes = [line.strip() for line in user_input["barcodes"].splitlines() if line.strip()]
            if not 1 <= len(codes) <= 20:
                errors["base"] = "invalid_bulk"
            else:
                from homeassistant.exceptions import ServiceValidationError
                from .services import async_track_parcels
                try:
                    outcome = await async_track_parcels(self.hass,[{
                        "barcode":code,"postal_code":user_input["postal_code"],
                        "group":user_input.get("group",""),"app_lang":user_input.get("app_lang","fr")}
                        for code in codes])
                except ServiceValidationError:
                    errors["base"] = "invalid_tracking"
                else:
                    results = outcome["results"]
                    return self.async_abort(reason="bulk_complete",description_placeholders={
                        "added":str(sum(r["status"]=="added" for r in results)),
                        "existing":str(sum(r["status"]=="already_configured" for r in results)),
                        "failed":", ".join(str(r["row"]) for r in results if r["status"] not in ("added","already_configured")) or "—"})
        return self.async_show_form(step_id="bulk",errors=errors,data_schema=vol.Schema({
            vol.Required("barcodes"):selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Required("postal_code"):str,
            vol.Optional("group",default=""):vol.All(str,vol.Length(max=40)),
            vol.Optional("app_lang",default="fr"):vol.In(_LANGUAGES),
        }))

    async def async_step_tracking(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                barcode, postcode = tracking_inputs(user_input["barcode"], user_input["postal_code"])
            except ValueError:
                errors["base"] = "invalid_tracking"
            else:
                await self.async_set_unique_id(f"tracking:{barcode}")
                self._abort_if_unique_id_configured()
                errors = await _validate_tracking(self.hass, barcode, postcode, user_input.get(CONF_APP_LANG, "fr"))
                if not errors:
                    label = user_input.get("label", "").strip()
                    return self.async_create_entry(title=label or f"bpost · {barcode[-6:]}", data={
                        "source": "public", "barcode": barcode, "postal_code": postcode,
                        "label": label, CONF_APP_LANG: user_input.get(CONF_APP_LANG, "fr"),
                        "group": user_input.get("group","").strip(),
                        "direction": user_input.get("direction","unknown"),
                    })
        return self.async_show_form(step_id="tracking", errors=errors, data_schema=vol.Schema({
            vol.Required("barcode"): str,
            vol.Required("postal_code"): str,
            vol.Optional("label", default=""): vol.All(str, vol.Length(max=80)),
            vol.Optional("group", default=""): vol.All(str, vol.Length(max=40)),
            vol.Optional("direction", default="unknown"): vol.In(["unknown","incoming","outgoing"]),
            vol.Optional(CONF_APP_LANG, default="fr"): vol.In(_LANGUAGES),
        }))

    async def async_step_account(
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
                tokens = await client.login(email, user_input[CONF_PASSWORD])
            except BpostAuthError:
                errors["base"] = "invalid_auth"
            except BpostError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"My bpost ({email})",
                    data=session_data({
                        CONF_USERNAME: email,
                        CONF_APP_LANG: user_input.get(CONF_APP_LANG, "fr"),
                    }, tokens),
                )
        return self.async_show_form(
            step_id="account",
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
                tokens = await client.login(
                    entry.data[CONF_USERNAME], user_input[CONF_PASSWORD])
            except BpostAuthError:
                errors["base"] = "invalid_auth"
            except BpostError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data=session_data(entry.data, tokens),
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )


class BpostOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self.config_entry.data.get("source") == "public":
            return await self.async_step_tracking_options(user_input)
        if user_input is not None:
            return self.async_create_entry(title="", data={**self.config_entry.options, **user_input})
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Optional("enable_live_tracking", default=self.config_entry.options.get("enable_live_tracking", True)): bool,
            vol.Optional("retention_days", default=self.config_entry.options.get("retention_days", DEFAULT_RETENTION_DAYS)): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
            vol.Optional("enable_mail", default=self.config_entry.options.get("enable_mail", True)): bool,
            vol.Optional("enable_mail_images", default=self.config_entry.options.get("enable_mail_images", False)): bool,
            vol.Optional("eta_change_minutes",default=self.config_entry.options.get("eta_change_minutes",30)):vol.All(vol.Coerce(int),vol.Range(min=5,max=240)),
            vol.Optional("group",default=self.config_entry.options.get("group","")):vol.All(str,vol.Length(max=40)),
        }))

    async def async_step_tracking_options(self, user_input=None) -> ConfigFlowResult:
        entry = self.config_entry
        errors = {}
        if user_input is not None:
            try:
                barcode, postcode = tracking_inputs(entry.data["barcode"], user_input["postal_code"])
            except ValueError:
                errors["base"] = "invalid_tracking"
            else:
                if postcode != entry.options.get("postal_code", entry.data["postal_code"]):
                    errors = await _validate_tracking(self.hass, barcode, postcode, entry.data.get(CONF_APP_LANG, "fr"))
                if not errors:
                    return self.async_create_entry(title="", data={**entry.options, **user_input,
                        "postal_code": postcode, "label": user_input.get("label", "").strip()})
        return self.async_show_form(step_id="tracking_options", errors=errors, data_schema=vol.Schema({
            vol.Required("postal_code", default=entry.options.get("postal_code", entry.data["postal_code"])): str,
            vol.Optional("label", default=entry.options.get("label", entry.data.get("label", ""))): vol.All(str, vol.Length(max=80)),
            vol.Optional("direction", default=entry.options.get("direction", entry.data.get("direction","unknown"))): vol.In(["unknown", "incoming", "outgoing"]),
            vol.Optional("group",default=entry.options.get("group",entry.data.get("group",""))):vol.All(str,vol.Length(max=40)),
            vol.Optional("eta_change_minutes",default=entry.options.get("eta_change_minutes",30)):vol.All(vol.Coerce(int),vol.Range(min=5,max=240)),
            vol.Optional("retention_days", default=entry.options.get("retention_days", DEFAULT_RETENTION_DAYS)): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
        }))


async def _validate_tracking(hass, barcode, postcode, lang):
    client = PublicTrackingClient(trust_env=async_get_clientsession(hass).trust_env, app_lang=lang)
    try:
        await client.get_parcel(barcode, postcode)
    except BpostTrackingNotFound:
        return {"base": "tracking_not_found"}
    except BpostRateLimitError:
        return {"base": "rate_limited"}
    except BpostError:
        return {"base": "cannot_connect"}
    finally:
        await client.close()
    return {}
