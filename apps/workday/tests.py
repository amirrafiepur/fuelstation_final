"""
Chronology tests -- covering the corrected "accounting month start" rule
and basic future/past-date enforcement.
"""

import datetime

from django.test import TestCase
from django.utils import timezone

from apps.license.models import License
from apps.workday import services


class AccountingStartDateTests(TestCase):
    def test_no_license_means_no_accounting_start(self):
        self.assertIsNone(services.get_accounting_start_date())

    def test_mid_month_activation_sets_start_to_day_one(self):
        License.objects.create(start_date=datetime.date(2026, 8, 15), duration_days=365)
        self.assertEqual(
            services.get_accounting_start_date(), datetime.date(2026, 8, 1)
        )

    def test_day_one_activation_sets_start_to_same_day(self):
        License.objects.create(start_date=datetime.date(2026, 8, 1), duration_days=365)
        self.assertEqual(
            services.get_accounting_start_date(), datetime.date(2026, 8, 1)
        )


class CanEnterDateTests(TestCase):
    def setUp(self):
        License.objects.create(start_date=datetime.date(2026, 8, 15), duration_days=365)

    def test_future_date_rejected(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        allowed, reason = services.can_enter_date(tomorrow)
        self.assertFalse(allowed)
        self.assertIn("آینده", reason)

    def test_date_before_accounting_start_rejected(self):
        allowed, reason = services.can_enter_date(datetime.date(2026, 7, 31))
        self.assertFalse(allowed)

    def test_date_on_accounting_start_allowed(self):
        allowed, _ = services.can_enter_date(datetime.date(2026, 8, 1))
        self.assertTrue(allowed)

    def test_date_between_start_and_activation_allowed(self):
        allowed, _ = services.can_enter_date(datetime.date(2026, 8, 10))
        self.assertTrue(allowed)


class IncompleteDaysTests(TestCase):
    def test_mid_month_activation_creates_missing_days_from_day_one(self):
        License.objects.create(start_date=datetime.date(2026, 8, 15), duration_days=365)
        missing = services.get_incomplete_days(up_to=datetime.date(2026, 8, 15))
        self.assertEqual(missing[0], datetime.date(2026, 8, 1))
        self.assertEqual(missing[-1], datetime.date(2026, 8, 15))
        self.assertEqual(len(missing), 15)

    def test_closing_a_day_removes_it_from_missing_list(self):
        License.objects.create(start_date=datetime.date(2026, 8, 15), duration_days=365)
        services.close_day(datetime.date(2026, 8, 1))
        missing = services.get_incomplete_days(up_to=datetime.date(2026, 8, 2))
        self.assertNotIn(datetime.date(2026, 8, 1), missing)
        self.assertIn(datetime.date(2026, 8, 2), missing)

    def test_deleting_reopens_the_day(self):
        License.objects.create(start_date=datetime.date(2026, 8, 15), duration_days=365)
        services.close_day(datetime.date(2026, 8, 1))
        services.reopen_day_on_delete(datetime.date(2026, 8, 1))
        missing = services.get_incomplete_days(up_to=datetime.date(2026, 8, 1))
        self.assertIn(datetime.date(2026, 8, 1), missing)


class LastDayOfMonthTests(TestCase):
    def test_february_non_leap(self):
        self.assertEqual(
            services.last_day_of_month(datetime.date(2026, 2, 5)),
            datetime.date(2026, 2, 28),
        )

    def test_february_leap(self):
        self.assertEqual(
            services.last_day_of_month(datetime.date(2028, 2, 5)),
            datetime.date(2028, 2, 29),
        )

    def test_31_day_month(self):
        self.assertEqual(
            services.last_day_of_month(datetime.date(2026, 8, 5)),
            datetime.date(2026, 8, 31),
        )
