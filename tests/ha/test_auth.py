"""Test the release layout against real Home Assistant entry/flow objects.

The integration and client are staged outside the checkout, as in a release.
Only HTTP calls and platform forwarding are replaced with synthetic results.
"""

import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import AsyncMock, Mock, patch

from homeassistant import loader
from homeassistant.config_entries import ConfigEntry, ConfigEntries, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed


class AuthTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.stage = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.stage.cleanup)
        root = Path(__file__).resolve().parents[2]
        package = Path(cls.stage.name) / 'custom_components'
        package.mkdir()
        (package / '__init__.py').write_text('')
        shutil.copytree(root / 'custom_components/my_bpost', package / 'my_bpost')
        shutil.copytree(root / 'pybpost/pybpost', package / 'my_bpost/pybpost')
        sys.path.insert(0, cls.stage.name)
        cls.addClassCleanup(sys.path.remove, cls.stage.name)
        cls.integration = importlib.import_module('custom_components.my_bpost')
        cls.flow_module = importlib.import_module('custom_components.my_bpost.config_flow')
        cls.diagnostics = importlib.import_module('custom_components.my_bpost.diagnostics')
        cls.client_module = importlib.import_module('custom_components.my_bpost.pybpost.client')
        cls.models = importlib.import_module('custom_components.my_bpost.pybpost.models')
        cls.coordinator_module = importlib.import_module('custom_components.my_bpost.coordinator')
        cls.live_module = importlib.import_module('custom_components.my_bpost.live')
        cls.sensor_module = importlib.import_module('custom_components.my_bpost.sensor')
        cls.tracker_module = importlib.import_module('custom_components.my_bpost.device_tracker')

    async def asyncSetUp(self):
        self.config = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.config.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        await self.hass.config_entries.async_initialize()
        from homeassistant.helpers import entity_registry as er, device_registry as dr
        await er.async_get(self.hass).async_load()
        await dr.async_get(self.hass).async_load()
        self.session_patch = patch('homeassistant.helpers.aiohttp_client.async_get_clientsession', return_value=object())
        self.session_patch.start()
        # config_flow imports the helper at module load.
        self.flow_session_patch = patch.object(self.flow_module, 'async_get_clientsession', return_value=object())
        self.flow_session_patch.start()
        self.mail_patch = patch.object(self.client_module.BpostClient, 'get_mail_summary', new=AsyncMock(return_value={'isMMTSubscribed': False}))
        self.mail_patch.start()

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.mail_patch.stop()
        self.session_patch.stop()
        self.flow_session_patch.stop()
        self.config.cleanup()

    async def entry(self, *, version=2, data=None):
        entry = ConfigEntry(
            version=version, minor_version=1, domain='my_bpost',
            title='My bpost', source='user', unique_id='fiction@example.invalid',
            data=data if data is not None else {
                'username': 'fiction@example.invalid', 'app_lang': 'fr',
                'access_token': 'old-access', 'refresh_token': 'old-refresh'},
            options={}, discovery_keys=MappingProxyType({}), subentries_data=None,
        )
        with patch.object(self.hass.config_entries, 'async_setup', new=AsyncMock(return_value=True)):
            await self.hass.config_entries.async_add(entry)
        return entry

    def flow(self, *, entry=None):
        flow = self.flow_module.BpostConfigFlow()
        flow.hass = self.hass
        flow.handler = 'my_bpost'
        flow.flow_id = 'synthetic-flow'
        flow.context = {'source': 'user'} if entry is None else {
            'source': 'reauth', 'entry_id': entry.entry_id}
        return flow

    async def test_new_entry_stores_tokens_only(self):
        flow = self.flow()
        with patch.object(self.client_module.BpostClient, 'login', new=AsyncMock(
            return_value=self.models.AuthTokens('new-access', 'new-refresh'))):
            result = await flow.async_step_user({
                'username': 'fiction@example.invalid', 'password': 'synthetic-password'})
        self.assertEqual(result['type'], 'create_entry')
        self.assertEqual(result['version'], 2)
        self.assertEqual(result['data']['refresh_token'], 'new-refresh')
        self.assertNotIn('password', result['data'])

    async def test_flow_distinguishes_auth_and_outage(self):
        for error, expected in ((self.client_module.BpostAuthError, 'invalid_auth'),
                                (self.client_module.BpostApiError, 'cannot_connect')):
            with self.subTest(error=error.__name__):
                with patch.object(self.client_module.BpostClient, 'login', new=AsyncMock(side_effect=error)):
                    result = await self.flow().async_step_user({
                        'username': 'fiction@example.invalid', 'password': 'synthetic-password'})
                self.assertEqual(result['errors']['base'], expected)

    async def test_reauth_replaces_tokens_and_removes_legacy_password(self):
        entry = await self.entry(data={'username': 'fiction@example.invalid', 'password': 'legacy-secret'})
        flow = self.flow(entry=entry)
        with patch.object(self.client_module.BpostClient, 'login', new=AsyncMock(
            return_value=self.models.AuthTokens('new-access', 'new-refresh'))), patch.object(
                self.hass.config_entries, 'async_schedule_reload') as reload:
            result = await flow.async_step_reauth_confirm({'password': 'synthetic-password'})
        self.assertEqual(result['reason'], 'reauth_successful')
        self.assertNotIn('password', entry.data)
        self.assertEqual(entry.data['access_token'], 'new-access')
        reload.assert_called_once_with(entry.entry_id)

    async def test_reauth_outage_preserves_previous_tokens(self):
        entry = await self.entry()
        before = dict(entry.data)
        with patch.object(self.client_module.BpostClient, 'login', new=AsyncMock(
            side_effect=self.client_module.BpostApiError)):
            result = await self.flow(entry=entry).async_step_reauth_confirm({'password': 'synthetic-password'})
        self.assertEqual(result['errors']['base'], 'cannot_connect')
        self.assertEqual(dict(entry.data), before)

    async def test_migration_is_local_preserves_entry_and_options(self):
        entry = await self.entry(version=1, data={
            'username': 'fiction@example.invalid', 'password': 'legacy-secret', 'app_lang': 'nl'})
        original_id = entry.entry_id
        self.hass.config_entries.async_update_entry(entry, options={'retention_days': 14})
        with patch.object(self.client_module.BpostClient, 'login', new=AsyncMock()) as login:
            self.assertTrue(await self.integration.async_migrate_entry(self.hass, entry))
        login.assert_not_awaited()
        self.assertEqual(entry.version, 2)
        self.assertEqual(entry.entry_id, original_id)
        self.assertEqual(entry.options['retention_days'], 14)
        self.assertNotIn('password', entry.data)
        with self.assertRaises(ConfigEntryAuthFailed):
            await self.integration.async_setup_entry(self.hass, entry)

    async def test_future_migration_is_rejected(self):
        entry = await self.entry(version=3)
        self.assertFalse(await self.integration.async_migrate_entry(self.hass, entry))

    async def setup_entry(self, entry):
        entry._async_set_state(self.hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
        with patch.object(self.client_module.BpostClient, 'get_parcels_list', new=AsyncMock(return_value=[])), patch.object(
            self.hass.config_entries, 'async_forward_entry_setups', new=AsyncMock()):
            self.assertTrue(await self.integration.async_setup_entry(self.hass, entry))
        entry._async_set_state(self.hass, ConfigEntryState.LOADED, None)
        self.addAsyncCleanup(entry.runtime_data.async_shutdown)
        return entry.runtime_data

    async def test_rotation_persists_without_reload_options_still_reload(self):
        entry = await self.entry()
        coordinator = await self.setup_entry(entry)
        client = coordinator.client
        self.assertEqual(client.tokens.access_token, 'old-access')
        self.assertIsNone(client._password)
        with patch.object(self.hass.config_entries, 'async_reload', new=AsyncMock()) as reload:
            with patch.object(client, '_post_raw', new=AsyncMock(side_effect=[
                self.client_module.BpostAuthError(),
                {'status': 'success', 'response': {'accessToken': 'rotated', 'refreshToken': 'rotated-refresh'}},
                {'status': 'success', 'response': {'items': []}},
            ])):
                await client.get_parcels_list()
            await self.hass.async_block_till_done()
            self.assertEqual(entry.data['access_token'], 'rotated')
            self.assertEqual(entry.data['refresh_token'], 'rotated-refresh')
            self.assertNotIn('password', entry.data)
            reload.assert_not_awaited()
            self.hass.config_entries.async_update_entry(entry, options={'retention_days': 14})
            await self.hass.async_block_till_done()
            reload.assert_awaited_once_with(entry.entry_id)

    async def test_coordinator_maps_errors_after_setup(self):
        entry = await self.entry()
        coordinator = await self.setup_entry(entry)
        for error, expected in ((self.client_module.BpostAuthError, ConfigEntryAuthFailed),
                                (self.client_module.BpostApiError, UpdateFailed)):
            with self.subTest(error=error.__name__):
                with patch.object(coordinator.client, 'get_parcels_list', new=AsyncMock(side_effect=error)):
                    with self.assertRaises(expected):
                        await coordinator._async_update_data()

    async def test_diagnostics_do_not_expose_credentials_or_tracking_ids(self):
        from homeassistant.helpers import entity_registry as er
        from homeassistant.helpers import device_registry as dr
        entry = await self.entry()
        coordinator = await self.setup_entry(entry)
        code = 'SYNTHETIC-TRACKING-123456'
        coordinator.data.summaries[code] = self.models.ParcelSummary(code)
        registry = er.async_get(self.hass)
        await registry.async_load()
        await dr.async_get(self.hass).async_load()
        registry.async_get_or_create('sensor', 'my_bpost', code,
                                     config_entry=entry, suggested_object_id='private_recipient')
        result = json.dumps(await self.diagnostics.async_get_config_entry_diagnostics(self.hass, entry))
        for private in ('fiction@example.invalid', 'old-access', 'old-refresh', code, '123456', 'private_recipient'):
            self.assertNotIn(private, result)
        self.assertIn('parcel_1', result)

    def parcel_data(self, statuses, *, active=True):
        data = self.coordinator_module.BpostData()
        for code, status in statuses.items():
            data.summaries[code] = self.models.ParcelSummary(code, status)
            data.details[code] = self.models.ParcelDetail(code, current_status=status,
                user_type='RECEIVER', receiver=self.models.Person(postcode='1000'))
        if active:
            data.active_codes = set(statuses)
        return data

    async def test_initial_inbox_is_silent_and_return_is_not_delivered(self):
        coordinator = await self.setup_entry(await self.entry())
        coordinator._previous = None
        with patch.object(type(self.hass.bus), 'async_fire') as fire:
            coordinator._detect_changes(self.parcel_data({'parcel': 'IN_TRANSIT'}))
            fire.assert_not_called()
            coordinator._detect_changes(self.parcel_data({'parcel': 'DELIVERED_TO_SENDER'}, active=False))
            self.assertEqual([c.args[0] for c in fire.call_args_list],
                             ['my_bpost_status_changed', 'my_bpost_returned'])
            self.assertEqual(fire.call_args_list[0].args[1]['new_status'], 'returned')

    async def test_delivery_events_only_on_canonical_transitions(self):
        coordinator = await self.setup_entry(await self.entry())
        coordinator._previous = None
        coordinator._detect_changes(self.parcel_data({'parcel': 'IN_TRANSIT'}))
        with patch.object(type(self.hass.bus), 'async_fire') as fire:
            coordinator._detect_changes(self.parcel_data({'parcel': 'OutForDelivery'}))
            self.assertEqual([c.args[0] for c in fire.call_args_list],
                             ['my_bpost_status_changed', 'my_bpost_out_for_delivery'])
            fire.reset_mock()
            coordinator._detect_changes(self.parcel_data({'parcel': 'OUT_FOR_DELIVERY'}))
            fire.assert_not_called()
            coordinator._detect_changes(self.parcel_data({'parcel': 'DistributedNormally'}, active=False))
            self.assertEqual([c.args[0] for c in fire.call_args_list],
                             ['my_bpost_status_changed', 'my_bpost_delivered'])

    async def test_new_history_is_not_announced_missing_parcel_not_reannounced(self):
        coordinator = await self.setup_entry(await self.entry())
        with patch.object(type(self.hass.bus), 'async_fire') as fire:
            coordinator._detect_changes(self.parcel_data({'history': 'DELIVERED'}, active=False))
            fire.assert_not_called()
            coordinator._detect_changes(self.parcel_data({'new': 'IN_TRANSIT'}))
            self.assertEqual(fire.call_count, 1)
            self.assertEqual(fire.call_args.args[0], 'my_bpost_new_package')
            fire.reset_mock()
            coordinator._detect_changes(self.parcel_data({}))
            coordinator._detect_changes(self.parcel_data({'new': 'IN_TRANSIT'}))
            fire.assert_not_called()

    async def test_parcel_baseline_survives_coordinator_restart(self):
        entry = await self.entry()
        coordinator = await self.setup_entry(entry)
        coordinator._previous = None
        data = self.parcel_data({'parcel': 'OUT_FOR_DELIVERY'})
        with patch.object(coordinator.client, 'get_parcels_list', new=AsyncMock(return_value=list(data.summaries.values()))), patch.object(
            coordinator.client, 'get_parcels_details', new=AsyncMock(return_value=(list(data.details.values()), []))):
            await coordinator._async_fetch_data()
        restarted = self.coordinator_module.BpostDataUpdateCoordinator(self.hass, coordinator.client, entry, scan_minutes=10)
        self.addAsyncCleanup(restarted.async_shutdown)
        await restarted._async_setup()
        with patch.object(type(self.hass.bus), 'async_fire') as fire:
            restarted._detect_changes(data)
            fire.assert_not_called()

    async def test_registry_migration_preserves_entity_id_and_is_idempotent(self):
        from homeassistant.helpers import entity_registry as er
        entry = await self.entry()
        registry = er.async_get(self.hass)
        legacy = registry.async_get_or_create('sensor', 'my_bpost', 'packages',
                                              config_entry=entry, suggested_object_id='custom_parcels')
        self.integration.async_migrate_entity_ids(self.hass, entry)
        self.integration.async_migrate_entity_ids(self.hass, entry)
        self.assertEqual(registry.async_get(legacy.entity_id).unique_id, f'{entry.entry_id}_packages')
        self.assertEqual(registry.async_get_entity_id('sensor', 'my_bpost', f'{entry.entry_id}_packages'), legacy.entity_id)

    async def test_same_parcel_in_two_accounts_has_distinct_identities(self):
        first = await self.entry()
        second = await self.entry()
        coordinator = await self.setup_entry(first)
        sensor1 = self.sensor_module.BpostParcelSensor(coordinator, first, 'same-code')
        sensor2 = self.sensor_module.BpostParcelSensor(coordinator, second, 'same-code')
        self.assertNotEqual(sensor1.unique_id, sensor2.unique_id)
        self.assertNotEqual(self.sensor_module.BpostPackagesSensor(coordinator, first).unique_id,
                            self.sensor_module.BpostPackagesSensor(coordinator, second).unique_id)

    async def live_coordinator(self, count=1):
        entry = await self.entry()
        coordinator = await self.setup_entry(entry)
        coordinator.data = self.parcel_data({f'parcel-{i}': 'OUT_FOR_DELIVERY' for i in range(count)})
        return entry, coordinator, coordinator.live

    async def test_live_budget_fairness_and_manual_refresh_limit(self):
        _, coordinator, live = await self.live_coordinator(3)
        status = self.models.LiveRoundStatus(stops_until_target=3)
        with patch.object(coordinator.client, 'get_live_status', new=AsyncMock(return_value=status)) as fetch:
            with patch.object(self.live_module, 'monotonic', return_value=100):
                live.data = await live._async_update_data()
                self.assertEqual(fetch.await_count, 2)
                live.data = await live._async_update_data()
                self.assertEqual(fetch.await_count, 2)
            with patch.object(self.live_module, 'monotonic', return_value=161):
                live.data = await live._async_update_data()
                self.assertEqual(fetch.call_args_list[2].args[0], 'parcel-2')
                self.assertLessEqual(fetch.await_count, 4)

    async def test_live_respects_server_interval_and_expires_old_data(self):
        _, coordinator, live = await self.live_coordinator()
        status = self.models.LiveRoundStatus(stops_until_target=0, auto_refresh_s=900)
        with patch.object(coordinator.client, 'get_live_status', new=AsyncMock(return_value=status)) as fetch:
            with patch.object(self.live_module, 'monotonic', return_value=100):
                live.data = await live._async_update_data()
                self.assertEqual(live.current('parcel-0').status.stops_until_target, 0)
            with patch.object(self.live_module, 'monotonic', return_value=701):
                self.assertIsNone(live.current('parcel-0'))
                live.data = await live._async_update_data()
                self.assertEqual(fetch.await_count, 1)

    async def test_live_missing_data_backs_off_without_zero_stops(self):
        _, coordinator, live = await self.live_coordinator()
        with patch.object(coordinator.client, 'get_live_status', new=AsyncMock(return_value=None)) as fetch:
            with patch.object(self.live_module, 'monotonic', return_value=100):
                live.data = await live._async_update_data()
                self.assertIsNone(live.current('parcel-0'))
            with patch.object(self.live_module, 'monotonic', return_value=161):
                live.data = await live._async_update_data()
                self.assertEqual(fetch.await_count, 1)

    async def test_live_429_pauses_whole_account(self):
        _, coordinator, live = await self.live_coordinator(3)
        error = self.client_module.BpostRateLimitError(600)
        with patch.object(coordinator.client, 'get_live_status', new=AsyncMock(side_effect=error)) as fetch:
            with patch.object(self.live_module, 'monotonic', return_value=100):
                live.data = await live._async_update_data()
            with patch.object(self.live_module, 'monotonic', return_value=300):
                live.data = await live._async_update_data()
            self.assertEqual(fetch.await_count, 1)
            self.assertEqual(live.data, {})

    async def test_live_never_polls_ineligible_or_disabled_parcels(self):
        entry, coordinator, live = await self.live_coordinator(2)
        coordinator.data.details['parcel-0'].receiver.postcode = None
        coordinator.data.details['parcel-1'].current_status = 'DELIVERED'
        with patch.object(coordinator.client, 'get_live_status', new=AsyncMock()) as fetch:
            live.data = await live._async_update_data()
            fetch.assert_not_awaited()
            self.assertIsNone(live.update_interval)
            coordinator.data = self.parcel_data({'parcel': 'OUT_FOR_DELIVERY'})
            self.hass.config_entries.async_update_entry(entry, options={'enable_live_tracking': False})
            live.data = await live._async_update_data()
            fetch.assert_not_awaited()

    async def test_live_auth_failure_does_not_mark_parcel_feed_failed(self):
        _, coordinator, live = await self.live_coordinator()
        with patch.object(coordinator.client, 'get_live_status', new=AsyncMock(side_effect=self.client_module.BpostAuthError)):
            with self.assertRaises(ConfigEntryAuthFailed):
                await live._async_update_data()
        self.assertTrue(coordinator.last_update_success)
        self.assertEqual(live.data, {})

    async def test_courier_and_pickup_have_separate_coords_and_expiry(self):
        entry, coordinator, live = await self.live_coordinator()
        coordinator.data.details['parcel-0'].delivery_point = self.models.DeliveryPoint(latitude=51, longitude=5)
        status = self.models.LiveRoundStatus(stops_until_target=2, last_known_lat=50.85, last_known_lon=4.35)
        courier = self.tracker_module.BpostParcelTracker(coordinator, entry, 'parcel-0', courier=True)
        pickup = self.tracker_module.BpostParcelTracker(coordinator, entry, 'parcel-0')
        with patch.object(coordinator.client, 'get_live_status', new=AsyncMock(return_value=status)):
            with patch.object(self.live_module, 'monotonic', return_value=100):
                live.data = await live._async_update_data()
                self.assertTrue(courier.available)
                self.assertEqual(courier.state_attributes['latitude'], 50.85)
                self.assertEqual(pickup.state_attributes['latitude'], 51)
                self.assertNotEqual(pickup.unique_id, courier.unique_id)
            with patch.object(self.live_module, 'monotonic', return_value=221):
                self.assertFalse(courier.available)
                self.assertNotIn('latitude', courier.state_attributes)
                self.assertTrue(pickup.available)
                coordinator.data.details['parcel-0'].delivery_point.latitude = float('nan')
                self.assertFalse(pickup.available)
                self.assertNotIn('latitude', pickup.state_attributes)

    async def test_normalized_sensor_raw_state_and_direction_counts(self):
        entry, coordinator, live = await self.live_coordinator(2)
        coordinator.data.details['parcel-1'].user_type = 'SENDER'
        parcel = self.sensor_module.BpostParcelSensor(coordinator, entry, 'parcel-0')
        self.assertEqual(parcel.native_value, 'out_for_delivery')
        self.assertEqual(parcel.extra_state_attributes['raw_status'], 'OUT_FOR_DELIVERY')
        self.assertFalse(parcel.extra_state_attributes['live_available'])
        self.assertNotIn('stops_remaining', parcel.extra_state_attributes)
        self.assertEqual(self.sensor_module.BpostPackagesSensor(coordinator, entry, 'incoming').native_value, 1)
        self.assertEqual(self.sensor_module.BpostPackagesSensor(coordinator, entry, 'outgoing').native_value, 1)
        coordinator.data.summaries.pop('parcel-0')
        self.assertFalse(parcel.available)

    async def test_options_flow_preserves_other_options(self):
        entry = await self.entry()
        self.hass.config_entries.async_update_entry(entry, options={'retention_days': 14})
        flow = self.flow_module.BpostOptionsFlow()
        flow.hass = self.hass
        flow.handler = entry.entry_id
        result = await flow.async_step_init({'enable_live_tracking': False})
        self.assertEqual(result['type'], 'create_entry')
        self.assertEqual(result['data'], {'retention_days': 14, 'enable_live_tracking': False})

    async def test_registry_conflict_leaves_legacy_identity_untouched(self):
        from homeassistant.exceptions import ConfigEntryError
        from homeassistant.helpers import entity_registry as er
        entry = await self.entry()
        registry = er.async_get(self.hass)
        legacy = registry.async_get_or_create('sensor', 'my_bpost', 'packages', config_entry=entry)
        registry.async_get_or_create('sensor', 'my_bpost', f'{entry.entry_id}_packages', config_entry=entry)
        with self.assertRaises(ConfigEntryError):
            self.integration.async_migrate_entity_ids(self.hass, entry)
        self.assertEqual(registry.async_get(legacy.entity_id).unique_id, 'packages')

    async def test_account_outage_hides_previously_valid_courier_data(self):
        _, coordinator, live = await self.live_coordinator()
        with patch.object(coordinator.client, 'get_live_status', new=AsyncMock(
            return_value=self.models.LiveRoundStatus(stops_until_target=2))):
            live.data = await live._async_update_data()
        self.assertIsNotNone(live.current('parcel-0'))
        coordinator.last_update_success = False
        self.assertIsNone(live.current('parcel-0'))

    async def test_account_polling_adapts_without_live_requests(self):
        coordinator = await self.setup_entry(await self.entry())
        for statuses, minutes in (({}, 30), ({'p': 'IN_TRANSIT'}, 10), ({'p': 'OUT_FOR_DELIVERY'}, 5)):
            with self.subTest(statuses=statuses):
                data = self.parcel_data(statuses)
                with patch.object(coordinator.client, 'get_parcels_list', new=AsyncMock(return_value=list(data.summaries.values()))), patch.object(
                    coordinator.client, 'get_parcels_details', new=AsyncMock(return_value=(list(data.details.values()), []))):
                    await coordinator._async_fetch_data()
                self.assertEqual(coordinator.update_interval.total_seconds(), minutes * 60)

    async def test_removing_entry_removes_parcel_baseline(self):
        entry = await self.entry()
        coordinator = await self.setup_entry(entry)
        self.assertIsNotNone(await coordinator._store.async_load())
        await self.integration.async_remove_entry(self.hass, entry)
        self.assertIsNone(await coordinator._store.async_load())

    async def fetch_data(self, coordinator, data):
        active = [detail for code, detail in data.details.items() if code in data.active_codes]
        history = [detail for code, detail in data.details.items() if code not in data.active_codes]
        with patch.object(coordinator.client, 'get_parcels_list', new=AsyncMock(return_value=list(data.summaries.values()))), patch.object(
            coordinator.client, 'get_parcels_details', new=AsyncMock(return_value=(active, history))):
            return await coordinator._async_update_data()

    async def test_retention_expiry_survives_restart_scoped_to_account(self):
        from datetime import timedelta
        from homeassistant.helpers import entity_registry as er
        from homeassistant.util import dt as dt_util
        entry, other = await self.entry(), await self.entry()
        coordinator = await self.setup_entry(entry)
        registry = er.async_get(self.hass)
        owned = [registry.async_get_or_create(domain, 'my_bpost', f'{entry.entry_id}_{key}', config_entry=entry)
                 for domain, key in [('sensor', 'parcel'), ('device_tracker', 'parcel_tracker'), ('device_tracker', 'parcel_courier')]]
        preserved = [registry.async_get_or_create(domain, 'my_bpost', f'{account.entry_id}_{key}', config_entry=account)
                     for account, domain, key in [(entry, 'sensor', 'packages'), (entry, 'calendar', 'deliveries'),
                                                  (other, 'sensor', 'parcel')]]
        data = self.parcel_data({'parcel': 'DELIVERED'}, active=False)
        now = dt_util.utcnow()
        with patch.object(self.coordinator_module.dt_util, 'utcnow', return_value=now):
            first = await self.fetch_data(coordinator, data)
        self.assertIn('parcel', first.summaries)
        restarted = self.coordinator_module.BpostDataUpdateCoordinator(self.hass, coordinator.client, entry, scan_minutes=10)
        self.addAsyncCleanup(restarted.async_shutdown)
        await restarted._async_setup()
        self.assertEqual(restarted._inactive_since, coordinator._inactive_since)
        with patch.object(self.coordinator_module.dt_util, 'utcnow', return_value=now + timedelta(days=7)):
            expired = await self.fetch_data(restarted, data)
            again = await self.fetch_data(restarted, data)
        self.assertEqual(expired.summaries, {})
        self.assertEqual(again.details, {})
        self.assertTrue(all(registry.async_get(entity.entity_id) is None for entity in owned))
        self.assertTrue(all(registry.async_get(entity.entity_id) is not None for entity in preserved))

    async def test_retention_active_reappearance_resets_clock_and_failure_preserves(self):
        from datetime import timedelta
        from homeassistant.util import dt as dt_util
        entry = await self.entry()
        coordinator = await self.setup_entry(entry)
        now = dt_util.utcnow()
        history = self.parcel_data({'parcel': 'DELIVERED'}, active=False)
        with patch.object(self.coordinator_module.dt_util, 'utcnow', return_value=now):
            await self.fetch_data(coordinator, history)
        with patch.object(self.coordinator_module.dt_util, 'utcnow', return_value=now + timedelta(days=8)):
            with patch.object(coordinator.client, 'get_parcels_list', new=AsyncMock(side_effect=self.client_module.BpostApiError)):
                with self.assertRaises(UpdateFailed):
                    await coordinator._async_update_data()
            self.assertEqual(coordinator.expired_codes, set())
            active = await self.fetch_data(coordinator, self.parcel_data({'parcel': 'IN_TRANSIT'}))
            self.assertIn('parcel', active.summaries)
            self.assertNotIn('parcel', coordinator._inactive_since)
            result = await self.fetch_data(coordinator, history)
            self.assertIn('parcel', result.summaries)
            self.assertEqual(coordinator._inactive_since['parcel'], (now + timedelta(days=8)).timestamp())

    async def test_retention_missing_legacy_entity_and_custom_duration(self):
        from datetime import timedelta
        from homeassistant.helpers import entity_registry as er
        from homeassistant.util import dt as dt_util
        entry = await self.entry()
        self.hass.config_entries.async_update_entry(entry, options={'retention_days': 14})
        coordinator = await self.setup_entry(entry)
        registry = er.async_get(self.hass)
        entity = registry.async_get_or_create('sensor', 'my_bpost', 'missing', config_entry=entry)
        now = dt_util.utcnow()
        for days in (0, 7, 14):
            with patch.object(self.coordinator_module.dt_util, 'utcnow', return_value=now + timedelta(days=days)):
                await self.fetch_data(coordinator, self.parcel_data({}))
            self.assertEqual(registry.async_get(entity.entity_id) is None, days == 14)
        self.assertNotIn('missing', coordinator._inactive_since)

    async def test_eta_changes_deduplicated_across_gaps_and_restart(self):
        entry = await self.entry()
        coordinator = await self.setup_entry(entry)
        coordinator._previous = None
        data = self.parcel_data({'parcel': 'IN_TRANSIT'})
        data.details['parcel'].eta = self.models.Eta('2026-10-06', '10:00', '12:00')
        with patch.object(type(self.hass.bus), 'async_fire') as fire:
            await self.fetch_data(coordinator, data)
            fire.assert_not_called()
            data.details['parcel'].eta.time1 = '11:00'
            await self.fetch_data(coordinator, data)
            self.assertEqual([call.args[0] for call in fire.call_args_list], ['my_bpost_eta_changed'])
            self.assertEqual(fire.call_args.args[1]['old_eta'][1], '10:00')
            self.assertEqual(fire.call_args.args[1]['new_eta'][1], '11:00')
            fire.reset_mock()
            data.details['parcel'].eta = self.models.Eta()
            await self.fetch_data(coordinator, data)
            restarted = self.coordinator_module.BpostDataUpdateCoordinator(self.hass, coordinator.client, entry, scan_minutes=10)
            self.addAsyncCleanup(restarted.async_shutdown)
            await restarted._async_setup()
            data.details['parcel'].eta = self.models.Eta('2026-10-06', '11:00', '12:00')
            await self.fetch_data(restarted, data)
            fire.assert_not_called()

    async def test_pickup_and_problem_device_events_once(self):
        coordinator = await self.setup_entry(await self.entry())
        coordinator._previous = None
        coordinator._detect_changes(self.parcel_data({'parcel': 'IN_TRANSIT'}))
        for status, event in [('AT_PICKUP_POINT', 'my_bpost_at_pickup_point'), ('PROBLEM', 'my_bpost_problem')]:
            with patch.object(type(self.hass.bus), 'async_fire') as fire:
                data = self.parcel_data({'parcel': status})
                coordinator._detect_changes(data)
                coordinator._detect_changes(data)
                self.assertEqual([call.args[0] for call in fire.call_args_list], ['my_bpost_status_changed', event])

    async def test_device_trigger_discovery_validation_and_account_filter(self):
        from homeassistant.helpers import device_registry as dr
        from homeassistant.components.device_automation import InvalidDeviceAutomationConfig
        module = importlib.import_module('custom_components.my_bpost.device_trigger')
        entry, other = await self.entry(), await self.entry()
        device = dr.async_get(self.hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={('my_bpost', entry.entry_id)})
        triggers = await module.async_get_triggers(self.hass, device.id)
        self.assertEqual(len(triggers), 9)
        self.assertEqual(await module.async_get_triggers(self.hass, 'missing-device'), [])
        config = next(trigger for trigger in triggers if trigger['type'] == 'delivered')
        with self.assertRaises(InvalidDeviceAutomationConfig):
            await module.async_validate_trigger_config(self.hass, {**config, 'device_id': 'missing-device'})
        import voluptuous as vol
        with self.assertRaises(vol.Invalid):
            await module.async_validate_trigger_config(self.hass, {**config, 'type': 'unsupported'})
        actions = []
        async def action(variables, context):
            actions.append(variables['trigger'])
        remove = await module.async_attach_trigger(self.hass, config, action,
            {'trigger_data': {'id': '0', 'idx': '0'}, 'variables': {}})
        self.hass.bus.async_fire('my_bpost_delivered', {'entry_id': other.entry_id, 'item_code': 'same'})
        self.hass.bus.async_fire('my_bpost_delivered', {'entry_id': entry.entry_id, 'item_code': 'same'})
        await self.hass.async_block_till_done()
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['platform'], 'device')
        self.assertEqual(actions[0]['event'].data['entry_id'], entry.entry_id)
        remove()
        self.hass.bus.async_fire('my_bpost_delivered', {'entry_id': entry.entry_id})
        await self.hass.async_block_till_done()
        self.assertEqual(len(actions), 1)

    async def test_calendar_dates_timezone_all_day_range_and_account_ids(self):
        from datetime import date, datetime, timezone, timedelta
        module = importlib.import_module('custom_components.my_bpost.calendar')
        entry = await self.entry()
        coordinator = await self.setup_entry(entry)
        data = self.parcel_data({key: 'IN_TRANSIT' for key in ['timed', 'all-day', 'invalid', 'partial', 'history']})
        data.active_codes.remove('history')
        data.details['timed'].eta = self.models.Eta('2026-10-25', '10:00', '12:00')
        data.details['all-day'].eta = self.models.Eta('24/10/2026')
        data.details['invalid'].eta = self.models.Eta('tomorrow', '10:00', '12:00')
        data.details['partial'].eta = self.models.Eta('26-10-2026', '10:00')
        data.details['history'].eta = self.models.Eta('2026-10-25', '10:00', '12:00')
        coordinator.data = data
        calendar = module.BpostDeliveryCalendar(coordinator, entry)
        events = module.delivery_events(data, entry.entry_id)
        self.assertEqual(len(events), 3)
        self.assertTrue(events[0].all_day)
        self.assertEqual(events[0].start, date(2026, 10, 24))
        self.assertEqual(events[0].end, date(2026, 10, 25))
        self.assertEqual(events[1].start.utcoffset(), timedelta(hours=1))
        self.assertEqual(events[1].start.hour, 10)
        self.assertTrue(events[2].all_day)
        ranged = await calendar.async_get_events(self.hass, datetime(2026,10,25,9,tzinfo=timezone.utc), datetime(2026,10,25,11,tzinfo=timezone.utc))
        self.assertEqual([e.uid for e in ranged], [f'{entry.entry_id}_timed'])
        self.assertEqual(await calendar.async_get_events(self.hass, datetime(2026,10,25,11,tzinfo=timezone.utc), datetime(2026,10,25,12,tzinfo=timezone.utc)), [])
        self.assertNotEqual(events[1].uid, module.delivery_events(data, 'other')[1].uid)
        with patch.object(module.dt_util, 'utcnow', return_value=datetime(2026,10,25,10,tzinfo=timezone.utc)):
            self.assertEqual(calendar.event.uid, ranged[0].uid)
        data.details['timed'].eta.day = '2026-07-25'
        self.assertEqual(next(e for e in module.delivery_events(data, entry.entry_id) if e.uid.endswith('_timed')).start.utcoffset(), timedelta(hours=2))

    async def test_calendar_reversed_window_falls_back_and_options_validate_range(self):
        import voluptuous as vol
        module = importlib.import_module('custom_components.my_bpost.calendar')
        data = self.parcel_data({'parcel': 'IN_TRANSIT'})
        data.details['parcel'].eta = self.models.Eta('2026-10-05', '16:00', '12:00')
        self.assertTrue(module.delivery_events(data, 'account')[0].all_day)
        entry = await self.entry()
        flow = self.flow_module.BpostOptionsFlow()
        flow.hass, flow.handler = self.hass, entry.entry_id
        result = await flow.async_step_init()
        for invalid in (0, -1, 366):
            with self.assertRaises(vol.Invalid):
                result['data_schema']({'retention_days': invalid})
        self.assertEqual(result['data_schema']({})['retention_days'], 7)

    async def test_public_display_options_do_not_need_the_backend(self):
        entry = await self.entry(data={'source': 'public', 'barcode': 'synthetic-code',
                                       'postal_code': '1000', 'label': 'Old name'})
        flow = self.flow_module.BpostOptionsFlow()
        flow.hass, flow.handler = self.hass, entry.entry_id
        with patch.object(self.flow_module, '_validate_tracking', new=AsyncMock()) as validate:
            result = await flow.async_step_init({'postal_code': '1000', 'label': 'New name',
                                                'direction': 'outgoing', 'retention_days': 30})
        self.assertEqual(result['type'], 'create_entry')
        self.assertEqual(result['data']['label'], 'New name')
        self.assertEqual(result['data']['direction'], 'outgoing')
        validate.assert_not_awaited()

    def mail_item(self, identifier='private-mail-id', **kwargs):
        from homeassistant.util import dt as dt_util
        from zoneinfo import ZoneInfo
        module = importlib.import_module('custom_components.my_bpost.pybpost.mail')
        return module.MailItem(identifier, dt_util.utcnow().astimezone(ZoneInfo('Europe/Brussels')).date(),
                              sender='private-sender', image_url='https://scan.bpost.be/a?sig=private-signature',
                              image_ref=kwargs.pop('image_ref', 'private-reference'), **kwargs)

    async def test_mail_capabilities_count_and_disabled_make_no_scan_requests(self):
        entry = await self.entry()
        parent = await self.setup_entry(entry)
        mail = parent.mail
        count = self.sensor_module.BpostMailSensor(mail, entry, status=False)
        status = self.sensor_module.BpostMailSensor(mail, entry, status=True)
        with patch.object(parent.client, 'get_letters', new=AsyncMock()) as letters:
            for summary, expected in [({'isMMTSubscribed':False,'isMMTEligible':False},'not_eligible'),
                    ({'isMMTSubscribed':False,'isMMTEligible':True},'not_subscribed'), ({},'unknown')]:
                with patch.object(parent.client,'get_mail_summary',new=AsyncMock(return_value=summary)):
                    await mail.async_refresh()
                self.assertEqual(status.native_value,expected)
                self.assertTrue(status.available)
                self.assertFalse(count.available)
                self.assertEqual(mail.update_interval.total_seconds(),12*3600)
            letters.assert_not_awaited()
        disabled_entry = await self.entry()
        self.hass.config_entries.async_update_entry(disabled_entry,options={'enable_mail':False})
        with patch.object(self.client_module.BpostClient,'get_mail_summary',new=AsyncMock()) as summary:
            disabled = await self.setup_entry(disabled_entry)
            summary.assert_not_awaited()
        self.assertEqual(disabled.mail.data.capability,'disabled')
        self.assertIsNone(disabled.mail.update_interval)

    async def test_mail_events_survive_gaps_restart_and_never_persist_links(self):
        entry = await self.entry()
        parent = await self.setup_entry(entry)
        mail = parent.mail
        first, second = self.mail_item(), self.mail_item('another-private-id')
        announced = []
        self.hass.bus.async_listen('my_bpost_letter_announced',announced.append)
        with patch.object(parent.client,'get_mail_summary',new=AsyncMock(return_value={'isMMTSubscribed':True})), patch.object(
            parent.client,'get_letters',new=AsyncMock(return_value=[first])) as letters:
            await mail.async_refresh()
            await self.hass.async_block_till_done()
            self.assertEqual(announced,[])
            letters.return_value = [first,second]
            await mail.async_refresh()
            await self.hass.async_block_till_done()
            self.assertEqual(len(announced),1)
            self.assertEqual(announced[0].data['mail_id'],second.key)
            letters.return_value = []
            await mail.async_refresh()
            module = importlib.import_module('custom_components.my_bpost.mail')
            restarted = module.BpostMailCoordinator(parent)
            self.addAsyncCleanup(restarted.async_shutdown)
            letters.return_value = [first,second]
            await restarted.async_refresh()
            await self.hass.async_block_till_done()
            self.assertEqual(len(announced),1)
            persisted = json.dumps(await restarted._store.async_load())
            for secret in ('private-mail-id','another-private-id','private-sender','private-signature','private-reference','https://'):
                self.assertNotIn(secret,persisted)
                self.assertNotIn(secret,str(announced[0].data))
            self.assertEqual(len(restarted.data.letters),2)
            await self.integration.async_remove_entry(self.hass,entry)
            self.assertIsNone(await restarted._store.async_load())

    async def test_mail_failure_is_isolated_and_count_does_not_become_zero(self):
        entry = await self.entry()
        parent = await self.setup_entry(entry)
        mail = parent.mail
        item = self.mail_item()
        count = self.sensor_module.BpostMailSensor(mail,entry,status=False)
        with patch.object(parent.client,'get_mail_summary',new=AsyncMock(return_value={'isMMTSubscribed':True})), patch.object(
            parent.client,'get_letters',new=AsyncMock(return_value=[item])):
            await mail.async_refresh()
        self.assertTrue(count.available)
        self.assertEqual(count.native_value,1)
        with patch.object(parent.client,'get_mail_summary',new=AsyncMock(side_effect=self.client_module.BpostApiError)):
            await mail.async_refresh()
        self.assertFalse(count.available)
        self.assertEqual(count.native_value,1)
        self.assertTrue(parent.last_update_success)
        self.assertEqual(mail._seen.keys(),{item.key})
        with patch.object(parent.client,'get_mail_summary',new=AsyncMock(side_effect=self.client_module.BpostRateLimitError(3600))):
            with self.assertRaises(UpdateFailed):
                await mail._async_update_data()
        self.assertEqual(mail.update_interval.total_seconds(),3600)
        with patch.object(parent.client,'get_mail_summary',new=AsyncMock(side_effect=self.client_module.BpostAuthError)):
            with self.assertRaises(ConfigEntryAuthFailed):
                await mail._async_update_data()

    async def test_mail_window_and_account_entities_are_not_parcel_retention(self):
        from datetime import timedelta
        from homeassistant.helpers import entity_registry as er
        from homeassistant.util import dt as dt_util
        from dataclasses import replace
        entry = await self.entry()
        parent = await self.setup_entry(entry)
        item = self.mail_item()
        old = replace(item,item_id='old',day=item.day-timedelta(days=30))
        future = replace(item,item_id='future',day=item.day+timedelta(days=1))
        with patch.object(parent.client,'get_mail_summary',new=AsyncMock(return_value={'isMMTSubscribed':True})), patch.object(
            parent.client,'get_letters',new=AsyncMock(return_value=[item,old,future])) as fetch:
            await parent.mail.async_refresh()
        self.assertEqual(set(parent.mail.data.letters),{item.key})
        self.assertEqual(fetch.call_args.args,(item.day-timedelta(days=29),item.day))
        registry = er.async_get(self.hass)
        entities = [registry.async_get_or_create('sensor','my_bpost',f'{entry.entry_id}_{key}',config_entry=entry)
                    for key in ('mail_count','mail_status')]
        for days in (0,8):
            with patch.object(self.coordinator_module.dt_util,'utcnow',return_value=dt_util.utcnow()+timedelta(days=days)):
                await self.fetch_data(parent,self.parcel_data({}))
        self.assertTrue(all(registry.async_get(entity.entity_id) is not None for entity in entities))
        self.assertNotIn('mail_count',parent._inactive_since)

    async def test_mail_diagnostics_include_only_capability_and_count(self):
        entry = await self.entry()
        parent = await self.setup_entry(entry)
        with patch.object(parent.client,'get_mail_summary',new=AsyncMock(return_value={'isMMTSubscribed':True})), patch.object(
            parent.client,'get_letters',new=AsyncMock(return_value=[self.mail_item()])):
            await parent.mail.async_refresh()
        report = await self.diagnostics.async_get_config_entry_diagnostics(self.hass,entry)
        self.assertEqual(report['mail'],{'last_update_success':True,'capability':'available','count':1})
        for private in ('private-mail-id','private-sender','private-signature','private-reference'):
            self.assertNotIn(private,json.dumps(report))

    async def test_mail_image_cache_expiry_url_rotation_and_outage(self):
        import asyncio
        from dataclasses import replace
        entry = await self.entry()
        self.hass.config_entries.async_update_entry(entry,options={'enable_mail_images':True})
        parent = await self.setup_entry(entry)
        mail_module = importlib.import_module('custom_components.my_bpost.mail')
        image_module = importlib.import_module('custom_components.my_bpost.image')
        item = self.mail_item()
        parent.mail.data = mail_module.MailData(mail_module.MailCapability.AVAILABLE,{item.key:item})
        image = image_module.BpostMailImage(self.hass,parent.mail,entry,item.key)
        with patch.object(parent.client,'get_mail_image',new=AsyncMock(return_value=(b'scan','image/png'))) as fetch, patch.object(
            image_module,'monotonic',return_value=100) as clock:
            self.assertEqual(await asyncio.gather(image.async_image(),image.async_image()),[b'scan',b'scan'])
            fetch.assert_awaited_once()
            parent.mail.data.letters[item.key] = replace(item,image_url='https://scan.bpost.be/a?sig=rotated')
            await image.async_image()
            self.assertEqual(fetch.await_count,2)
            clock.return_value = 1001
            await image.async_image()
            self.assertEqual(fetch.await_count,3)
            parent.mail.last_update_success = False
            self.assertIsNone(await image.async_image())
            self.assertIsNone(image._bytes)
            self.assertEqual(fetch.await_count,3)
            self.assertNotIn('private',json.dumps(image.extra_state_attributes))
            self.assertIsNone(image.image_url)

    async def test_mail_image_failure_backoff_and_mid_request_removal(self):
        entry = await self.entry()
        self.hass.config_entries.async_update_entry(entry,options={'enable_mail_images':True})
        parent = await self.setup_entry(entry)
        mail_module = importlib.import_module('custom_components.my_bpost.mail')
        image_module = importlib.import_module('custom_components.my_bpost.image')
        item = self.mail_item()
        parent.mail.data = mail_module.MailData(mail_module.MailCapability.AVAILABLE,{item.key:item})
        image = image_module.BpostMailImage(self.hass,parent.mail,entry,item.key)
        with patch.object(parent.client,'get_mail_image',new=AsyncMock(side_effect=self.client_module.BpostApiError)) as fetch, patch.object(
            image_module,'monotonic',return_value=100) as clock:
            self.assertIsNone(await image.async_image())
            self.assertIsNone(await image.async_image())
            fetch.assert_awaited_once()
            clock.return_value = 161
            await image.async_image()
            self.assertEqual(fetch.await_count,2)
        async def remove_during_fetch(url):
            parent.mail.data.letters.clear()
            return b'stale','image/jpeg'
        image._retry_at = 0
        with patch.object(parent.client,'get_mail_image',side_effect=remove_during_fetch):
            self.assertIsNone(await image.async_image())
        self.assertIsNone(image._bytes)
