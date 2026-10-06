"""Blueprints through HA's parser, automation engine and native mobile action.

Only the final notify service is a local sink: no phone receives test messages.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
import tempfile
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from homeassistant import loader
from homeassistant.config_entries import ConfigEntry, ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util


class BlueprintTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        for name in list(sys.modules):
            if name == 'custom_components' or name.startswith('custom_components.'):
                del sys.modules[name]
        self.config = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parents[2]
        shutil.copytree(root/'blueprints',Path(self.config.name)/'blueprints')
        package = Path(self.config.name)/'custom_components'
        shutil.copytree(root/'custom_components',package)
        shutil.copytree(root/'pybpost/pybpost',package/'my_bpost/pybpost')
        (package/'__init__.py').write_text('')
        sys.path.insert(0,self.config.name)
        self.addCleanup(sys.path.remove,self.config.name)
        self.hass = HomeAssistant(self.config.name)
        # Dependencies used by the native action are pinned in requirements-dev.
        # Do not let HA install unrelated after_dependencies (Matter, etc.) in tests.
        self.hass.config.skip_pip = True
        await self.hass.config.async_set_time_zone('Europe/Brussels')
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass,{})
        await self.hass.config_entries.async_initialize()
        await dr.async_get(self.hass).async_load()
        await er.async_get(self.hass).async_load()
        self.account = await self.entry('my_bpost')
        self.account_device = dr.async_get(self.hass).async_get_or_create(
            config_entry_id=self.account.entry_id,identifiers={('my_bpost',self.account.entry_id)})
        mobile = await self.entry('mobile_app')
        self.phone = dr.async_get(self.hass).async_get_or_create(
            config_entry_id=mobile.entry_id,identifiers={('mobile_app','synthetic-phone')})
        from homeassistant.components.mobile_app.const import DATA_DEVICES, DATA_NOTIFY
        self.hass.data['mobile_app'] = {
            DATA_DEVICES: {'synthetic-webhook':self.phone},
            DATA_NOTIFY: SimpleNamespace(registered_targets={'blueprint_sink':'synthetic-webhook'}),
        }
        self.messages = []
        async def capture(call): self.messages.append(dict(call.data))
        self.hass.services.async_register('notify','blueprint_sink',capture)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.config.cleanup()

    async def entry(self,domain):
        entry = ConfigEntry(version=1,minor_version=1,domain=domain,title='Synthetic',source='user',
            unique_id=None,data={},options={},discovery_keys=MappingProxyType({}),subentries_data=None)
        with patch.object(self.hass.config_entries,'async_setup',new=AsyncMock(return_value=True)):
            await self.hass.config_entries.async_add(entry)
        return entry

    async def setup_automation(self,kind='parcel',**inputs):
        defaults={'notify_device':self.phone.id}
        if kind!='daily':defaults['account_device']=self.account_device.id
        config = {'id':'test-notification','alias':'Blueprint test','use_blueprint':{
            'path':f'my_bpost/{kind}_notifications.yaml',
            'input':{**defaults,**inputs}}}
        from homeassistant.components.automation.config import _async_validate_config_item
        await _async_validate_config_item(self.hass,config,True,True)
        self.assertTrue(await async_setup_component(self.hass,'automation',{'automation':[config]}))
        await self.hass.async_start()
        await self.hass.async_block_till_done()
        self.assertEqual(self.hass.states.get('automation.blueprint_test').state,'on')

    async def fire(self,event='my_bpost_delivered',**data):
        payload = {'entry_id':self.account.entry_id,'parcel_id':'opaque-parcel-key','mail_id':'opaque-mail-key',
            'item_code':'PRIVATE-TRACKING','sender':'PRIVATE-SENDER','direction':'incoming',**data}
        if event != 'my_bpost_letter_announced':
            payload['event_type'] = event
            event = 'my_bpost_notification'
        self.hass.bus.async_fire(event,payload)
        await self.hass.async_block_till_done()

    async def test_parcel_account_direction_privacy_and_notification_replacement(self):
        await self.setup_automation(direction='incoming',dashboard_path='/lovelace/deliveries')
        await self.fire(entry_id='another-account')
        await self.fire(direction='outgoing')
        await self.fire('my_bpost_new_package')  # Not selected by default.
        self.assertEqual(self.messages,[])
        await self.fire('my_bpost_at_pickup_point')
        self.assertEqual(len(self.messages),1)
        message = self.messages[-1]
        self.assertIn('disponible au retrait',message['message'])
        self.assertNotIn('PRIVATE',str(message))
        self.assertEqual(message['data']['url'],'/lovelace/deliveries')
        self.assertEqual(message['data']['clickAction'],'/lovelace/deliveries')
        await self.fire()
        self.assertEqual(len(self.messages),2)
        self.assertEqual(self.messages[0]['data']['tag'],self.messages[1]['data']['tag'])
        await self.fire(parcel_id='other-opaque-key')
        self.assertNotEqual(self.messages[-1]['data']['tag'],self.messages[0]['data']['tag'])

    async def test_eta_details_and_selected_event_language(self):
        await self.setup_automation(events=['my_bpost_eta_changed'],language='en',include_details=True)
        await self.fire()  # Delivered was not selected.
        self.assertEqual(self.messages,[])
        await self.fire('my_bpost_eta_changed',new_eta=['2026-10-07','12:00','14:00'])
        self.assertEqual(len(self.messages),1)
        text = self.messages[0]['message']
        for value in ('delivery window changed','PRIVATE-TRACKING','2026-10-07','12:00'):
            self.assertIn(value,text)
        self.assertNotIn('PRIVATE-SENDER',text)

    async def test_quiet_hours_cross_midnight_and_boundaries(self):
        await self.setup_automation(quiet_enabled=True,quiet_start='22:00:00',quiet_end='07:00:00')
        for hour,minute,expected in [(21,59,1),(22,0,1),(23,0,1),(0,0,1),(6,59,1),(7,0,2)]:
            # Brussels is UTC+2 on this date; pin actual HA now() rather than a copy of the template.
            local = datetime(2026,10,6,hour,minute,tzinfo=dt_util.get_time_zone('Europe/Brussels'))
            with patch('homeassistant.util.dt.now',return_value=local), patch('homeassistant.util.dt.utcnow',return_value=local.astimezone(timezone.utc)):
                await self.fire()
            self.assertEqual(len(self.messages),expected,(hour,minute))

    async def test_daytime_quiet_hours_and_equal_times(self):
        await self.setup_automation(quiet_enabled=True,quiet_start='12:00:00',quiet_end='14:00:00')
        for hour,expected in [(11,1),(12,1),(13,1),(14,2)]:
            local = datetime(2026,10,6,hour,tzinfo=dt_util.get_time_zone('Europe/Brussels'))
            with patch('homeassistant.util.dt.now',return_value=local), patch('homeassistant.util.dt.utcnow',return_value=local.astimezone(timezone.utc)):
                await self.fire()
            self.assertEqual(len(self.messages),expected)

    async def test_mail_blueprint_filters_account_and_sends_no_scan_links(self):
        await self.setup_automation(kind='mail',language='nl',quiet_enabled=True,quiet_start='07:00:00',quiet_end='07:00:00')
        await self.fire('my_bpost_letter_announced',entry_id='other')
        self.assertEqual(self.messages,[])
        await self.fire('my_bpost_letter_announced',image_url='https://example.invalid/private-signed-image')
        self.assertEqual(len(self.messages),1)
        self.assertIn('nieuwe brief',self.messages[0]['message'])
        self.assertNotIn('private-signed-image',str(self.messages[0]))
        self.assertNotIn('PRIVATE',str(self.messages[0]))
        self.assertIn('opaque-mail-key',self.messages[0]['data']['tag'])

    async def test_daily_summary_deduplicates_and_sends_no_personal_fields(self):
        import importlib
        services=importlib.import_module('custom_components.my_bpost.services')
        services.async_register_services(self.hass)
        for entity in ('sensor.one','sensor.duplicate'):
            self.hass.states.async_set(entity,'at_pickup_point',{'integration':'my_bpost',
                'tracking_number':'PRIVATE-CODE','account_id':self.account.entry_id,
                'friendly_name':'PRIVATE-NAME','active':True})
        await self.setup_automation(kind='daily',language='fr')
        await self.hass.services.async_call('automation','trigger',{'entity_id':'automation.blueprint_test'},blocking=True)
        await self.hass.async_block_till_done()
        self.assertEqual(len(self.messages),1)
        self.assertIn('À retirer: 1',self.messages[0]['message'])
        self.assertNotIn('PRIVATE',str(self.messages[0]))

    async def test_raw_updates_reach_one_all_sources_notification_through_timer(self):
        import importlib
        notifications=importlib.import_module('custom_components.my_bpost.notifications')
        hub=notifications.NotificationHub(self.hass)
        await hub.async_setup()
        await self.setup_automation(all_sources=True)
        attrs={'integration':'my_bpost','tracking_number':'PRIVATE-CODE',
               'account_id':'other-source','active':True,'user_type':'RECEIVER'}
        self.hass.states.async_set('sensor.parcel','in_transit',attrs)
        await self.hass.async_block_till_done()
        sent=asyncio.Event()
        async def capture(call):
            self.messages.append(dict(call.data))
            sent.set()
        self.hass.services.async_register('notify','blueprint_sink',capture)
        with patch.object(notifications,'WINDOW_SECONDS',0.01):
            for event in ('status_changed','out_for_delivery','delivered'):
                self.hass.bus.async_fire('my_bpost_'+event,{'item_code':'PRIVATE-CODE'})
            self.hass.states.async_set('sensor.parcel','delivered',attrs)
            self.hass.states.async_set('sensor.duplicate','delivered',{**attrs,'tracking_source':'public'})
            await asyncio.wait_for(sent.wait(),timeout=5)
            await self.hass.async_block_till_done()
        self.assertEqual(len(self.messages),1)
        self.assertIn('livré',self.messages[0]['message'])
        self.assertNotIn('PRIVATE',str(self.messages[0]))

    async def test_pickup_reminder_is_silent_without_ready_to_collect_parcels(self):
        import importlib
        importlib.import_module('custom_components.my_bpost.services').async_register_services(self.hass)
        await self.setup_automation(kind='daily',pickup_only=True)
        await self.hass.services.async_call('automation','trigger',{'entity_id':'automation.blueprint_test'},blocking=True)
        await self.hass.async_block_till_done()
        self.assertEqual(self.messages,[])
