"""Mail Ahead schema and private scan transport with synthetic HTTP responses."""

from datetime import date
import unittest
from unittest.mock import patch

import aiohttp
from aiohttp import web

from pybpost import AuthTokens, BpostClient, MailCapability, mail_capability
from pybpost.client import _mail_image_url
from pybpost.exceptions import BpostApiError, BpostRateLimitError
from pybpost.mail import parse_mail_items

PNG = b'\x89PNG\r\n\x1a\n' + b'synthetic-image'


class MailModelsTest(unittest.TestCase):
    def test_capability_requires_explicit_booleans(self):
        for payload, expected in [({}, 'unknown'), ({'isMMTSubscribed': 'true'}, 'unknown'),
                ({'isMMTSubscribed': True, 'isMMTEligible': False}, 'available'),
                ({'isMMTSubscribed': False, 'isMMTEligible': True}, 'not_subscribed'),
                ({'isMMTSubscribed': False, 'isMMTEligible': False}, 'not_eligible')]:
            self.assertEqual(mail_capability(payload), expected)

    def test_parse_deduplicate_and_private_repr(self):
        raw = {'itemId': 'private-identity', 'sender': {'name': 'private-sender'},
               'imageUrl': 'https://scan.bpost.be/a?sig=private-signature', 'imageRefId': 'private-reference',
               'plannedDistributionDate': '2026-10-07'}
        items = parse_mail_items({'2026-10-05': [raw], '2026-10-06': [raw, {'itemId': 'another'}]})
        self.assertEqual(len(items), 2)
        item = next(item for item in items if item.item_id == 'private-identity')
        self.assertEqual(item.day, date(2026,10,6))
        self.assertEqual(item.planned_delivery, date(2026,10,7))
        self.assertEqual(item.key, parse_mail_items({'2026-10-06': [raw]})[0].key)
        for value in ('private-identity','private-sender','private-signature','private-reference'):
            self.assertNotIn(value, repr(item))
            self.assertNotIn(value, item.key)

    def test_malformed_lists_never_become_empty_inboxes(self):
        for value in (None, [], {'not-a-date': []}, {'2026-10-06': {}},
                      {'2026-10-06': [None]}, {'2026-10-06': [{'imageUrl':'a'}]}):
            with self.subTest(value=value), self.assertRaises(BpostApiError):
                parse_mail_items(value)
        self.assertEqual(parse_mail_items({}), [])

    def test_scan_address_constraints_and_signature_preserved(self):
        for url in ('http://scan.bpost.be/a', 'https://localhost/a', 'https://127.0.0.1/a',
                    'https://bpost.be.evil.invalid/a', 'https://bpost.be@evil.invalid/a',
                    'https://user@scan.bpost.be/a', 'https://scan.bpost.be:8443/a',
                    'file:///tmp/private', 'https://scan.bpost.be/a#secret'):
            with self.subTest(url=url), self.assertRaises(BpostApiError):
                _mail_image_url(url)
        url = 'https://synthetic.blob.core.windows.net/mail/a?sig=a%2Fb%3Dc&x=1+2'
        self.assertEqual(_mail_image_url(url), url)


class MailClientTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        self.summary = {'status':'success', 'response':{'isMMTSubscribed':True}}
        self.letters = {'status':'success', 'response':{'images':{}}}
        self.status, self.content_type, self.content = 200, 'image/png', PNG
        self.chunked = False
        self.headers = {}
        app = web.Application()
        app.router.add_route('*', '/{path:.*}', self.handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.base = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/'
        self.base_patch = patch('pybpost.client.BASE_URL', self.base)
        self.base_patch.start()
        self.session = aiohttp.ClientSession(headers={'Authorization':'private-account-default'}, cookies={'account':'private-cookie'})
        self.client = BpostClient(self.session, tokens=AuthTokens('private-token','private-refresh'))

    async def asyncTearDown(self):
        await self.client.close()
        await self.session.close()
        await self.runner.cleanup()
        self.base_patch.stop()

    async def handle(self, request):
        self.calls.append((request.method, request.path, dict(request.headers), await request.json() if request.method == 'POST' else None))
        if request.path == '/mails/getmailsummary':
            return web.json_response(self.summary)
        if request.path == '/mmt/retrieveImages':
            return web.json_response(self.letters)
        if self.chunked:
            response = web.StreamResponse(status=self.status, headers={'Content-Type':self.content_type})
            await response.prepare(request)
            await response.write(self.content)
            await response.write_eof()
            return response
        return web.Response(status=self.status, body=self.content, content_type=self.content_type, headers=self.headers)

    async def fetch_image(self):
        # Validate the real HTTPS destination, then route its transport to our local
        # HTTP fixture. URL validation itself is exercised separately above.
        def fixture_url(url):
            _mail_image_url(url)
            return self.base + 'scan'
        with patch('pybpost.client._mail_image_url', side_effect=fixture_url):
            return await self.client.get_mail_image('https://scan.bpost.be/a?sig=private-signature')

    async def test_mail_api_contract_and_invalid_envelopes(self):
        self.assertTrue((await self.client.get_mail_summary())['isMMTSubscribed'])
        self.assertEqual(await self.client.get_letters(date(2026,9,7),date(2026,10,6)), [])
        self.assertEqual(self.calls[-1][3], {'appLang':'fr','fromDate':'2026-09-07','toDate':'2026-10-06'})
        self.assertEqual(self.calls[-1][2]['Authorization'], 'private-token')
        self.summary = {'status':'error','response':{}}
        with self.assertRaises(BpostApiError):
            await self.client.get_mail_summary()
        self.letters = {'status':'success','response':{}}
        with self.assertRaises(BpostApiError):
            await self.client.get_letters(date(2026,10,5),date(2026,10,6))

    async def test_scan_uses_isolated_session_without_account_headers_or_cookies(self):
        content, mime = await self.fetch_image()
        self.assertEqual((content,mime), (PNG,'image/png'))
        headers = {key.lower():value for key,value in self.calls[-1][2].items()}
        for forbidden in ('authorization','x-api-key','cookie','applang'):
            self.assertNotIn(forbidden,headers)
        image_session = self.client._image_session
        await self.client.close()
        self.assertTrue(image_session.closed)
        self.assertFalse(self.session.closed)

    async def test_scan_redirect_is_not_followed(self):
        self.status = 302
        self.headers = {'Location': self.base+'private'}
        with self.assertRaises(BpostApiError) as caught:
            await self.fetch_image()
        self.assertEqual(len(self.calls),1)
        self.assertNotIn('private',str(caught.exception))

    async def test_scan_size_mime_and_signature_limits(self):
        for mime, content in [('image/svg+xml',b'<svg/>'),('image/png',b'<html/>'),('text/html',PNG)]:
            self.content_type,self.content = mime,content
            with self.assertRaises(BpostApiError):
                await self.fetch_image()
        self.content_type,self.content = 'image/png',PNG * 4
        for chunked in (False,True):
            self.chunked = chunked
            with patch('pybpost.client.MAX_MAIL_IMAGE_BYTES',32), self.assertRaises(BpostApiError):
                await self.fetch_image()

    async def test_scan_rate_limit_also_pauses_account(self):
        self.status,self.headers = 429,{'Retry-After':'120'}
        with self.assertRaises(BpostRateLimitError):
            await self.fetch_image()
        with self.assertRaises(BpostRateLimitError):
            await self.client.get_mail_summary()
        self.assertEqual(len(self.calls),1)

    async def test_invalid_date_range_does_not_request(self):
        with self.assertRaises(ValueError):
            await self.client.get_letters(date(2026,10,6),date(2026,10,5))
        self.assertEqual(self.calls,[])
