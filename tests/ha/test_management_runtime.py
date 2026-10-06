"""Native HA bulk flows/admin services; all public API responses are synthetic."""

import importlib
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from homeassistant.bootstrap import async_setup_hass
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.helpers import entity_registry as er
from homeassistant.runner import RuntimeConfig

from runtime_support import isolated_runtime, install_release


class ManagementRuntimeTest(unittest.IsolatedAsyncioTestCase):
    @isolated_runtime
    async def test_bulk_ui_partial_results_services_permissions_and_account_protection(self):
        for name in list(sys.modules):
            if name=='custom_components' or name.startswith('custom_components.'):
                del sys.modules[name]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);install_release(root)
            (root/'custom_components/__init__.py').write_text('')
            with socket.socket() as probe:
                probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
            (root/'configuration.yaml').write_text(f'homeassistant:\n  time_zone: Europe/Brussels\nhttp:\n  server_host: 127.0.0.1\n  server_port: {port}\nfrontend:\nmy_bpost:\n')
            sys.path.insert(0,temp);hass=None
            try:
                api=importlib.import_module('custom_components.my_bpost.pybpost.tracking')
                client=importlib.import_module('custom_components.my_bpost.pybpost.client')
                models=importlib.import_module('custom_components.my_bpost.pybpost.models')
                async def lookup(code,postcode):
                    if code=='MISSING':raise api.BpostTrackingNotFound('synthetic')
                    if code=='PAUSE':raise api.BpostRateLimitError(900)
                    return models.ParcelDetail(code,current_status='AT_PICKUP_POINT')
                with patch.object(api.PublicTrackingClient,'get_parcel',new=AsyncMock(side_effect=lookup)) as calls,patch.object(
                    client.BpostClient,'login',new=AsyncMock(return_value=models.AuthTokens('synthetic','refresh'))),patch.object(
                    client.BpostClient,'get_parcels_list',new=AsyncMock(return_value=[])),patch.object(
                    client.BpostClient,'get_mail_summary',new=AsyncMock(return_value={'isMMTSubscribed':False})):
                    hass=await async_setup_hass(RuntimeConfig(config_dir=temp,skip_pip=True));self.assertIsNotNone(hass)
                    await hass.async_start()
                    result=await hass.config_entries.flow.async_init('my_bpost',context={'source':'user'})
                    self.assertIn('bulk',result['menu_options'])
                    result=await hass.config_entries.flow.async_configure(result['flow_id'],{'next_step_id':'bulk'})
                    result=await hass.config_entries.flow.async_configure(result['flow_id'],{
                        'barcodes':'FIRST\nMISSING\nSECOND\nFIRST','postal_code':'1000','group':'Home','app_lang':'fr'})
                    self.assertEqual(result['reason'],'bulk_complete')
                    self.assertEqual(result['description_placeholders'],{'added':'2','existing':'1','failed':'2'})
                    await hass.async_block_till_done()
                    entries=hass.config_entries.async_entries('my_bpost')
                    self.assertEqual(len(entries),2)
                    self.assertTrue(all(e.data['group']=='Home' for e in entries))
                    counts=await hass.services.async_call('my_bpost','get_summary',{'group':'Home'},blocking=True,return_response=True)
                    self.assertEqual(counts['pickup'],2)
                    empty=await hass.services.async_call('my_bpost','get_summary',{'group':'Work'},blocking=True,return_response=True)
                    self.assertEqual(empty['parcels'],0)

                    result=await hass.services.async_call('my_bpost','track_parcels',{'parcels':[
                        {'barcode':'FIRST','postal_code':'1000'}, {'barcode':'PAUSE','postal_code':'1000'},
                        {'barcode':'AFTER-PAUSE','postal_code':'1000'}]},blocking=True,return_response=True)
                    self.assertEqual([r['status'] for r in result['results']],['already_configured','rate_limited','rate_limited'])
                    self.assertFalse(any(c.args[0]=='AFTER-PAUSE' for c in calls.call_args_list))
                    with self.assertRaises(ServiceValidationError):
                        await hass.services.async_call('my_bpost','track_parcels',{'parcels':[
                            {'barcode':'VALID','postal_code':'1000'},{'barcode':' ','postal_code':'1000'}]},blocking=True)
                    self.assertFalse(any(c.args[0]=='VALID' for c in calls.call_args_list))

                    await hass.auth.async_create_user('Synthetic owner')
                    nonadmin=await hass.auth.async_create_user('Synthetic nonadmin',group_ids=['system-users'])
                    self.assertFalse(nonadmin.is_admin)
                    with self.assertRaises(Unauthorized):
                        await hass.services.async_call('my_bpost','untrack_parcels',{'entry_ids':[entries[0].entry_id]},
                            blocking=True,context=Context(user_id=nonadmin.id))
                    result=await hass.config_entries.flow.async_init('my_bpost',context={'source':'user'},
                        data={'username':'synthetic@example.invalid','password':'synthetic'})
                    account=result['result'];await hass.async_block_till_done()
                    with self.assertRaises(ServiceValidationError):
                        await hass.services.async_call('my_bpost','untrack_parcels',{
                            'entry_ids':[entries[0].entry_id,account.entry_id]},blocking=True)
                    self.assertIsNotNone(hass.config_entries.async_get_entry(entries[0].entry_id))
                    result=await hass.services.async_call('my_bpost','untrack_parcels',{
                        'entry_ids':[e.entry_id for e in entries]},blocking=True,return_response=True)
                    self.assertEqual([r['status'] for r in result['results']],['removed','removed'])
                    result=await hass.services.async_call('my_bpost','untrack_parcels',{
                        'entry_ids':[entries[0].entry_id]},blocking=True,return_response=True)
                    self.assertEqual(result['results'][0]['status'],'not_found')
                    await hass.async_block_till_done()
                    self.assertEqual(hass.config_entries.async_entries('my_bpost'),[account])
                    self.assertFalse(any(e.config_entry_id in {x.entry_id for x in entries} for e in er.async_get(hass).entities.values()))
            finally:
                if hass is not None:await hass.async_stop()
                sys.path.remove(temp)
