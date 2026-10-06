"""Cross-source selection, grouped notifications and readable health states."""

from datetime import datetime, timezone
import importlib
import json
import sys
import unittest
from unittest.mock import AsyncMock, patch

import test_auth as auth_support


class FeatureTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        for name in list(sys.modules):
            if name == 'custom_components' or name.startswith('custom_components.'):
                del sys.modules[name]
        auth_support.AuthTest.setUpClass.__func__(cls)

    asyncSetUp = auth_support.AuthTest.asyncSetUp
    asyncTearDown = auth_support.AuthTest.asyncTearDown
    entry = auth_support.AuthTest.entry
    setup_entry = auth_support.AuthTest.setup_entry

    def parcel(self, entity='sensor.account', *, code='PRIVATE-CODE', entry='account',
               status='in_transit', source='account', fetched='2026-10-06T10:00:00Z', **attrs):
        self.hass.states.async_set(entity,status,{'integration':'my_bpost','tracking_number':code,
            'account_id':entry,'tracking_source':source,'active':True,'last_fetch':fetched,**attrs})

    def module(self,name):
        return importlib.import_module(f'custom_components.my_bpost.{name}')

    async def test_selection_available_newest_tie_and_group_filters(self):
        m=self.module('selection')
        self.parcel(parcel_group='Home')
        self.parcel('sensor.manual',entry='manual',source='public',parcel_group='Work')
        chosen=lambda: m.select_parcels(m.parcel_states(self.hass))['PRIVATE-CODE'].entity_id
        self.assertEqual(chosen(),'sensor.account')
        self.parcel('sensor.manual',entry='manual',source='public',fetched='2026-10-06T11:00:00Z')
        self.assertEqual(chosen(),'sensor.manual')
        self.parcel('sensor.manual',entry='manual',source='public',status='unavailable',fetched='2026-10-06T12:00:00Z')
        self.assertEqual(chosen(),'sensor.account')
        self.assertEqual(len(m.parcel_states(self.hass,group='Home')),1)
        self.assertEqual(len(m.parcel_states(self.hass,entry_id='manual')),1)

    async def test_summary_has_disjoint_counts_no_private_fields_and_local_day(self):
        m=self.module('selection')
        self.parcel(delivery_date='2026-10-07')
        self.parcel('sensor.copy',entry='manual',source='public',delivery_date='2026-10-07')
        self.parcel('sensor.pickup',code='PICKUP',status='at_pickup_point',delivery_date='2026-10-07')
        self.parcel('sensor.problem',code='PROBLEM',status='problem',delivery_date='2026-10-07')
        self.parcel('sensor.unavailable',code='MISSING',status='unavailable')
        with patch.object(m.dt_util,'now',return_value=datetime(2026,10,7,0,1,tzinfo=timezone.utc)):
            result=m.summary(self.hass)
        self.assertEqual({k:result[k] for k in ('today','pickup','problem','unavailable','duplicates')},
                         dict(today=1,pickup=1,problem=1,unavailable=1,duplicates=1))
        self.assertNotIn('PRIVATE',json.dumps(result))

    async def hub(self):
        hub=self.module('notifications').NotificationHub(self.hass)
        await hub.async_setup()
        self.addAsyncCleanup(hub.stop,None)
        return hub

    async def test_grouped_updates_deduplicate_and_survive_store_reload(self):
        hub=await self.hub()
        messages=[];self.hass.bus.async_listen('my_bpost_notification',messages.append)
        self.parcel();await self.hass.async_block_till_done()
        self.hass.bus.async_fire('my_bpost_status_changed',{'item_code':'PRIVATE-CODE'})
        self.hass.bus.async_fire('my_bpost_out_for_delivery',{'item_code':'PRIVATE-CODE'})
        self.parcel(status='out_for_delivery',fetched='2026-10-06T11:00:00Z')
        self.parcel('sensor.copy',source='public',status='out_for_delivery',fetched='2026-10-06T11:00:00Z')
        await self.hass.async_block_till_done()
        self.assertEqual(messages,[])
        self.assertIsNotNone(hub.timer)
        await hub.async_flush();await self.hass.async_block_till_done()
        self.assertEqual(len(messages),1)
        self.assertEqual(messages[0].data['event_type'],'my_bpost_out_for_delivery')
        self.assertEqual(messages[0].data['entry_id'],'account')
        await hub.stop(None)
        stored=await hub.store.async_load()
        self.assertNotIn('PRIVATE-CODE',json.dumps(stored))
        restarted=await self.hub()
        self.hass.bus.async_fire('my_bpost_out_for_delivery',{'item_code':'PRIVATE-CODE'})
        await self.hass.async_block_till_done();await restarted.async_flush()
        await self.hass.async_block_till_done();self.assertEqual(len(messages),1)

    async def test_eta_accumulates_small_changes_until_configured_threshold(self):
        hub=await self.hub();messages=[]
        self.hass.bus.async_listen('my_bpost_notification',messages.append)
        entry=await self.entry()
        self.hass.config_entries.async_update_entry(entry,options={'eta_change_minutes':30})
        self.parcel(entry=entry.entry_id,delivery_date='2026-10-07',delivery_window_start='10:00',delivery_window_end='12:00')
        await self.hass.async_block_till_done()
        for start,end,expected in [('10:20','12:20',0),('10:40','12:40',1),('10:50','12:50',1)]:
            self.hass.bus.async_fire('my_bpost_eta_changed',{'item_code':'PRIVATE-CODE'})
            self.parcel(entry=entry.entry_id,delivery_date='2026-10-07',delivery_window_start=start,delivery_window_end=end)
            await self.hass.async_block_till_done();await hub.async_flush();await self.hass.async_block_till_done()
            self.assertEqual(len(messages),expected)
        self.assertEqual(messages[0].data['eta_shift_minutes'],40)

    async def test_coalescing_uses_final_selected_status_and_healthy_fallback(self):
        hub=await self.hub();messages=[]
        self.hass.bus.async_listen('my_bpost_notification',messages.append)
        self.parcel();await self.hass.async_block_till_done()
        for kind in ('out_for_delivery','delivered'):
            self.hass.bus.async_fire('my_bpost_'+kind,{'item_code':'PRIVATE-CODE'})
        self.parcel(status='unavailable')
        self.parcel('sensor.manual',source='public',entry='manual',status='delivered')
        await self.hass.async_block_till_done();await hub.async_flush();await self.hass.async_block_till_done()
        self.assertEqual(len(messages),1)
        self.assertEqual(messages[0].data['event_type'],'my_bpost_delivered')
        self.assertEqual(messages[0].data['entry_id'],'manual')

    async def test_late_eta_establishes_baseline_then_detects_day_change(self):
        hub=await self.hub();messages=[]
        self.hass.bus.async_listen('my_bpost_notification',messages.append)
        self.parcel(fetched=None);await self.hass.async_block_till_done()
        for day, expected in [('2026-10-07',0),('2026-10-08',1)]:
            if expected:
                self.hass.bus.async_fire('my_bpost_eta_changed',{'item_code':'PRIVATE-CODE'})
            self.parcel(delivery_date=day)
            await self.hass.async_block_till_done();await hub.async_flush();await self.hass.async_block_till_done()
            self.assertEqual(len(messages),expected)
        self.assertEqual(messages[0].data['eta_shift_minutes'],1440)

    async def test_late_time_window_is_seeded_without_losing_subsequent_shift(self):
        hub=await self.hub();messages=[]
        self.hass.bus.async_listen('my_bpost_notification',messages.append)
        self.parcel(delivery_date='2026-10-07');await self.hass.async_block_till_done()
        for start, expected in [('10:00',0),('10:40',1)]:
            self.hass.bus.async_fire('my_bpost_eta_changed',{'item_code':'PRIVATE-CODE'})
            self.parcel(delivery_date='2026-10-07',delivery_window_start=start)
            await self.hass.async_block_till_done();await hub.async_flush();await self.hass.async_block_till_done()
            self.assertEqual(len(messages),expected)

    async def test_health_distinguishes_failures_and_recovers_without_disappearing(self):
        entry=await self.entry();coordinator=await self.setup_entry(entry)
        sensor=self.sensor_module.BpostHealthSensor(coordinator,entry)
        errors=self.module('pybpost.exceptions')
        for error,expected in [(errors.BpostRateLimitError(600),'rate_limited'),(errors.BpostMaintenanceError(),'maintenance'),
                (errors.BpostForceUpdateError(),'outdated_client'),(errors.BpostAuthError(),'auth_required'),(errors.BpostApiError(),'service_unavailable')]:
            with patch.object(coordinator,'_async_fetch_data',new=AsyncMock(side_effect=error)), patch.object(
                    type(entry),'async_start_reauth') as reauth:
                await coordinator.async_refresh()
                self.assertEqual(reauth.call_count,1 if expected=='auth_required' else 0)
            self.assertTrue(sensor.available);self.assertEqual(sensor.native_value,expected)
            self.assertEqual(sensor.extra_state_attributes['retry_at'] is not None,expected=='rate_limited')
        with patch.object(coordinator,'_async_fetch_data',new=AsyncMock(return_value=coordinator.data)):
            await coordinator.async_refresh()
        self.assertEqual(sensor.native_value,'ok');self.assertIsNone(sensor.extra_state_attributes['retry_at'])
