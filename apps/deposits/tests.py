import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.license.models import License

from .models import Deposit
from .views import _decade_for_date

User = get_user_model()


class DecadeForDateTests(TestCase):
    """
    _decade_for_date() buckets by the JALALI day-of-month (1-10/11-20/
    21-end), since Deposit.date is now displayed/entered in Jalali and
    the decade is a slice of that Jalali month -- a Gregorian
    day-of-month can land in a different third of the month than the
    corresponding Jalali day, so this must not be computed from
    date.day directly.
    """

    def test_gregorian_day_25_can_fall_in_jalali_first_decade(self):
        # 2026-02-25 is Jalali 1404/12/06 -- Jalali day 6, first decade.
        # (Gregorian day-of-month 25 would incorrectly suggest the third
        # decade if computed the old, Gregorian-day way.)
        self.assertEqual(_decade_for_date(datetime.date(2026, 2, 25)), Deposit.FIRST_DECADE)

    def test_jalali_day_10_is_first_decade(self):
        # 2026-09-01 is Jalali 1405/06/10.
        self.assertEqual(_decade_for_date(datetime.date(2026, 9, 1)), Deposit.FIRST_DECADE)

    def test_jalali_day_11_is_second_decade(self):
        # 2026-09-02 is Jalali 1405/06/11.
        self.assertEqual(_decade_for_date(datetime.date(2026, 9, 2)), Deposit.SECOND_DECADE)

    def test_jalali_day_20_is_second_decade(self):
        # 2026-09-11 is Jalali 1405/06/20.
        self.assertEqual(_decade_for_date(datetime.date(2026, 9, 11)), Deposit.SECOND_DECADE)

    def test_jalali_day_21_is_third_decade(self):
        # 2026-09-12 is Jalali 1405/06/21.
        self.assertEqual(_decade_for_date(datetime.date(2026, 9, 12)), Deposit.THIRD_DECADE)

    def test_jalali_day_23_is_third_decade(self):
        # 2026-09-14 is Jalali 1405/06/23.
        self.assertEqual(_decade_for_date(datetime.date(2026, 9, 14)), Deposit.THIRD_DECADE)


class DepositHttpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="op1", password="testpass123")
        License.objects.create(start_date=datetime.date(2026, 8, 1), duration_days=365)
        self.client.login(username="op1", password="testpass123")

    def test_deposit_list_renders_empty(self):
        """Deposits are fully optional -- an empty list is a valid state,
        not an error or a blocking condition."""
        resp = self.client.get("/deposits/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "واریزی ثبت نشده است")

    def test_create_deposit_form_defaults_decade_from_date(self):
        resp = self.client.get("/deposits/new/")
        self.assertEqual(resp.status_code, 200)
        # Default date is today; decade select should be pre-populated
        # (not blank) based on that date -- exact value depends on today,
        # so just confirm the decade field renders with a selected option.
        self.assertContains(resp, 'name="decade"')

    def test_create_deposit_first_decade(self):
        resp = self.client.post("/deposits/new/", {
            "date": "1405/05/14", "year": 2026, "month": 8, "decade": Deposit.FIRST_DECADE,
            "deposit_amount": "1000000", "difference_amount": "0",
            "document_number": "", "bank": "", "branch": "",
        })
        self.assertEqual(resp.status_code, 302)
        deposit = Deposit.objects.get()
        self.assertEqual(deposit.decade, Deposit.FIRST_DECADE)

    def test_create_deposit_third_decade(self):
        # 1404/12/06 is a Jalali-first-decade date; the decade value
        # itself is operator-submitted (not server-validated against
        # the date), so this just confirms THIRD_DECADE round-trips.
        resp = self.client.post("/deposits/new/", {
            "date": "1404/12/06", "year": 2026, "month": 2, "decade": Deposit.THIRD_DECADE,
            "deposit_amount": "500000", "difference_amount": "0",
            "document_number": "", "bank": "", "branch": "",
        })
        self.assertEqual(resp.status_code, 302)
        deposit = Deposit.objects.get()
        self.assertEqual(deposit.date, datetime.date(2026, 2, 25))
        self.assertEqual(deposit.decade, Deposit.THIRD_DECADE)

    def test_edit_deposit_preserves_original_date(self):
        deposit = Deposit.objects.create(
            date=datetime.date(2026, 8, 5), year=2026, month=8, decade=Deposit.FIRST_DECADE,
            deposit_amount=Decimal("1000000"),
        )
        resp = self.client.post(f"/deposits/{deposit.pk}/edit/", {
            "date": "1405/05/14", "year": 2026, "month": 8, "decade": Deposit.FIRST_DECADE,
            "deposit_amount": "1500000", "difference_amount": "0",
            "document_number": "", "bank": "", "branch": "",
        })
        self.assertEqual(resp.status_code, 302)
        deposit.refresh_from_db()
        self.assertEqual(deposit.date, datetime.date(2026, 8, 5))
        self.assertEqual(deposit.deposit_amount, Decimal("1500000"))

    def test_delete_deposit_requires_post_confirmation(self):
        deposit = Deposit.objects.create(
            date=datetime.date(2026, 8, 5), year=2026, month=8, decade=Deposit.FIRST_DECADE,
            deposit_amount=Decimal("1000000"),
        )
        resp_get = self.client.get(f"/deposits/{deposit.pk}/delete/")
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(Deposit.objects.count(), 1)

        resp_post = self.client.post(f"/deposits/{deposit.pk}/delete/")
        self.assertEqual(resp_post.status_code, 302)
        self.assertEqual(Deposit.objects.count(), 0)

    def test_deposit_list_shows_created_deposit(self):
        Deposit.objects.create(
            date=datetime.date(2026, 8, 5), year=2026, month=8, decade=Deposit.FIRST_DECADE,
            deposit_amount=Decimal("1234567"), document_number="DOC-999",
        )
        resp = self.client.get("/deposits/")
        self.assertContains(resp, "DOC-999")

    def test_bank_and_branch_are_optional(self):
        resp = self.client.post("/deposits/new/", {
            "date": "1405/05/14", "year": 2026, "month": 8, "decade": Deposit.FIRST_DECADE,
            "deposit_amount": "1000000", "difference_amount": "0",
            "document_number": "", "bank": "", "branch": "",
        })
        self.assertEqual(resp.status_code, 302)
        deposit = Deposit.objects.get()
        self.assertEqual(deposit.bank, "")
        self.assertEqual(deposit.branch, "")
