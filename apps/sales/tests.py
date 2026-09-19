import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.sales import services
from apps.sales.models import SalesInvoice, NozzleSale
from apps.stations.models import Station, Product, Tank, Nozzle
from apps.workday.models import DailyWorkingDay

User = get_user_model()


class NozzleSaleCalculationTests(TestCase):
    def setUp(self):
        station = Station.objects.create(name="S", province="P", city="C")
        product = Product.objects.create(name="Regular")
        self.tank = Tank.objects.create(station=station, product=product, capacity=1000)
        self.nozzle = Nozzle.objects.create(tank=self.tank, number=1)
        self.user = User.objects.create_user(username="op", password="x")
        self.working_day = DailyWorkingDay.objects.create(date=datetime.date(2026, 8, 1))
        self.invoice = SalesInvoice.objects.create(working_day=self.working_day, operator=self.user)

    def test_operation_and_mechanical_sales_spec_example(self):
        # Spec example: New=10000, Previous=9000, Test=20 -> Operation=1000,
        # Mechanical Sales=980.
        sale = NozzleSale.objects.create(
            sales_invoice=self.invoice,
            nozzle=self.nozzle,
            previous_meter=Decimal("9000"),
            new_meter=Decimal("10000"),
            test=Decimal("20"),
            sales_rate=Decimal("1200"),
        )
        self.assertEqual(sale.operation, Decimal("1000"))
        self.assertEqual(sale.mechanical_sales, Decimal("980"))
        self.assertEqual(sale.sales_amount, Decimal("980"))
        self.assertEqual(sale.total_amount, Decimal("980") * Decimal("1200"))

    def test_zero_test_means_mechanical_sales_equals_operation(self):
        sale = NozzleSale.objects.create(
            sales_invoice=self.invoice,
            nozzle=self.nozzle,
            previous_meter=Decimal("100"),
            new_meter=Decimal("150"),
            test=Decimal("0"),
            sales_rate=Decimal("1200"),
        )
        self.assertEqual(sale.operation, Decimal("50"))
        self.assertEqual(sale.mechanical_sales, Decimal("50"))

    def test_non_operating_nozzle_is_all_zero(self):
        sale = NozzleSale.objects.create(
            sales_invoice=self.invoice,
            nozzle=self.nozzle,
            previous_meter=Decimal("500"),
            new_meter=Decimal("500"),
            test=Decimal("0"),
            sales_rate=Decimal("1200"),
        )
        self.assertEqual(sale.operation, Decimal("0"))
        self.assertEqual(sale.mechanical_sales, Decimal("0"))
        self.assertEqual(sale.total_amount, Decimal("0"))

    def test_negative_meter_movement_still_calculates(self):
        """A new meter lower than previous is a warning, not a rejection --
        the calculation must still be performed per the spec."""
        sale = NozzleSale.objects.create(
            sales_invoice=self.invoice,
            nozzle=self.nozzle,
            previous_meter=Decimal("1000"),
            new_meter=Decimal("900"),
            test=Decimal("0"),
            sales_rate=Decimal("1200"),
        )
        self.assertEqual(sale.operation, Decimal("-100"))


class ProductSalesAggregationTests(TestCase):
    def setUp(self):
        station = Station.objects.create(name="S", province="P", city="C")
        self.product = Product.objects.create(name="Regular")
        self.tank = Tank.objects.create(station=station, product=self.product, capacity=1000)
        self.nozzle1 = Nozzle.objects.create(tank=self.tank, number=1)
        self.nozzle2 = Nozzle.objects.create(tank=self.tank, number=2)
        self.user = User.objects.create_user(username="op", password="x")
        self.working_day = DailyWorkingDay.objects.create(date=datetime.date(2026, 8, 1))
        self.invoice = SalesInvoice.objects.create(working_day=self.working_day, operator=self.user)

    def test_product_sales_sums_all_nozzles_of_that_tank(self):
        NozzleSale.objects.create(
            sales_invoice=self.invoice, nozzle=self.nozzle1,
            previous_meter=0, new_meter=100, test=0, sales_rate=Decimal("1200"),
        )
        NozzleSale.objects.create(
            sales_invoice=self.invoice, nozzle=self.nozzle2,
            previous_meter=0, new_meter=50, test=0, sales_rate=Decimal("1200"),
        )
        total = services.get_product_sales(self.tank, self.working_day)
        self.assertEqual(total, Decimal("150"))


