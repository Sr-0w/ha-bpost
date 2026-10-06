"""Install the release ZIP over a legacy account and run HA's migration/reauth.

The v1 account and unscoped registry identities match the v0.2.0 release.
Only bpost HTTP methods are replaced; HA owns entry setup, migration and reload.
"""

import importlib
from pathlib import Path
import socket
import sys
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import AsyncMock, patch

import aiohttp
from homeassistant.bootstrap import async_setup_hass
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.runner import RuntimeConfig

from runtime_support import isolated_runtime, install_release


class UpgradeRuntimeTest(unittest.IsolatedAsyncioTestCase):
    @isolated_runtime
    async def test_v1_migration_reauth_preserves_entities_options_and_reload(self):
        for name in list(sys.modules):
            if name == "custom_components" or name.startswith("custom_components."):
                del sys.modules[name]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install_release(root)
            (root / "custom_components/__init__.py").write_text("")
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            (root / "configuration.yaml").write_text(
                f"homeassistant:\n  time_zone: Europe/Brussels\nhttp:\n"
                f"  server_host: 127.0.0.1\n  server_port: {port}\nfrontend:\nmy_bpost:\n")
            sys.path.insert(0, temp)
            hass = None
            try:
                client = importlib.import_module("custom_components.my_bpost.pybpost.client")
                models = importlib.import_module("custom_components.my_bpost.pybpost.models")
                summary = models.ParcelSummary("upgrade-parcel", "IN_TRANSIT")
                detail = models.ParcelDetail("upgrade-parcel", current_status="IN_TRANSIT",
                    user_type="RECEIVER", delivery_point=models.DeliveryPoint(latitude=50.85, longitude=4.35))
                with patch.object(client.BpostClient, "login", new=AsyncMock(return_value=models.AuthTokens("new-access", "new-refresh"))) as login, patch.object(
                    client.BpostClient, "get_parcels_list", new=AsyncMock(return_value=[summary])) as parcels, patch.object(
                    client.BpostClient, "get_parcels_details", new=AsyncMock(return_value=([detail], []))):
                    hass = await async_setup_hass(RuntimeConfig(config_dir=temp, skip_pip=True))
                    self.assertIsNotNone(hass)
                    await hass.async_start()
                    options = {"retention_days": 21, "enable_live_tracking": False, "enable_mail": False}
                    entry = ConfigEntry(version=1, minor_version=1, domain="my_bpost",
                        title="Renamed account", source="user", unique_id="upgrade@example.invalid",
                        data={"username": "upgrade@example.invalid", "password": "legacy-synthetic", "app_lang": "nl"},
                        options=options, discovery_keys=MappingProxyType({}), subentries_data=None)
                    # Seed the legacy registry before allowing HA to load the entry.
                    with patch.object(hass.config_entries, "async_setup", new=AsyncMock(return_value=True)):
                        await hass.config_entries.async_add(entry)
                    registry = er.async_get(hass)
                    legacy = [registry.async_get_or_create(domain, "my_bpost", key, config_entry=entry,
                        suggested_object_id=name) for domain, key, name in (
                            ("sensor", "packages", "my_renamed_counter"),
                            ("sensor", "upgrade-parcel", "my_renamed_parcel"),
                            ("device_tracker", "upgrade-parcel_tracker", "my_renamed_pickup"))]
                    registry.async_update_entity(legacy[1].entity_id, name="My custom parcel")
                    events = []
                    hass.bus.async_listen("my_bpost_new_package", events.append)
                    self.assertFalse(await hass.config_entries.async_setup(entry.entry_id))
                    await hass.async_block_till_done()
                    self.assertEqual(entry.version, 2)
                    self.assertNotIn("password", entry.data)
                    self.assertEqual(dict(entry.options), options)
                    login.assert_not_awaited()
                    parcels.assert_not_awaited()  # Migration works without a backend.
                    flows = hass.config_entries.flow.async_progress_by_handler("my_bpost")
                    self.assertEqual(len(flows), 1)
                    self.assertEqual(flows[0]["step_id"], "reauth_confirm")
                    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"],
                        {"password": "new-synthetic"})
                    self.assertEqual(result["reason"], "reauth_successful")
                    await hass.async_block_till_done()
                    self.assertEqual(entry.state, ConfigEntryState.LOADED)
                    self.assertEqual(entry.title, "Renamed account")
                    self.assertEqual(entry.unique_id, "upgrade@example.invalid")
                    self.assertEqual(entry.data["app_lang"], "nl")
                    self.assertNotIn("password", entry.data)
                    self.assertEqual(entry.data["refresh_token"], "new-refresh")
                    self.assertEqual(dict(entry.options), options)
                    for entity in legacy:
                        current = registry.async_get(entity.entity_id)
                        self.assertEqual(current.unique_id, f"{entry.entry_id}_{entity.unique_id}")
                        self.assertIsNotNone(hass.states.get(entity.entity_id))
                    self.assertEqual(registry.async_get(legacy[1].entity_id).name, "My custom parcel")
                    self.assertEqual(hass.states.get(legacy[0].entity_id).state, "1")
                    self.assertEqual(hass.states.get(legacy[1].entity_id).state, "in_transit")
                    self.assertEqual(events, [])
                    # Serve exactly the card that shipped in the extracted ZIP.
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"http://127.0.0.1:{port}/my_bpost_card/my-bpost-parcels-card.js?v=0.6.0") as response:
                            self.assertEqual(response.status, 200)
                            self.assertEqual(await response.read(), (root / "custom_components/my_bpost/frontend/my-bpost-parcels-card.js").read_bytes())
                    identities = {item.entity_id: item.unique_id for item in er.async_entries_for_config_entry(registry, entry.entry_id)}
                    self.assertTrue(await hass.config_entries.async_reload(entry.entry_id))
                    await hass.async_block_till_done()
                    self.assertEqual(entry.state, ConfigEntryState.LOADED)
                    self.assertEqual(identities, {item.entity_id: item.unique_id for item in er.async_entries_for_config_entry(registry, entry.entry_id)})
                    self.assertEqual(login.await_count, 1)
                    self.assertEqual(events, [])
                    await hass.async_stop()
                    stored = (root / ".storage/core.config_entries").read_text()
                    self.assertNotIn("legacy-synthetic", stored)
                    self.assertNotIn("new-synthetic", stored)
                    self.assertNotIn('"password"', stored)
                    self.assertIn("new-refresh", stored)
                    hass = None
            finally:
                if hass is not None:
                    await hass.async_stop()
                sys.path.remove(temp)
