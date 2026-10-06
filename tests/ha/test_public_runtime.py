"""Public tracking UI, account coexistence, failure isolation and persistence."""

import asyncio
from contextlib import nullcontext
import importlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from homeassistant.bootstrap import async_setup_hass
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.runner import RuntimeConfig

from runtime_support import isolated_runtime, install_release


class PublicRuntimeTest(unittest.IsolatedAsyncioTestCase):
    @isolated_runtime
    async def test_public_flow_options_failures_restart_and_remove(self):
        restoring = os.environ.get("BPOST_PUBLIC_RESTORE")
        for name in list(sys.modules):
            if name == "custom_components" or name.startswith("custom_components."):
                del sys.modules[name]
        with (nullcontext(restoring) if restoring else tempfile.TemporaryDirectory()) as temp:
            root = Path(temp)
            if not restoring:
                install_release(root)
                (root / "custom_components/__init__.py").write_text("")
            with socket.socket() as probe:
                probe.bind(("127.0.0.1",0)); port=probe.getsockname()[1]
            (root / "configuration.yaml").write_text(
                f"homeassistant:\n  time_zone: Europe/Brussels\nhttp:\n  server_host: 127.0.0.1\n  server_port: {port}\nfrontend:\nmy_bpost:\n")
            sys.path.insert(0,temp)
            hass=None
            try:
                api=importlib.import_module("custom_components.my_bpost.pybpost.tracking")
                client=importlib.import_module("custom_components.my_bpost.pybpost.client")
                models=importlib.import_module("custom_components.my_bpost.pybpost.models")
                coord=importlib.import_module("custom_components.my_bpost.coordinator")
                code="SYNTHETIC-TRACKING"
                detail=models.ParcelDetail(code,current_status="DELIVERED" if restoring else "IN_TRANSIT")
                with patch.object(api.PublicTrackingClient,"get_parcel",new=AsyncMock(return_value=detail)) as lookup, patch.object(
                    client.BpostClient,"login",new=AsyncMock(return_value=models.AuthTokens("synthetic","refresh"))) as login, patch.object(
                    client.BpostClient,"get_parcels_list",new=AsyncMock(return_value=[models.ParcelSummary(code,"IN_TRANSIT")])), patch.object(
                    client.BpostClient,"get_parcels_details",new=AsyncMock(return_value=([models.ParcelDetail(code,current_status="IN_TRANSIT")],[]))), patch.object(
                    client.BpostClient,"get_mail_summary",new=AsyncMock(return_value={"isMMTSubscribed":False})), patch.object(
                    coord.BpostDataUpdateCoordinator,"_fire") as fire:
                    hass=await async_setup_hass(RuntimeConfig(config_dir=temp,skip_pip=True))
                    self.assertIsNotNone(hass);await hass.async_start()
                    registry=er.async_get(hass)
                    if restoring:
                        entries=hass.config_entries.async_entries("my_bpost")
                        entry=next(e for e in entries if e.data.get("source")=="public")
                        account=next(e for e in entries if e.data.get("source")!="public")
                        self.assertEqual(entry.state,ConfigEntryState.LOADED)
                        self.assertEqual(entry.options["label"],"Renamed parcel")
                        sensor=registry.async_get_entity_id("sensor","my_bpost",f"{entry.entry_id}_{code}")
                        self.assertEqual(sensor,json.loads((root/"expected.json").read_text())["entity_id"])
                        self.assertEqual(hass.states.get(sensor).state,"delivered")
                        fire.assert_not_called();login.assert_not_awaited()
                        await hass.config_entries.async_remove(entry.entry_id)
                        await hass.async_block_till_done()
                        self.assertIsNone(registry.async_get(sensor))
                        self.assertEqual(er.async_entries_for_config_entry(registry,entry.entry_id),[])
                        self.assertFalse((root/f".storage/my_bpost.{entry.entry_id}.parcels").exists())
                        self.assertFalse((root/f".storage/my_bpost.{entry.entry_id}.mail").exists())
                        self.assertEqual(account.state,ConfigEntryState.LOADED)
                        self.assertTrue(er.async_entries_for_config_entry(registry,account.entry_id))
                        return

                    async def start_tracking():
                        result=await hass.config_entries.flow.async_init("my_bpost",context={"source":"user"})
                        self.assertEqual(result["type"],"menu")
                        result=await hass.config_entries.flow.async_configure(result["flow_id"],{"next_step_id":"tracking"})
                        self.assertEqual(result["step_id"],"tracking")
                        return result

                    result=await start_tracking()
                    data={"barcode":code,"postal_code":"1000","label":"Private parcel name","app_lang":"fr"}
                    result=await hass.config_entries.flow.async_configure(result["flow_id"],{**data,"barcode":" "})
                    self.assertEqual(result["errors"]["base"],"invalid_tracking");lookup.assert_not_awaited()
                    lookup.side_effect=api.BpostTrackingNotFound("synthetic")
                    result=await hass.config_entries.flow.async_configure(result["flow_id"],data)
                    self.assertEqual(result["errors"]["base"],"tracking_not_found")
                    lookup.side_effect=None
                    result=await hass.config_entries.flow.async_configure(result["flow_id"],data)
                    self.assertEqual(result["type"],"create_entry");entry=result["result"]
                    await hass.async_block_till_done()
                    self.assertEqual(entry.state,ConfigEntryState.LOADED);login.assert_not_awaited()
                    fire.assert_not_called()
                    for key in ("username","password","access_token","refresh_token"):
                        self.assertNotIn(key,entry.data)
                    sensor=registry.async_get_entity_id("sensor","my_bpost",f"{entry.entry_id}_{code}")
                    self.assertEqual(hass.states.get(sensor).state,"in_transit")
                    self.assertEqual(hass.states.get(sensor).attributes["tracking_source"],"public")
                    self.assertEqual(hass.states.get(sensor).attributes["friendly_name"],"Private parcel name")
                    self.assertIsNone(registry.async_get_entity_id("sensor","my_bpost",f"{entry.entry_id}_mail_count"))
                    from homeassistant.helpers import device_registry as dr
                    triggers=importlib.import_module("custom_components.my_bpost.device_trigger")
                    device=dr.async_get(hass).async_get_device(identifiers={("my_bpost",entry.entry_id)})
                    offered=await triggers.async_get_triggers(hass,device.id)
                    self.assertEqual(len(offered),8)
                    self.assertNotIn("letter_announced",[item["type"] for item in offered])
                    result=await start_tracking();before=lookup.await_count
                    result=await hass.config_entries.flow.async_configure(result["flow_id"],data)
                    self.assertEqual(result["reason"],"already_configured");self.assertEqual(lookup.await_count,before)

                    # Failure keeps the entity/entry; recovery announces a real transition once.
                    lookup.side_effect=api.BpostApiError("synthetic service error")
                    await entry.runtime_data.async_refresh();await hass.async_block_till_done()
                    self.assertEqual(hass.states.get(sensor).state,"unavailable")
                    self.assertIsNotNone(registry.async_get(sensor))
                    self.assertEqual(hass.config_entries.flow.async_progress_by_handler("my_bpost"),[])
                    lookup.side_effect=api.BpostRateLimitError(900)
                    await entry.runtime_data.async_refresh()
                    self.assertEqual(entry.runtime_data.update_interval.total_seconds(),900)
                    lookup.side_effect=None;detail.current_status="DELIVERED"
                    await entry.runtime_data.async_refresh();await hass.async_block_till_done()
                    self.assertEqual(hass.states.get(sensor).state,"delivered")
                    self.assertEqual([call.args[0] for call in fire.call_args_list],["my_bpost_status_changed","my_bpost_delivered"])
                    fire.reset_mock()

                    result=await hass.config_entries.options.async_init(entry.entry_id)
                    self.assertEqual(result["step_id"],"tracking_options")
                    lookup.side_effect=api.BpostTrackingNotFound("synthetic")
                    result=await hass.config_entries.options.async_configure(result["flow_id"],{
                        "postal_code":"2000","label":"Renamed parcel","direction":"incoming","retention_days":21})
                    self.assertEqual(result["errors"]["base"],"tracking_not_found")
                    self.assertNotIn("postal_code",entry.options)
                    lookup.side_effect=None
                    result=await hass.config_entries.options.async_configure(result["flow_id"],{
                        "postal_code":"2000","label":"Renamed parcel","direction":"incoming","retention_days":21})
                    self.assertEqual(result["type"],"create_entry")
                    await hass.async_block_till_done()
                    self.assertEqual(entry.state,ConfigEntryState.LOADED)
                    self.assertEqual(lookup.call_args.args,(code,"2000"))
                    self.assertEqual(hass.states.get(sensor).attributes["friendly_name"],"Renamed parcel")
                    self.assertEqual(hass.states.get(sensor).attributes["user_type"],"RECEIVER")
                    diagnostics=importlib.import_module("custom_components.my_bpost.diagnostics")
                    diagnostic=json.dumps(await diagnostics.async_get_config_entry_diagnostics(hass,entry))
                    for private in (code,"1000","2000","Private parcel name","Renamed parcel"):
                        self.assertNotIn(private,diagnostic)
                    fire.assert_not_called()

                    # The same parcel on an account is a separate source and survives removal.
                    result=await hass.config_entries.flow.async_init("my_bpost",context={"source":"user"},
                        data={"username":"synthetic@example.invalid","password":"synthetic"})
                    account=result["result"];await hass.async_block_till_done()
                    self.assertEqual(account.state,ConfigEntryState.LOADED)
                    other=registry.async_get_entity_id("sensor","my_bpost",f"{account.entry_id}_{code}")
                    self.assertNotEqual(sensor,other)
                    await hass.async_stop();hass=None
                    (root/"expected.json").write_text(json.dumps({"entity_id":sensor}))
                    process=await asyncio.create_subprocess_exec(sys.executable,"-m","unittest","discover",
                        "-s",str(Path(__file__).parent),"-p",Path(__file__).name,"-v",
                        env={**os.environ,"BPOST_PUBLIC_RESTORE":temp},stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
                    try:
                        output,_=await asyncio.wait_for(process.communicate(),45)
                        self.assertEqual(process.returncode,0,output.decode(errors="replace"))
                    finally:
                        if process.returncode is None:
                            process.kill();await process.wait()
            finally:
                if hass is not None:await hass.async_stop()
                sys.path.remove(temp)