class ValidateAllNozzlesRegisteredTests(TestCase):
    def setUp(self):
        station = Station.objects.create(name="S", province="P", city="C")
        product = Product.objects.create(name="Regular")
        self.tank = Tank.objects.create(station=station, product=product, capacity=1000)
        self.n1 = Nozzle.objects.create(tank=self.tank, number=1)
        self.n2 = Nozzle.objects.create(tank=self.tank, number=2)
        self.user = User.objects.create_user(username="op", password="x")
        self.working_day = DailyWorkingDay.objects.create(date=datetime.date(2026, 8, 1))

    def test_missing_nozzle_detected(self):
        invoice = SalesInvoice.objects.create(working_day=self.working_day, operator=self.user)
        NozzleSale.objects.create(
            sales_invoice=invoice, nozzle=self.n1, previous_meter=0, new_meter=10, test=0,
            sales_rate=Decimal("1200"),
        )
        complete, missing = services.validate_all_nozzles_registered(self.working_day)
        self.assertFalse(complete)
        self.assertEqual(missing, [2])

    def test_all_nozzles_registered(self):
        invoice = SalesInvoice.objects.create(working_day=self.working_day, operator=self.user)
        for n in (self.n1, self.n2):
            NozzleSale.objects.create(
                sales_invoice=invoice, nozzle=n, previous_meter=0, new_meter=0, test=0,
                sales_rate=Decimal("1200"),
            )
        complete, missing = services.validate_all_nozzles_registered(self.working_day)
        self.assertTrue(complete)
        self.assertEqual(missing, [])


class GetPreviousNewMeterTests(TestCase):
    """
    get_previous_new_meter() suggests Previous Meter exactly the way
    get_most_recent_rate() suggests سری/sales_rate: it returns the value
    to pre-fill, never anything about locking the field.
    """

    def setUp(self):
        station = Station.objects.create(name="S", province="P", city="C")
        product = Product.objects.create(name="Regular")
        self.tank = Tank.objects.create(station=station, product=product, capacity=1000)
        self.nozzle = Nozzle.objects.create(tank=self.tank, number=1)
        self.other_nozzle = Nozzle.objects.create(tank=self.tank, number=2)
        self.user = User.objects.create_user(username="op", password="x")

    def test_returns_none_when_nozzle_has_no_prior_entries(self):
        self.assertIsNone(services.get_previous_new_meter(self.nozzle))

    def test_returns_new_meter_of_the_only_prior_entry(self):
        wd1 = DailyWorkingDay.objects.create(date=datetime.date(2026, 8, 1))
        invoice1 = SalesInvoice.objects.create(working_day=wd1, operator=self.user)
        NozzleSale.objects.create(
            sales_invoice=invoice1, nozzle=self.nozzle,
            previous_meter=Decimal("0"), new_meter=Decimal("150"), test=Decimal("0"),
            sales_rate=Decimal("1200"),
        )
        self.assertEqual(services.get_previous_new_meter(self.nozzle), Decimal("150"))

    def test_returns_new_meter_of_the_chronologically_latest_entry(self):
        wd1 = DailyWorkingDay.objects.create(date=datetime.date(2026, 8, 1))
        wd2 = DailyWorkingDay.objects.create(date=datetime.date(2026, 8, 2))
        invoice1 = SalesInvoice.objects.create(working_day=wd1, operator=self.user)
        invoice2 = SalesInvoice.objects.create(working_day=wd2, operator=self.user)
        NozzleSale.objects.create(
            sales_invoice=invoice1, nozzle=self.nozzle,
            previous_meter=Decimal("0"), new_meter=Decimal("150"), test=Decimal("0"),
            sales_rate=Decimal("1200"),
        )
        NozzleSale.objects.create(
            sales_invoice=invoice2, nozzle=self.nozzle,
            previous_meter=Decimal("150"), new_meter=Decimal("300"), test=Decimal("0"),
            sales_rate=Decimal("1200"),
        )
        self.assertEqual(services.get_previous_new_meter(self.nozzle), Decimal("300"))

    def test_independent_per_nozzle(self):
        wd1 = DailyWorkingDay.objects.create(date=datetime.date(2026, 8, 1))
        invoice1 = SalesInvoice.objects.create(working_day=wd1, operator=self.user)
        NozzleSale.objects.create(
            sales_invoice=invoice1, nozzle=self.nozzle,
            previous_meter=Decimal("0"), new_meter=Decimal("150"), test=Decimal("0"),
            sales_rate=Decimal("1200"),
        )
        # A different nozzle with no entries of its own must not see the
        # first nozzle's suggested meter.
        self.assertIsNone(services.get_previous_new_meter(self.other_nozzle))


