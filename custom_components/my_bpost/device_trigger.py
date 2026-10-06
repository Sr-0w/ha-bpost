"""Account device triggers offered by Home Assistant's automation editor."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA, InvalidDeviceAutomationConfig
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN, EVENT_NEW_PACKAGE, EVENT_STATUS_CHANGED, EVENT_OUT_FOR_DELIVERY,
    EVENT_DELIVERED, EVENT_AT_PICKUP_POINT, EVENT_RETURNED, EVENT_PROBLEM, EVENT_ETA_CHANGED,
    EVENT_LETTER_ANNOUNCED,
)

TRIGGERS = {
    "new_package": EVENT_NEW_PACKAGE,
    "status_changed": EVENT_STATUS_CHANGED,
    "out_for_delivery": EVENT_OUT_FOR_DELIVERY,
    "delivered": EVENT_DELIVERED,
    "at_pickup_point": EVENT_AT_PICKUP_POINT,
    "returned": EVENT_RETURNED,
    "problem": EVENT_PROBLEM,
    "eta_changed": EVENT_ETA_CHANGED,
    "letter_announced": EVENT_LETTER_ANNOUNCED,
}
TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend({
    vol.Required("type"): vol.In(TRIGGERS),
})


def _account_id(hass: HomeAssistant, device_id: str) -> str:
    device = dr.async_get(hass).async_get(device_id)
    if device:
        for domain, identifier in device.identifiers:
            entry = hass.config_entries.async_get_entry(identifier)
            if (domain == DOMAIN and entry and entry.domain == DOMAIN
                    and entry.entry_id in device.config_entries):
                return identifier
    raise InvalidDeviceAutomationConfig("This device is not a My bpost account")


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict[str, str]]:
    try:
        entry_id = _account_id(hass, device_id)
    except InvalidDeviceAutomationConfig:
        return []
    return [{"platform": "device", "domain": DOMAIN, "device_id": device_id, "type": kind}
            for kind in TRIGGERS
            if kind != "letter_announced" or hass.config_entries.async_get_entry(entry_id).data.get("source") != "public"]


async def async_validate_trigger_config(hass: HomeAssistant, config: ConfigType) -> ConfigType:
    config = TRIGGER_SCHEMA(config)
    entry_id = _account_id(hass, config["device_id"])
    if (config["type"] == "letter_announced"
            and hass.config_entries.async_get_entry(entry_id).data.get("source") == "public"):
        raise InvalidDeviceAutomationConfig("Public parcel tracking does not provide Mail Ahead")
    return config


async def async_attach_trigger(hass: HomeAssistant, config: ConfigType,
                               action: TriggerActionType, trigger_info: TriggerInfo) -> CALLBACK_TYPE:
    config = await async_validate_trigger_config(hass, config)
    event_config = event_trigger.TRIGGER_SCHEMA({
        "platform": "event", "event_type": TRIGGERS[config["type"]],
        "event_data": {"entry_id": _account_id(hass, config["device_id"])},
    })
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type="device")
