import datetime
from decimal import Decimal

from django.test import TestCase

from apps.purchases import services
from apps.purchases.models import PurchaseInvoice
from apps.stations.models import Station, Product, Tank
from apps.workday.models import DailyWorkingDay


class MultiplePurchasesPerDayTests(TestCase):
    def setUp(self):
        station = Station.objects.create(name="S", province="P", city="C")
        product = Product.objects.create(name="Regular")
        self.tank = Tank.objects.create(station=station, product=product, capacity=50000)
        self.working_day = DailyWorkingDay.objects.create(date=datetime.date(2026, 8, 1))

    def test_multiple_invoices_same_day_all_contribute(self):
        PurchaseInvoice.objects.create(
            working_day=self.working_day, tank=self.tank, quantity=3200, purchase_rate=Decimal("1000")
        )
        PurchaseInvoice.objects.create(
            working_day=self.working_day, tank=self.tank, quantity=3100, purchase_rate=Decimal("1000")
        )
        PurchaseInvoice.objects.create(
            working_day=self.working_day, tank=self.tank, quantity=3000, purchase_rate=Decimal("1000")
        )
        total = services.get_daily_purchase_total(self.tank, self.working_day)
        self.assertEqual(total, Decimal("9300"))

    def test_duplicate_business_document_numbers_allowed(self):
        PurchaseInvoice.objects.create(
            working_day=self.working_day, tank=self.tank, quantity=100,
            purchase_rate=Decimal("1000"), document_number="INV-001",
        )
        # Must not raise -- no uniqueness constraint on document_number.
        PurchaseInvoice.objects.create(
            working_day=self.working_day, tank=self.tank, quantity=200,
            purchase_rate=Decimal("1000"), document_number="INV-001",
        )
        self.assertEqual(
            PurchaseInvoice.objects.filter(document_number="INV-001").count(), 2
        )

    def test_duplicate_tanker_numbers_allowed(self):
        PurchaseInvoice.objects.create(
            working_day=self.working_day, tank=self.tank, quantity=100,
            purchase_rate=Decimal("1000"), tanker_number="12-ABC-34",
        )
        PurchaseInvoice.objects.create(
            working_day=self.working_day, tank=self.tank, quantity=100,
            purchase_rate=Decimal("1000"), tanker_number="12-ABC-34",
        )
        count = services.get_monthly_unloading_count(self.tank, 2026, 8)
        self.assertEqual(count, 2)


# ---------------------------------------------------------------------------
# HTTP-level integration tests for the Phase 5 purchase workflow, covering
# the ten mandatory rules from the Phase 5 requirements document.
# ---------------------------------------------------------------------------

from django.contrib.auth import get_user_model as _get_user_model
from django.test import TestCase as _TestCase

from apps.license.models import License as _License

_User = _get_user_model()


