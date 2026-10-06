"""Stable state vocabulary and defensive live payload parsing."""

import unittest

from pybpost.models import LiveRoundStatus, DeliveryPoint
from pybpost.status import ParcelStatus, normalize_status


class StatusTest(unittest.TestCase):
    def test_spelling_variants(self):
        for code in ('OutForDelivery', 'OUT_FOR_DELIVERY', 'out_for_delivery', 'AROUND'):
            with self.subTest(code=code):
                self.assertEqual(normalize_status(code), ParcelStatus.OUT_FOR_DELIVERY)

    def test_return_is_not_recipient_delivery(self):
        self.assertEqual(normalize_status('DELIVERED_TO_SENDER'), ParcelStatus.RETURNED)
        self.assertEqual(normalize_status('ON_THE_WAY_TO_SENDER'), ParcelStatus.RETURNING)

    def test_unknown_codes_are_not_guessed(self):
        for code in (None, '', 'NotDelivered', 'NotOutForDelivery', 'new_backend_state'):
            with self.subTest(code=code):
                self.assertEqual(normalize_status(code), ParcelStatus.UNKNOWN)

    def test_specific_status_precedes_summary(self):
        self.assertEqual(normalize_status('DELIVERED', 'IN_TRANSIT'), ParcelStatus.DELIVERED)
        self.assertEqual(normalize_status('unrecognized', 'IN_TRANSIT'), ParcelStatus.IN_TRANSIT)

    def test_inactive_announcements_remain_registered(self):
        self.assertEqual(normalize_status('AnnouncementReceived'), ParcelStatus.REGISTERED)


class LiveModelTest(unittest.TestCase):
    def parse(self, round_info, **data):
        return LiveRoundStatus.from_chunk({'response': {'data': {
            'itemOnRoundStatus': round_info, **data}}})

    def test_zero_stops_is_real_data(self):
        result = self.parse({'nrOfStopsUntilTarget': 0})
        self.assertIsNotNone(result)
        self.assertEqual(result.stops_until_target, 0)

    def test_missing_or_malformed_chunk_is_unavailable(self):
        for payload in ({}, {'response': []}, {'response': {'data': []}},
                        {'response': {'data': {'itemOnRoundStatus': []}}}):
            with self.subTest(payload=payload):
                self.assertIsNone(LiveRoundStatus.from_chunk(payload))
        self.assertIsNone(self.parse({}))

    def test_invalid_numbers_are_absent(self):
        for value in ('NaN', 'inf', '-inf', True, -1, 1.5, 'n/a'):
            with self.subTest(value=value):
                result = self.parse({'nrOfStopsUntilTarget': value, 'estimatedDeliveryTimeWindow': '14:00–15:00'})
                self.assertIsNone(result.stops_until_target)

    def test_valid_coords_and_raw_progress(self):
        result = self.parse({'nrOfStopsUntilTarget': '7', 'progressUntilTarget': '64',
                             'lastKnownLocation': {'latitude': '50.85', 'longitude': '4.35'}})
        self.assertTrue(result.has_coords)
        self.assertEqual(result.stops_until_target, 7)
        self.assertEqual(result.progress_until_target, 64)  # No assumed percentage/fraction conversion.

    def test_invalid_coordinates_are_not_published(self):
        for latitude, longitude in ((91, 4), (50, 181), ('NaN', 4), (50, None)):
            with self.subTest(latitude=latitude, longitude=longitude):
                result = self.parse({'nrOfStopsUntilTarget': 2,
                                    'lastKnownLocation': {'latitude': latitude, 'longitude': longitude}})
                self.assertFalse(result.has_coords)
                self.assertIsNone(result.last_known_lat)
                self.assertIsNone(result.last_known_lon)

    def test_refresh_floor_and_server_guidance(self):
        for supplied, expected in ((5, 60), (300, 300), ('bad', 60), (float('inf'), 60)):
            with self.subTest(supplied=supplied):
                self.assertEqual(self.parse({'nrOfStopsUntilTarget': 2}, autoRefreshTimeInSeconds=supplied).auto_refresh_s, expected)

    def test_pickup_coordinate_validation(self):
        self.assertFalse(DeliveryPoint(latitude=float('nan'), longitude=4).has_coords)
        self.assertFalse(DeliveryPoint(latitude=95, longitude=4).has_coords)
        self.assertTrue(DeliveryPoint(latitude=0, longitude=0).has_coords)
