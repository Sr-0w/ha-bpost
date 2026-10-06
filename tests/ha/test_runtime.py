"""Real HA runtime/platform lifecycle with a synthetic delivery backend."""

import importlib
from datetime import timedelta
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from homeassistant.bootstrap import async_setup_hass
from runtime_support import isolated_runtime, install_release, assert_coordinators_stopped
from homeassistant.config_entries import ConfigEntryState
from homeassistant.runner import RuntimeConfig
from homeassistant.util import dt as dt_util


class RuntimeTest(unittest.IsolatedAsyncioTestCase):
    @isolated_runtime
    async def test_delivery_entities_live_expiry_and_reload(self):
        # Other suites use a different release staging directory.
        for name in list(sys.modules):
            if name == 'custom_components' or name.startswith('custom_components.'):
                del sys.modules[name]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = Path(__file__).resolve().parents[2]
            install_release(root)
            (root / 'custom_components/__init__.py').write_text('')
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            (root / 'configuration.yaml').write_text(
                f'homeassistant:\n  time_zone: Europe/Paris\nhttp:\n  server_host: 127.0.0.1\n  server_port: {port}\nfrontend:\nmy_bpost:\n')
            sys.path.insert(0, temp)
            hass = None
            try:
                client_module = importlib.import_module('custom_components.my_bpost.pybpost.client')
                models = importlib.import_module('custom_components.my_bpost.pybpost.models')
                live_module = importlib.import_module('custom_components.my_bpost.live')
                summary = models.ParcelSummary('synthetic-parcel', 'OUT_FOR_DELIVERY')
                detail = models.ParcelDetail('synthetic-parcel', current_status='OUT_FOR_DELIVERY',
                    user_type='RECEIVER', receiver=models.Person(postcode='1000'),
                    delivery_point=models.DeliveryPoint(name='Synthetic pickup', latitude=51, longitude=5))
                tomorrow = dt_util.now().date() + timedelta(days=1)
                detail.eta = models.Eta(tomorrow.isoformat(), '10:00', '12:00')
                live = models.LiveRoundStatus(stops_until_target=0, eta_window='14:00–15:00',
                                              last_known_lat=50.85, last_known_lon=4.35)
                with patch.object(client_module.BpostClient, 'login', new=AsyncMock(return_value=models.AuthTokens('synthetic', 'synthetic-refresh'))), patch.object(
                    client_module.BpostClient, 'get_parcels_list', new=AsyncMock(return_value=[summary])), patch.object(
                    client_module.BpostClient, 'get_parcels_details', new=AsyncMock(return_value=([detail], []))) as details, patch.object(
                    client_module.BpostClient, 'get_live_status', new=AsyncMock(return_value=live)), patch.object(
                    live_module, 'monotonic', return_value=100) as clock, patch.object(
                    client_module.BpostClient, 'get_mail_summary', new=AsyncMock(return_value={'isMMTSubscribed': False})):
                    hass = await async_setup_hass(RuntimeConfig(config_dir=temp, skip_pip=True))
                    self.assertIsNotNone(hass)
                    await hass.async_start()
                    delivered = []
                    hass.bus.async_listen('my_bpost_delivered', delivered.append)
                    result = await hass.config_entries.flow.async_init('my_bpost', context={'source': 'user'},
                        data={'username': 'synthetic@example.invalid', 'password': 'synthetic'})
                    self.assertEqual(result['type'], 'create_entry')
                    entry = result['result']
                    await hass.async_block_till_done()
                    self.assertEqual(entry.state, ConfigEntryState.LOADED)
                    self.assertNotIn('password', entry.data)
                    states = [s for s in hass.states.async_all() if s.attributes.get('integration') == 'my_bpost']
                    parcel = next(s for s in states if s.domain == 'sensor' and s.attributes.get('tracking_number'))
                    courier = next(s for s in states if s.attributes.get('location_kind') == 'courier')
                    pickup = next(s for s in states if s.attributes.get('location_kind') == 'pickup')
                    self.assertEqual(parcel.state, 'out_for_delivery')
                    self.assertEqual(parcel.attributes['stops_remaining'], 0)
                    self.assertEqual(courier.attributes['latitude'], 50.85)
                    self.assertEqual(pickup.attributes['latitude'], 51)
                    self.assertEqual(delivered, [])
                    calendar = next(s for s in hass.states.async_all() if s.domain == 'calendar')
                    response = await hass.services.async_call('calendar', 'get_events', {
                        'entity_id': calendar.entity_id, 'start_date_time': tomorrow.isoformat(),
                        'end_date_time': (tomorrow + timedelta(days=1)).isoformat(),
                    }, blocking=True, return_response=True)
                    self.assertEqual(len(response[calendar.entity_id]['events']), 1)
                    self.assertIn('T10:00:00', response[calendar.entity_id]['events'][0]['start'])
                    from homeassistant.helpers import device_registry as dr
                    from homeassistant.components.device_automation import async_get_device_automations, DeviceAutomationType
                    device = dr.async_get(hass).async_get_device(identifiers={('my_bpost', entry.entry_id)})
                    automations = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, [device.id])
                    triggers = [trigger for trigger in automations[device.id] if trigger['domain'] == 'my_bpost']
                    self.assertEqual(len(triggers), 9)

                    # Expire an observation without another successful response.
                    clock.return_value = 221
                    entry.runtime_data.live.async_update_listeners()
                    await hass.async_block_till_done()
                    self.assertEqual(hass.states.get(courier.entity_id).state, 'unavailable')
                    self.assertNotIn('latitude', hass.states.get(courier.entity_id).attributes)
                    self.assertFalse(hass.states.get(parcel.entity_id).attributes['live_available'])
                    self.assertNotEqual(hass.states.get(pickup.entity_id).state, 'unavailable')

                    detail.current_status = 'DELIVERED'
                    details.return_value = ([], [detail])
                    await entry.runtime_data.async_refresh()
                    await hass.async_block_till_done()
                    self.assertEqual(hass.states.get(parcel.entity_id).state, 'delivered')
                    self.assertEqual(len(delivered), 1)
                    self.assertNotIn('start_time', hass.states.get(calendar.entity_id).attributes)
                    previous = entry.runtime_data
                    self.assertTrue(await hass.config_entries.async_reload(entry.entry_id))
                    await hass.async_block_till_done()
                    await assert_coordinators_stopped(self, previous)
                    self.assertIsNot(previous, entry.runtime_data)
                    self.assertFalse(previous.client._session.closed)  # Shared HA session.
                    self.assertEqual(entry.state, ConfigEntryState.LOADED)
                    self.assertEqual(hass.states.get(parcel.entity_id).state, 'delivered')
                    self.assertEqual(len(delivered), 1)

                    # Simulate expiry and verify platform removal, then a restart:
                    # history must not recreate expired sensors or either tracker.
                    entry.runtime_data._inactive_since['synthetic-parcel'] = (dt_util.utcnow() - timedelta(days=8)).timestamp()
                    await entry.runtime_data.async_refresh()
                    await hass.async_block_till_done()
                    from homeassistant.helpers import entity_registry as er
                    registry = er.async_get(hass)
                    for entity_id in (parcel.entity_id, courier.entity_id, pickup.entity_id):
                        self.assertIsNone(hass.states.get(entity_id))
                        self.assertIsNone(registry.async_get(entity_id))
                    self.assertIsNotNone(hass.states.get(calendar.entity_id))
                    self.assertTrue(await hass.config_entries.async_reload(entry.entry_id))
                    await hass.async_block_till_done()
                    self.assertFalse(any(s.attributes.get('tracking_number') for s in hass.states.async_all()))

                    # A backend reactivation can create entities again, in this
                    # same running platform (known-code sets must be pruned).
                    detail.current_status = 'OUT_FOR_DELIVERY'
                    details.return_value = ([detail], [])
                    await entry.runtime_data.async_refresh()
                    await hass.async_block_till_done()
                    restored = [s for s in hass.states.async_all() if s.domain == 'sensor' and s.attributes.get('tracking_number')]
                    self.assertEqual(len(restored), 1)
                    self.assertEqual(restored[0].state, 'out_for_delivery')
                    details.return_value = ([], [detail])
                    entry.runtime_data._inactive_since['synthetic-parcel'] = (dt_util.utcnow() - timedelta(days=8)).timestamp()
                    await entry.runtime_data.async_refresh()
                    await hass.async_block_till_done()
                    self.assertIsNone(hass.states.get(restored[0].entity_id))
                    details.return_value = ([detail], [])
                    await entry.runtime_data.async_refresh()
                    await hass.async_block_till_done()
                    self.assertEqual(hass.states.get(restored[0].entity_id).state, 'out_for_delivery')
            finally:
                if hass is not None:
                    await hass.async_stop()
                sys.path.remove(temp)
