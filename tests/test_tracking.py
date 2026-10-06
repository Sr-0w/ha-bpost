"""Public tracking protocol and transport using synthetic data only."""

import json
import unittest
from unittest.mock import patch

from aiohttp import web

from pybpost.exceptions import BpostApiError, BpostRateLimitError
from pybpost.tracking import PublicTrackingClient, BpostTrackingNotFound, parse_tracking, tracking_inputs


def payload(code="TEST-PARCEL"):
    return {"items": [{"itemCode": code, "activeStep": {"knownProcessStep": "out_for_delivery_byCar"},
        "senderCommercialName": "Fictional shop", "receiver": {"postcode": "private-postcode"},
        "events": [{"date": "06/10/2026", "time": "09:30", "key": {
            "FR": {"description": "En livraison"}, "EN": {"description": "Out for delivery"}},
            "location": {"locationName": "Fictional depot"}}]}]}


class TrackingModelsTest(unittest.TestCase):
    def test_public_model_localization_and_private_fields(self):
        detail = parse_tracking(payload(), "TEST-PARCEL")
        self.assertEqual(detail.canonical_status, "out_for_delivery")
        self.assertEqual(detail.current_status, "out_for_delivery_byCar")
        self.assertEqual(detail.last_event.description, "En livraison")
        self.assertEqual(detail.last_event.date, "2026-10-06")
        self.assertEqual(detail.last_event.location, "Fictional depot")
        self.assertIsNone(detail.receiver.postcode)
        self.assertEqual(detail.raw, {})
        self.assertEqual(parse_tracking(payload(), "TEST-PARCEL", "de").last_event.description, "Out for delivery")

    def test_delivered_evidence_and_unknown_states(self):
        data = payload()
        data["items"][0]["activeStep"] = {"knownProcessStep": "FUTURE_CODE"}
        self.assertEqual(parse_tracking(data,"TEST-PARCEL").canonical_status,"unknown")
        data["items"][0]["actualDeliveryInformation"] = {"actualDeliveryTime": {"day":"not-a-day"}}
        self.assertEqual(parse_tracking(data,"TEST-PARCEL").canonical_status,"unknown")
        data["items"][0]["actualDeliveryInformation"]["actualDeliveryTime"]["day"] = "2026-10-06"
        self.assertEqual(parse_tracking(data,"TEST-PARCEL").canonical_status,"delivered")
        data["items"][0]["activeStep"]["knownProcessStep"] = "RETURNED_TO_SENDER"
        self.assertEqual(parse_tracking(data,"TEST-PARCEL").canonical_status,"returned")

    def test_eta_uses_absolute_time_in_belgium(self):
        data=payload()
        data['items'][0]['expectedDeliveryTimeRange']={'time1':'2026-10-06T08:00:00Z','time2':'2026-10-06T10:00:00Z'}
        eta=parse_tracking(data,'TEST-PARCEL').eta
        self.assertEqual((eta.day,eta.time1,eta.time2),('2026-10-06','10:00','12:00'))
        data['items'][0]['expectedDeliveryTimeRange']={'time1':'10:00','time2':'12:00'}
        self.assertTrue(parse_tracking(data,'TEST-PARCEL').eta.is_empty)

    def test_empty_malformed_and_identity_mismatch_are_distinct(self):
        with self.assertRaises(BpostTrackingNotFound): parse_tracking({'items':[]},'TEST-PARCEL')
        for value in ([],{}, {'items':None},{'error':'private-body'}, {'items':[{}]},payload('OTHER')):
            with self.subTest(value=value),self.assertRaises(BpostApiError): parse_tracking(value,'TEST-PARCEL')
        relabelled=payload('NEW-CODE');relabelled['items'][0]['searchCode']='TEST-PARCEL'
        self.assertEqual(parse_tracking(relabelled,'TEST-PARCEL').item_code,'TEST-PARCEL')

    def test_input_normalization_preserves_carrier_identifier(self):
        self.assertEqual(tracking_inputs(' AbC-12 ',' ab1 2cd '),('AbC-12','AB1 2CD'))
        for code,postcode in (('', '1000'),('ab\ncd','1000'),('x',''),('x','!'),('x'*129,'1000')):
            with self.subTest(code=code),self.assertRaises(ValueError): tracking_inputs(code,postcode)


class TrackingClientTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests=[];self.body=json.dumps(payload());self.status=200;self.headers={}
        app=web.Application();app.router.add_get('/items',self.handle)
        self.runner=web.AppRunner(app);await self.runner.setup()
        site=web.TCPSite(self.runner,'127.0.0.1',0);await site.start()
        self.url=f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/items'
        self.url_patch=patch('pybpost.tracking.PUBLIC_TRACKING_URL',self.url);self.url_patch.start()
        self.client=PublicTrackingClient()

    async def asyncTearDown(self):
        await self.client.close();self.url_patch.stop();await self.runner.cleanup()

    async def handle(self,request):
        self.requests.append((dict(request.query),dict(request.headers)))
        return web.Response(text=self.body,status=self.status,headers={**self.headers,'Set-Cookie':'unwanted=private'})

    async def test_real_http_query_encoding_and_no_authentication_or_cookies(self):
        code='synthetic&other=value'
        self.body=json.dumps(payload(code))
        await self.client.get_parcel(code,'1000')
        await self.client.get_parcel(code,'1000')
        for query,headers in self.requests:
            self.assertEqual(query,{'itemIdentifier':code,'postalCode':'1000'})
            self.assertFalse({'authorization','cookie','x-api-key'} & {h.lower() for h in headers})
        session=self.client._session;await self.client.close();self.assertTrue(session.closed)

    async def test_rate_limit_blocks_followup_requests(self):
        self.status=429;self.headers={'Retry-After':'600'}
        for _ in range(2):
            with self.assertRaises(BpostRateLimitError) as caught:
                await self.client.get_parcel('TEST-PARCEL','1000')
            self.assertGreater(caught.exception.retry_after,590)
        self.assertEqual(len(self.requests),1)

    async def test_redirect_and_http_errors_never_follow_or_leak_body(self):
        for status in (302,401,403,404,503):
            self.status=status;self.headers={'Location':self.url};self.body='private-body'
            with self.subTest(status=status),self.assertRaises(BpostApiError) as caught:
                await self.client.get_parcel('TEST-PARCEL','1000')
            self.assertNotIn('private',str(caught.exception))
        self.assertEqual(len(self.requests),5)

    async def test_invalid_json_and_large_response_are_bounded(self):
        self.body='private invalid json'
        with self.assertRaises(BpostApiError) as caught:await self.client.get_parcel('TEST-PARCEL','1000')
        self.assertNotIn('private',str(caught.exception))
        self.body=json.dumps(payload())
        with patch('pybpost.tracking.MAX_RESPONSE_BYTES',10),self.assertRaises(BpostApiError):
            await self.client.get_parcel('TEST-PARCEL','1000')

    async def test_not_found_is_not_an_http_failure(self):
        self.body='{"items":[]}'
        with self.assertRaises(BpostTrackingNotFound):await self.client.get_parcel('TEST-PARCEL','1000')
