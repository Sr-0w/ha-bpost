"""Real HA mail entities, protected image proxy and reload lifecycle."""

import base64
from datetime import datetime
from zoneinfo import ZoneInfo
import importlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import aiohttp
from homeassistant.bootstrap import async_setup_hass
from runtime_support import isolated_runtime, install_release, assert_coordinators_stopped
from homeassistant.config_entries import ConfigEntryState
from homeassistant.runner import RuntimeConfig
from homeassistant.helpers import entity_registry as er

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=')


class MailRuntimeTest(unittest.IsolatedAsyncioTestCase):
    @isolated_runtime
    async def test_mail_proxy_privacy_events_reload_removal_and_opt_out(self):
        for name in list(sys.modules):
            if name == 'custom_components' or name.startswith('custom_components.'):
                del sys.modules[name]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = Path(__file__).resolve().parents[2]
            install_release(root)
            (root/'custom_components/__init__.py').write_text('')
            with socket.socket() as probe:
                probe.bind(('127.0.0.1',0))
                port = probe.getsockname()[1]
            (root/'configuration.yaml').write_text(
                f'homeassistant:\n  time_zone: Europe/Brussels\nhttp:\n  server_host: 127.0.0.1\n  server_port: {port}\nfrontend:\nmy_bpost:\n')
            sys.path.insert(0,temp)
            hass = None
            try:
                client_module = importlib.import_module('custom_components.my_bpost.pybpost.client')
                models = importlib.import_module('custom_components.my_bpost.pybpost.models')
                mail_models = importlib.import_module('custom_components.my_bpost.pybpost.mail')
                first = mail_models.MailItem('private-letter-one',datetime.now(ZoneInfo('Europe/Brussels')).date(),sender='private-sender',
                    image_url='https://scan.bpost.be/one?sig=private-signature',image_ref='private-reference')
                second = mail_models.MailItem('private-letter-two',datetime.now(ZoneInfo('Europe/Brussels')).date(),image_url='https://scan.bpost.be/two?sig=private-two')
                with patch.object(client_module.BpostClient,'login',new=AsyncMock(return_value=models.AuthTokens('synthetic','synthetic-refresh'))), patch.object(
                    client_module.BpostClient,'get_parcels_list',new=AsyncMock(return_value=[])), patch.object(
                    client_module.BpostClient,'get_mail_summary',new=AsyncMock(return_value={'isMMTSubscribed':True})) as summary, patch.object(
                    client_module.BpostClient,'get_letters',new=AsyncMock(return_value=[first])) as letters, patch.object(
                    client_module.BpostClient,'get_mail_image',new=AsyncMock(return_value=(PNG,'image/png'))) as scan:
                    hass = await async_setup_hass(RuntimeConfig(config_dir=temp,skip_pip=True))
                    self.assertIsNotNone(hass)
                    await hass.async_start()
                    announced = []
                    hass.bus.async_listen('my_bpost_letter_announced',announced.append)
                    result = await hass.config_entries.flow.async_init('my_bpost',context={'source':'user'},
                        data={'username':'synthetic@example.invalid','password':'synthetic'})
                    entry = result['result']
                    await hass.async_block_till_done()
                    self.assertEqual(entry.state,ConfigEntryState.LOADED)
                    self.assertEqual(announced,[])
                    self.assertEqual(hass.states.async_all('image'),[])
                    scan.assert_not_awaited()
                    registry = er.async_get(hass)
                    count_id = registry.async_get_entity_id('sensor','my_bpost',f'{entry.entry_id}_mail_count')
                    status_id = registry.async_get_entity_id('sensor','my_bpost',f'{entry.entry_id}_mail_status')
                    self.assertEqual(hass.states.get(count_id).state,'1')
                    self.assertEqual(hass.states.get(status_id).state,'available')

                    # Enabling images reloads the entry but does not download scans.
                    previous = entry.runtime_data
                    hass.config_entries.async_update_entry(entry,options={'enable_mail_images':True})
                    await hass.async_block_till_done()
                    await assert_coordinators_stopped(self, previous)
                    self.assertEqual(entry.state,ConfigEntryState.LOADED)
                    image_state = hass.states.async_all('image')[0]
                    scan.assert_not_awaited()
                    self.assertEqual(announced,[])
                    for state in hass.states.async_all():
                        serialized = json.dumps(dict(state.attributes))
                        for private in ('private-letter','private-signature','private-reference','private-sender','scan.bpost.be'):
                            self.assertNotIn(private,serialized)
                    async with aiohttp.ClientSession() as session:
                        base = f'http://127.0.0.1:{port}'
                        async with session.get(base+f'/api/image_proxy/{image_state.entity_id}') as response:
                            self.assertEqual(response.status,403)
                        scan.assert_not_awaited()
                        async with session.get(base+image_state.attributes['entity_picture']) as response:
                            self.assertEqual(response.status,200)
                            self.assertEqual(response.content_type,'image/png')
                            self.assertEqual(await response.read(),PNG)
                        scan.assert_awaited_once()
                        async with session.get(base+image_state.attributes['entity_picture']) as response:
                            self.assertEqual(response.status,200)
                        scan.assert_awaited_once()

                    # A letter arrives while the entry is unloaded. Its saved
                    # baseline must be loaded before the first new mail poll.
                    previous = entry.runtime_data
                    self.assertTrue(await hass.config_entries.async_unload(entry.entry_id))
                    await assert_coordinators_stopped(self, previous)
                    letters.return_value = [first,second]
                    self.assertTrue(await hass.config_entries.async_setup(entry.entry_id))
                    await hass.async_block_till_done()
                    self.assertEqual(hass.states.get(count_id).state,'2')
                    self.assertEqual(len(announced),1)
                    self.assertEqual(len(hass.states.async_all('image')),2)
                    self.assertTrue(await hass.config_entries.async_reload(entry.entry_id))
                    await hass.async_block_till_done()
                    self.assertEqual(len(announced),1)
                    self.assertEqual(len(hass.states.async_all('image')),2)

                    # An outage keeps identity but never serves stale cached scans.
                    summary.side_effect = client_module.BpostApiError()
                    await entry.runtime_data.mail.async_refresh()
                    await hass.async_block_till_done()
                    self.assertEqual(hass.states.get(count_id).state,'unavailable')
                    self.assertTrue(all(state.state == 'unavailable' for state in hass.states.async_all('image')))
                    from homeassistant.components.image import async_get_image
                    from homeassistant.exceptions import HomeAssistantError
                    with self.assertRaises(HomeAssistantError):
                        await async_get_image(hass,image_state.entity_id)
                    summary.side_effect = None
                    letters.return_value = [second]
                    await entry.runtime_data.mail.async_refresh()
                    await hass.async_block_till_done()
                    self.assertIsNone(hass.states.get(image_state.entity_id))
                    self.assertIsNone(registry.async_get(image_state.entity_id))
                    self.assertEqual(hass.states.get(count_id).state,'1')
                    letters.return_value = [first,second]
                    await entry.runtime_data.mail.async_refresh()
                    await hass.async_block_till_done()
                    self.assertEqual(len(hass.states.async_all('image')),2)
                    self.assertEqual(len(announced),1)

                    # Opt-out removes the image registry entries as well as states.
                    hass.config_entries.async_update_entry(entry,options={'enable_mail':False,'enable_mail_images':False})
                    await hass.async_block_till_done()
                    self.assertEqual(hass.states.get(status_id).state,'disabled')
                    self.assertEqual(hass.states.get(count_id).state,'unavailable')
                    self.assertEqual(hass.states.async_all('image'),[])
                    self.assertFalse(any(e.domain == 'image' for e in er.async_entries_for_config_entry(registry,entry.entry_id)))
            finally:
                if hass is not None:
                    await hass.async_stop()
                sys.path.remove(temp)
