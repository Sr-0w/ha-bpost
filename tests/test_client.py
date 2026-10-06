"""Exercise authentication over HTTP using a local, synthetic bpost server."""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import aiohttp
from aiohttp import web

from pybpost import AuthTokens, BpostClient
from pybpost.exceptions import BpostApiError, BpostAuthError, BpostMaintenanceError, BpostRateLimitError


class ClientTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        self.responses = {}
        self.response_headers = {}
        self.old_requests = 0
        self.both_old_requests = asyncio.Event()
        self.concurrent = False
        app = web.Application()
        app.router.add_post('/{path:.*}', self.handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.base_patch = patch('pybpost.client.BASE_URL', f'http://127.0.0.1:{port}/')
        self.base_patch.start()
        self.session = aiohttp.ClientSession()
        self.callback = AsyncMock()
        self.client = BpostClient(self.session, tokens=AuthTokens('old', 'refresh'),
                                  on_tokens_updated=self.callback)

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()
        self.base_patch.stop()

    async def handle(self, request):
        path = request.match_info['path']
        body = await request.json()
        auth = request.headers.get('Authorization')
        self.calls.append((path, body, auth))
        if path in self.responses:
            status, payload = self.responses[path]
            if isinstance(payload, str):
                return web.Response(status=status, text=payload, headers=self.response_headers.get(path))
            return web.json_response(payload, status=status, headers=self.response_headers.get(path))
        if path == 'users/login':
            return web.json_response({'status': 'success', 'response': {
                'accessToken': 'new', 'refreshToken': 'rotated'}})
        if path == 'users/refreshtoken':
            return web.json_response({'status': 'success', 'response': {
                'access_token': 'new', 'refresh_token': 'rotated'}})
        if auth == 'old':
            if self.concurrent:
                self.old_requests += 1
                if self.old_requests == 2:
                    self.both_old_requests.set()
                await asyncio.wait_for(self.both_old_requests.wait(), 2)
            return web.json_response({'code': 'expired'}, status=401)
        return web.json_response({'status': 'success', 'response': {'items': []}})

    async def test_restored_session_never_logs_in(self):
        self.client = BpostClient(self.session, tokens=AuthTokens('new', 'refresh'))
        self.assertEqual(await self.client.get_parcels_list(), [])
        self.assertEqual([p for p, _, _ in self.calls], ['parcel/getparcelslist'])

    async def test_refresh_persists_rotated_tokens_and_retries(self):
        self.assertEqual(await self.client.get_parcels_list(), [])
        self.assertEqual([p for p, _, _ in self.calls], [
            'parcel/getparcelslist', 'users/refreshtoken', 'parcel/getparcelslist'])
        self.assertIsNone(self.calls[1][2])
        self.callback.assert_awaited_once()
        self.assertEqual(self.callback.call_args.args[0], AuthTokens('new', 'rotated'))

    async def test_concurrent_rejections_refresh_once(self):
        self.concurrent = True
        await asyncio.gather(self.client.get_parcels_list(), self.client.get_parcels_list())
        self.assertEqual(sum(p == 'users/refreshtoken' for p, _, _ in self.calls), 1)
        self.callback.assert_awaited_once()

    async def test_refresh_outage_is_not_auth_failure(self):
        self.responses['users/refreshtoken'] = (503, 'maintenance')
        with self.assertRaises(BpostMaintenanceError):
            await self.client.get_parcels_list()
        self.callback.assert_not_awaited()
        self.assertEqual(self.client.tokens.access_token, 'old')

    async def test_rejected_refresh_requires_reauth_without_login(self):
        self.responses['users/refreshtoken'] = (401, {'code': 'expired'})
        with self.assertRaises(BpostAuthError):
            await self.client.get_parcels_list()
        self.assertNotIn('users/login', [p for p, _, _ in self.calls])

    async def test_omitted_refresh_token_preserves_previous(self):
        self.responses['users/refreshtoken'] = (200, {
            'status': 'success', 'response': {'accessToken': 'new'}})
        await self.client.get_parcels_list()
        self.assertEqual(self.client.tokens.refresh_token, 'refresh')

    async def test_malformed_refresh_does_not_discard_session(self):
        self.responses['users/refreshtoken'] = (200, {'status': 'success', 'response': []})
        with self.assertRaises(BpostApiError):
            await self.client.get_parcels_list()
        self.assertEqual(self.client.tokens.access_token, 'old')

    async def test_second_rejection_does_not_loop(self):
        self.responses['parcel/getparcelslist'] = (403, {'code': 'expired'})
        with self.assertRaises(BpostAuthError):
            await self.client.get_parcels_list()
        self.assertEqual(len(self.calls), 3)

    async def test_login_forgets_constructor_credentials(self):
        self.client = BpostClient(self.session, email='fiction@example.invalid', password='synthetic')
        await self.client.get_parcels_list()
        self.assertIsNone(self.client._password)
        self.assertIsNone(self.client._email)
        self.responses['users/refreshtoken'] = (401, {})
        self.responses['parcel/getparcelslist'] = (401, {})
        with self.assertRaises(BpostAuthError):
            await self.client.get_parcels_list()
        self.assertEqual(sum(p == 'users/login' for p, _, _ in self.calls), 1)

    async def test_concurrent_initial_requests_login_once(self):
        self.client = BpostClient(self.session, email='fiction@example.invalid', password='synthetic')
        await asyncio.gather(self.client.get_parcels_list(), self.client.get_parcels_list())
        self.assertEqual(sum(p == 'users/login' for p, _, _ in self.calls), 1)

    async def test_failed_login_also_forgets_credentials(self):
        self.client = BpostClient(self.session, email='fiction@example.invalid', password='synthetic')
        self.responses['users/login'] = (401, {})
        with self.assertRaises(BpostAuthError):
            await self.client.login()
        self.assertIsNone(self.client._password)

    async def test_error_body_is_never_exposed(self):
        for payload in ({'private': 'synthetic-secret'}, 'synthetic-secret', []):
            with self.subTest(payload=type(payload).__name__):
                self.responses['parcel/getparcelslist'] = (500, payload)
                with self.assertRaises(BpostApiError) as caught:
                    await self.client.get_parcels_list()
                self.assertNotIn('synthetic-secret', str(caught.exception))

    async def test_non_object_success_is_protocol_error(self):
        self.responses['parcel/getparcelslist'] = (200, [])
        with self.assertRaises(BpostApiError):
            await self.client.get_parcels_list()

    async def test_live_api_failure_is_optional(self):
        self.responses['parcel/getparcelchunks'] = (500, {})
        self.assertIsNone(await self.client.get_live_status('synthetic', '1000'))

    async def test_live_rate_limit_is_not_hidden(self):
        self.responses['parcel/getparcelchunks'] = (429, 'Too many requests')
        self.response_headers['parcel/getparcelchunks'] = {'Retry-After': '600'}
        with self.assertRaises(BpostRateLimitError) as caught:
            await self.client.get_live_status('synthetic', '1000')
        self.assertEqual(caught.exception.retry_after, 600)

    async def test_invalid_rate_limit_has_safe_default(self):
        self.responses['parcel/getparcelslist'] = (429, {})
        self.response_headers['parcel/getparcelslist'] = {'Retry-After': 'NaN'}
        with self.assertRaises(BpostRateLimitError) as caught:
            await self.client.get_parcels_list()
        self.assertEqual(caught.exception.retry_after, 300)

    async def test_rate_limit_blocks_other_account_endpoints_until_deadline(self):
        self.responses['parcel/getparcelchunks'] = (429, {})
        self.response_headers['parcel/getparcelchunks'] = {'Retry-After': '600'}
        with patch('pybpost.client.monotonic', return_value=100):
            with self.assertRaises(BpostRateLimitError):
                await self.client.get_live_status('synthetic', '1000')
            with self.assertRaises(BpostRateLimitError):
                await self.client.get_parcels_list()
        self.assertEqual(len(self.calls), 1)
        self.client._tokens = AuthTokens('new', 'refresh')
        with patch('pybpost.client.monotonic', return_value=701):
            self.assertEqual(await self.client.get_parcels_list(), [])
        self.assertEqual(len(self.calls), 2)

    async def test_failed_envelope_does_not_become_empty_inbox(self):
        for payload in ({'status': 'error', 'response': {}},
                        {'status': 'success', 'response': []},
                        {'status': 'success', 'response': {'items': {}}}):
            with self.subTest(payload=payload):
                self.responses['parcel/getparcelslist'] = (200, payload)
                with self.assertRaises(BpostApiError):
                    await self.client.get_parcels_list()

    async def test_live_auth_failure_propagates(self):
        self.responses['parcel/getparcelchunks'] = (401, {})
        with self.assertRaises(BpostAuthError):
            await self.client.get_live_status('synthetic', '1000')

    async def test_transport_error_is_sanitized(self):
        with patch.object(self.session, 'post', side_effect=aiohttp.ClientConnectionError('private')):
            with self.assertRaises(BpostApiError) as caught:
                await self.client.get_parcels_list()
        self.assertNotIn('private', str(caught.exception))

    async def test_timeout_is_api_error(self):
        with patch.object(self.session, 'post', side_effect=TimeoutError):
            with self.assertRaises(BpostApiError):
                await self.client.get_parcels_list()

    async def test_session_ownership(self):
        await self.client.close()
        self.assertFalse(self.session.closed)
        own = BpostClient()
        session = await own._ensure_session()
        await own.close()
        self.assertTrue(session.closed)

    def test_token_repr_hides_secrets(self):
        self.assertNotIn('old', repr(self.client.tokens))
        self.assertNotIn("'refresh'", repr(self.client.tokens))