# ---------------------------------------------------------------------------
# HTTP-level integration tests for the sequential nozzle entry workflow.
# ---------------------------------------------------------------------------

from django.contrib.auth import get_user_model as _get_user_model
from django.test import TestCase as _TestCase

from apps.license.models import License as _License
from apps.workday.models import DailyWorkingDay as _DailyWorkingDay

_User = _get_user_model()


class SequentialNozzleEntryHttpTests(_TestCase):
    def setUp(self):
        self.user = _User.objects.create_user(username="op1", password="testpass123")
        _License.objects.create(start_date=datetime.date(2026, 8, 1), duration_days=365)
        station = Station.objects.create(name="S", province="P", city="C")
        product = Product.objects.create(name="Regular")
        self.tank = Tank.objects.create(station=station, product=product, capacity=50000)
        Nozzle.objects.create(tank=self.tank, number=1)
        Nozzle.objects.create(tank=self.tank, number=2)
        self.client.login(username="op1", password="testpass123")
        self.date = "2026-08-01"

    def test_nozzle_entry_next_redirects_to_first_nozzle(self):
        resp = self.client.get(f"/sales/invoices/{self.date}/nozzle/")
        self.assertRedirects(resp, f"/sales/invoices/{self.date}/nozzle/1/")

    def test_saving_first_nozzle_advances_to_second(self):
        resp = self.client.post(
            f"/sales/invoices/{self.date}/nozzle/1/",
            {"previous_meter": "0", "new_meter": "100", "test": "0", "sales_rate": "1200"},
        )
        self.assertRedirects(resp, f"/sales/invoices/{self.date}/nozzle/2/")

    def test_saving_last_nozzle_redirects_to_invoice_detail(self):
        self.client.post(
            f"/sales/invoices/{self.date}/nozzle/1/",
            {"previous_meter": "0", "new_meter": "100", "test": "0", "sales_rate": "1200"},
        )
        resp = self.client.post(
            f"/sales/invoices/{self.date}/nozzle/2/",
            {"previous_meter": "0", "new_meter": "50", "test": "0", "sales_rate": "1200"},
        )
        self.assertRedirects(resp, f"/sales/invoices/{self.date}/")

    def test_negative_meter_shows_warning_without_saving(self):
        resp = self.client.post(
            f"/sales/invoices/{self.date}/nozzle/1/",
            {"previous_meter": "1000", "new_meter": "900", "test": "0", "sales_rate": "1200"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "هشدار")
        self.assertEqual(NozzleSale.objects.filter(nozzle__number=1).count(), 0)

    def test_confirming_negative_meter_saves(self):
        self.client.post(
            f"/sales/invoices/{self.date}/nozzle/1/",
            {"previous_meter": "1000", "new_meter": "900", "test": "0", "sales_rate": "1200"},
        )
        resp = self.client.post(
            f"/sales/invoices/{self.date}/nozzle/1/",
            {
                "previous_meter": "1000", "new_meter": "900", "test": "0", "sales_rate": "1200",
                "confirm_negative_meter": "1",
            },
        )
        self.assertEqual(NozzleSale.objects.filter(nozzle__number=1).count(), 1)
        sale = NozzleSale.objects.get(nozzle__number=1)
        self.assertEqual(sale.operation, Decimal("-100"))

    def test_invoice_detail_shows_missing_nozzles_warning(self):
        self.client.post(
            f"/sales/invoices/{self.date}/nozzle/1/",
            {"previous_meter": "0", "new_meter": "100", "test": "0", "sales_rate": "1200"},
        )
        resp = self.client.get(f"/sales/invoices/{self.date}/")
        self.assertContains(resp, "2")  # missing nozzle number shown

    def test_future_date_entry_blocked(self):
        resp = self.client.post(
            f"/sales/invoices/2099-01-01/nozzle/1/",
            {"previous_meter": "0", "new_meter": "100", "test": "0", "sales_rate": "1200"},
            follow=True,
        )
        self.assertContains(resp, "آینده")

    def test_date_before_accounting_start_blocked(self):
        resp = self.client.post(
            f"/sales/invoices/2026-07-15/nozzle/1/",
            {"previous_meter": "0", "new_meter": "100", "test": "0", "sales_rate": "1200"},
            follow=True,
        )
        self.assertContains(resp, "خارج")

    def test_editing_existing_nozzle_sale_does_not_duplicate(self):
        self.client.post(
            f"/sales/invoices/{self.date}/nozzle/1/",
            {"previous_meter": "0", "new_meter": "100", "test": "0", "sales_rate": "1200"},
        )
        self.client.post(
            f"/sales/invoices/{self.date}/nozzle/1/",
            {"previous_meter": "0", "new_meter": "150", "test": "0", "sales_rate": "1200"},
        )
        self.assertEqual(NozzleSale.objects.filter(nozzle__number=1).count(), 1)
        self.assertEqual(NozzleSale.objects.get(nozzle__number=1).new_meter, Decimal("150"))


class PreviousMeterSuggestionHttpTests(_TestCase):
    """
    Previous Meter is suggested (pre-filled) from this same nozzle's
    prior New Meter exactly like سری/sales_rate is suggested -- a normal,
    always-editable field, never read-only/locked.
    """

    def setUp(self):
        self.user = _User.objects.create_user(username="op1", password="testpass123")
        _License.objects.create(start_date=datetime.date(2026, 8, 1), duration_days=365)
        station = Station.objects.create(name="S", province="P", city="C")
        product = Product.objects.create(name="Regular")
        self.tank = Tank.objects.create(station=station, product=product, capacity=50000)
        Nozzle.objects.create(tank=self.tank, number=1)
        Nozzle.objects.create(tank=self.tank, number=2)
        self.client.login(username="op1", password="testpass123")

    def test_first_entry_ever_leaves_previous_meter_blank(self):
        resp = self.client.get("/sales/invoices/2026-08-01/nozzle/1/")
        self.assertNotContains(resp, 'value="0.00"')
        self.assertNotContains(resp, "readonly")

    def test_second_day_prefills_previous_meter_from_prior_new_meter(self):
        self.client.post(
            "/sales/invoices/2026-08-01/nozzle/1/",
            {"previous_meter": "0", "new_meter": "150", "test": "0", "sales_rate": "1200"},
        )
        resp = self.client.get("/sales/invoices/2026-08-02/nozzle/1/")
        self.assertContains(resp, 'value="150.00"')

    def test_prefilled_previous_meter_field_is_never_readonly(self):
        self.client.post(
            "/sales/invoices/2026-08-01/nozzle/1/",
            {"previous_meter": "0", "new_meter": "150", "test": "0", "sales_rate": "1200"},
        )
        resp = self.client.get("/sales/invoices/2026-08-02/nozzle/1/")
        self.assertNotContains(resp, "readonly")

    def test_operator_can_override_the_suggested_previous_meter(self):
        self.client.post(
            "/sales/invoices/2026-08-01/nozzle/1/",
            {"previous_meter": "0", "new_meter": "150", "test": "0", "sales_rate": "1200"},
        )
        # The operator types a different value than the one suggested --
        # since the field is a normal editable input, this must be
        # accepted and saved as-is, exactly like overriding sales_rate.
        self.client.post(
            "/sales/invoices/2026-08-02/nozzle/1/",
            {"previous_meter": "160", "new_meter": "300", "test": "0", "sales_rate": "1200"},
        )
        wd2_sale = NozzleSale.objects.get(
            nozzle__number=1, sales_invoice__working_day__date=datetime.date(2026, 8, 2)
        )
        self.assertEqual(wd2_sale.previous_meter, Decimal("160"))

    def test_suggestion_is_independent_per_nozzle(self):
        self.client.post(
            "/sales/invoices/2026-08-01/nozzle/1/",
            {"previous_meter": "0", "new_meter": "150", "test": "0", "sales_rate": "1200"},
        )
        # Nozzle 2 has never been entered -- must stay blank on this same
        # working day, unaffected by nozzle 1's history.
        resp = self.client.get("/sales/invoices/2026-08-01/nozzle/2/")
        self.assertNotContains(resp, 'value="150.00"')

    def test_third_day_prefills_from_second_days_new_meter(self):
        self.client.post(
            "/sales/invoices/2026-08-01/nozzle/1/",
            {"previous_meter": "0", "new_meter": "150", "test": "0", "sales_rate": "1200"},
        )
        self.client.post(
            "/sales/invoices/2026-08-02/nozzle/1/",
            {"previous_meter": "150", "new_meter": "300", "test": "0", "sales_rate": "1200"},
        )
        resp = self.client.get("/sales/invoices/2026-08-03/nozzle/1/")
        self.assertContains(resp, 'value="300.00"')