class PurchaseWorkflowHttpTests(_TestCase):
    def setUp(self):
        self.user = _User.objects.create_user(username="op1", password="testpass123")
        _License.objects.create(start_date=datetime.date(2026, 8, 1), duration_days=365)
        station = Station.objects.create(name="S", province="P", city="C")
        self.regular = Product.objects.create(name="Regular")
        self.super_ = Product.objects.create(name="Super")
        self.regular_tank = Tank.objects.create(station=station, product=self.regular, capacity=50000)
        self.super_tank = Tank.objects.create(station=station, product=self.super_, capacity=30000)
        self.client.login(username="op1", password="testpass123")
        self.date = "2026-08-01"

    # Rule 1: multiple invoices per day.
    def test_multiple_purchase_invoices_same_day_same_tank(self):
        for qty in (10000, 15000, 8000):
            resp = self.client.post(
                f"/purchases/{self.date}/tank/{self.regular_tank.id}/new/",
                {"quantity": qty, "purchase_rate": "1000"},
            )
            self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            PurchaseInvoice.objects.filter(tank=self.regular_tank, working_day__date=self.date).count(), 3
        )

    # Rule 7: derived daily total, using the exact spec example.
    def test_daily_total_matches_spec_example(self):
        for qty in (10000, 15000, 8000):
            self.client.post(
                f"/purchases/{self.date}/tank/{self.regular_tank.id}/new/",
                {"quantity": qty, "purchase_rate": "1000"},
            )
        working_day = DailyWorkingDay.objects.get(date=self.date)
        total = services.get_daily_purchase_total(self.regular_tank, working_day)
        self.assertEqual(total, Decimal("33000"))
        # Also verify the rendered list page shows it.
        resp = self.client.get(f"/purchases/{self.date}/")
        self.assertContains(resp, "33000")

    # Rule 2: duplicate document numbers accepted, no error/warning.
    def test_duplicate_document_number_accepted_via_form(self):
        r1 = self.client.post(
            f"/purchases/{self.date}/tank/{self.regular_tank.id}/new/",
            {"quantity": 100, "purchase_rate": "1000", "document_number": "INV-1"},
        )
        r2 = self.client.post(
            f"/purchases/{self.date}/tank/{self.regular_tank.id}/new/",
            {"quantity": 200, "purchase_rate": "1000", "document_number": "INV-1"},
        )
        self.assertEqual(r1.status_code, 302)
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(PurchaseInvoice.objects.filter(document_number="INV-1").count(), 2)

    # Rule 2: duplicate tanker numbers accepted, no error/warning.
    def test_duplicate_tanker_number_accepted_via_form(self):
        r1 = self.client.post(
            f"/purchases/{self.date}/tank/{self.regular_tank.id}/new/",
            {"quantity": 100, "purchase_rate": "1000", "tanker_number": "12-ABC-34"},
        )
        r2 = self.client.post(
            f"/purchases/{self.date}/tank/{self.regular_tank.id}/new/",
            {"quantity": 200, "purchase_rate": "1000", "tanker_number": "12-ABC-34"},
        )
        self.assertEqual(r1.status_code, 302)
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(PurchaseInvoice.objects.filter(tanker_number="12-ABC-34").count(), 2)

    # Rule 3: no capacity restriction -- an unusually large value must be accepted.
    def test_unrestricted_tanker_capacity_accepted(self):
        resp = self.client.post(
            f"/purchases/{self.date}/tank/{self.regular_tank.id}/new/",
            {"quantity": 100, "purchase_rate": "1000", "tanker_capacity": 999999},
        )
        self.assertEqual(resp.status_code, 302)
        invoice = PurchaseInvoice.objects.get(tanker_capacity=999999)
        self.assertEqual(invoice.tanker_capacity, 999999)

    # Rule 4: historical rate is frozen even after the suggested rate changes.
    def test_historical_purchase_rate_frozen_after_later_change(self):
        self.client.post(
            f"/purchases/{self.date}/tank/{self.regular_tank.id}/new/",
            {"quantity": 100, "purchase_rate": "1000"},
        )
        first_invoice = PurchaseInvoice.objects.get(quantity=100)

        # A later purchase uses a different rate.
        self.client.post(
            f"/purchases/{self.date}/tank/{self.regular_tank.id}/new/",
            {"quantity": 200, "purchase_rate": "1500"},
        )
        first_invoice.refresh_from_db()
        self.assertEqual(first_invoice.purchase_rate, Decimal("1000"))

    # Rule 5: rate suggestion uses the most recently used rate for that product.
    def test_rate_suggestion_uses_most_recent_rate_for_product(self):
        self.client.post(
            f"/purchases/{self.date}/tank/{self.regular_tank.id}/new/",
            {"quantity": 100, "purchase_rate": "1234"},
        )
        resp = self.client.get(f"/purchases/{self.date}/tank/{self.regular_tank.id}/new/")
        self.assertContains(resp, "1234")

    # Rule 6: Regular and Super rate suggestions are fully independent.
    def test_regular_and_super_rate_suggestions_independent(self):
        self.client.post(
            f"/purchases/{self.date}/tank/{self.regular_tank.id}/new/",
            {"quantity": 100, "purchase_rate": "1200"},
        )
        self.client.post(
            f"/purchases/{self.date}/tank/{self.super_tank.id}/new/",
            {"quantity": 100, "purchase_rate": "1500"},
        )
        # Changing Regular's most recent rate...
        self.client.post(
            f"/purchases/{self.date}/tank/{self.regular_tank.id}/new/",
            {"quantity": 50, "purchase_rate": "1800"},
        )
        # ...must not affect Super's suggested rate.
        super_suggestion = services.get_most_recent_rate(self.super_tank)
        self.assertEqual(super_suggestion, Decimal("1500"))
        regular_suggestion = services.get_most_recent_rate(self.regular_tank)
        self.assertEqual(regular_suggestion, Decimal("1800"))

    # Rule 8: purchases are optional and never block day completion.
    def test_day_with_no_purchases_can_still_be_closed(self):
        working_day = DailyWorkingDay.objects.get_or_create(date=datetime.date(2026, 8, 1))[0]
        self.assertEqual(
            PurchaseInvoice.objects.filter(working_day=working_day).count(), 0
        )
        # close_day() must succeed regardless -- no purchase requirement
        # is checked by workday services.
        from apps.workday import services as workday_services
        workday_services.close_day(datetime.date(2026, 8, 1))
        working_day.refresh_from_db()
        self.assertEqual(working_day.status, DailyWorkingDay.COMPLETE)

    # Rule 10: chronology -- future dates blocked for purchase entry too.
    def test_future_date_purchase_entry_blocked(self):
        resp = self.client.post(
            f"/purchases/2099-01-01/tank/{self.regular_tank.id}/new/",
            {"quantity": 100, "purchase_rate": "1000"},
            follow=True,
        )
        self.assertContains(resp, "آینده")
        self.assertEqual(PurchaseInvoice.objects.count(), 0)

    # Rule 10: chronology -- dates before accounting start blocked.
    def test_date_before_accounting_start_blocked_for_purchases(self):
        resp = self.client.post(
            f"/purchases/2026-07-15/tank/{self.regular_tank.id}/new/",
            {"quantity": 100, "purchase_rate": "1000"},
            follow=True,
        )
        self.assertContains(resp, "خارج")
        self.assertEqual(PurchaseInvoice.objects.count(), 0)

    # Rule 10: editing a historical purchase preserves its working_day.
    def test_editing_purchase_preserves_working_day(self):
        self.client.post(
            f"/purchases/{self.date}/tank/{self.regular_tank.id}/new/",
            {"quantity": 100, "purchase_rate": "1000"},
        )
        invoice = PurchaseInvoice.objects.get(quantity=100)
        original_working_day_id = invoice.working_day_id

        self.client.post(
            f"/purchases/{self.date}/invoice/{invoice.pk}/edit/",
            {"quantity": 150, "purchase_rate": "1000"},
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.working_day_id, original_working_day_id)
        self.assertEqual(invoice.quantity, 150)

    # Rule 9: the view layer never duplicates the aggregation formula --
    # it must produce identical results to calling the service directly.
    def test_view_and_service_aggregation_agree(self):
        for qty in (500, 700):
            self.client.post(
                f"/purchases/{self.date}/tank/{self.regular_tank.id}/new/",
                {"quantity": qty, "purchase_rate": "1000"},
            )
        working_day = DailyWorkingDay.objects.get(date=self.date)
        service_total = services.get_daily_purchase_total(self.regular_tank, working_day)
        resp = self.client.get(f"/purchases/{self.date}/")
        self.assertContains(resp, str(service_total))
