"""Account-scoped entity identities and migration preserving entity IDs."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN


def unique_id(entry: ConfigEntry, key: str) -> str:
    return f"{entry.entry_id}_{key}"


@callback
def async_migrate_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    registry = er.async_get(hass)
    changes = []
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.platform != DOMAIN or entity.unique_id.startswith(f"{entry.entry_id}_"):
            continue
        target = unique_id(entry, entity.unique_id)
        existing = registry.async_get_entity_id(entity.domain, DOMAIN, target)
        if existing is not None and existing != entity.entity_id:
            raise ConfigEntryError("Conflicting My bpost entity identity; migration was not applied.")
        changes.append((entity.entity_id, target))
    for entity_id, target in changes:
        registry.async_update_entity(entity_id, new_unique_id=target)
