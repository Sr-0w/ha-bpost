"""Admin-only manual parcel management and private aggregate summaries."""

import asyncio

import voluptuous as vol

from homeassistant.core import SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.service import async_register_admin_service

from .const import DOMAIN
from .pybpost.tracking import tracking_inputs
from .selection import summary

LOCK = "my_bpost_management_lock"
PARCEL_SCHEMA = vol.Schema({
    vol.Required("barcode"): str, vol.Required("postal_code"): str,
    vol.Optional("label",default=""): vol.All(str,vol.Length(max=80)),
    vol.Optional("group",default=""): vol.All(str,vol.Length(max=40)),
    vol.Optional("direction",default="unknown"): vol.In(["unknown","incoming","outgoing"]),
    vol.Optional("app_lang",default="fr"): vol.In(["fr","nl","en","de"]),
})


async def async_track_parcels(hass, parcels):
    """Sequential bounded imports; return one explicit result per requested row."""
    if not 1 <= len(parcels) <= 20:
        raise ServiceValidationError("Provide between 1 and 20 parcels")
    cleaned = []
    try:
        for item in parcels:
            item = PARCEL_SCHEMA(item)
            code, postcode = tracking_inputs(item["barcode"],item["postal_code"])
            cleaned.append({**item,"barcode":code,"postal_code":postcode})
    except (ValueError,vol.Invalid):
        raise ServiceValidationError("Invalid parcel input; no parcels were added") from None
    lock = hass.data.setdefault(LOCK,asyncio.Lock())
    results = []
    async with lock:
        paused = False
        for index, item in enumerate(cleaned,1):
            if paused:
                results.append({"row":index,"status":"rate_limited"})
                continue
            existing = next((e for e in hass.config_entries.async_entries(DOMAIN)
                             if e.data.get("source")=="public" and e.data.get("barcode")==item["barcode"]),None)
            if existing:
                results.append({"row":index,"status":"already_configured","entry_id":existing.entry_id})
                continue
            result = await hass.config_entries.flow.async_init(DOMAIN,context={"source":"user"})
            result = await hass.config_entries.flow.async_configure(result["flow_id"],{"next_step_id":"tracking"})
            result = await hass.config_entries.flow.async_configure(result["flow_id"],item)
            if result["type"] == "create_entry":
                results.append({"row":index,"status":"added","entry_id":result["result"].entry_id})
            else:
                reason = result.get("errors",{}).get("base",result.get("reason","cannot_connect"))
                results.append({"row":index,"status":reason})
                if result["type"] == "form":
                    hass.config_entries.flow.async_abort(result["flow_id"])
                paused = reason == "rate_limited"
    return {"results":results}


def async_register_services(hass):
    async def track(call):
        return await async_track_parcels(hass,call.data["parcels"])

    async def untrack(call):
        async with hass.data.setdefault(LOCK,asyncio.Lock()):
            entries = {key: hass.config_entries.async_get_entry(key) for key in dict.fromkeys(call.data["entry_ids"])}
            if any(e and (e.domain != DOMAIN or e.data.get("source") != "public") for e in entries.values()):
                raise ServiceValidationError("Only manual My bpost entries can be removed by this action")
            results = []
            for key, entry in entries.items():
                if entry:
                    success = await hass.config_entries.async_remove(entry.entry_id)
                    results.append({"entry_id":entry.entry_id,"status":"removed" if success else "failed"})
                else:
                    results.append({"entry_id":key,"status":"not_found"})
            return {"results":results}

    async def get_summary(call):
        return summary(hass,entry_id=call.data.get("entry_id"),group=call.data.get("group") or None)

    async_register_admin_service(hass,DOMAIN,"track_parcels",track,
        schema=vol.Schema({vol.Required("parcels"):vol.All([PARCEL_SCHEMA],vol.Length(min=1,max=20))}),
        supports_response=SupportsResponse.OPTIONAL)
    async_register_admin_service(hass,DOMAIN,"untrack_parcels",untrack,
        schema=vol.Schema({vol.Required("entry_ids"):vol.All([str],vol.Length(min=1,max=20))}),
        supports_response=SupportsResponse.OPTIONAL)
    async_register_admin_service(hass,DOMAIN,"get_summary",get_summary,
        schema=vol.Schema({vol.Optional("entry_id"):str,vol.Optional("group"):str}),
        supports_response=SupportsResponse.ONLY)
