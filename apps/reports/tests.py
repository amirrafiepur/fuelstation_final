"""
Reports are read-only derived views over existing source-of-truth data.
These tests verify that:
1. Reports render without errors and show aggregated data.
2. Report numbers are computed on-the-fly from existing models, not stored.
3. Changes to source data (sales, purchases, inventory) immediately
   reflect in reports without needing cache invalidation.
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.license.models import License
from apps.stations.models import Station, Product, Tank, Nozzle
from apps.workday.models import DailyWorkingDay
from apps.sales.models import SalesInvoice, NozzleSale
from apps.purchases.models import PurchaseInvoice
from apps.inventory.models import TankInventory, OpeningInventory

User = get_user_model()


class ReportsHttpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="op1", password="testpass123")
        License.objects.create(start_date=datetime.date(2026, 8, 1), duration_days=365)
        station = Station.objects.create(name="S", province="P", city="C")
        self.product = Product.objects.create(name="Regular")
        self.tank = Tank.objects.create(station=station, product=self.product, capacity=50000)
        self.nozzle = Nozzle.objects.create(tank=self.tank, number=1)
        self.wd = DailyWorkingDay.objects.create(date=datetime.date(2026, 8, 1))
        self.client.login(username="op1", password="testpass123")

    def test_nozzle_ledger_renders(self):
        resp = self.client.get("/reports/nozzle-ledger/?nozzle_id=1")
        self.assertEqual(resp.status_code, 200)

    def test_nozzle_ledger_shows_nozzle_data(self):
        invoice = SalesInvoice.objects.create(working_day=self.wd, operator=self.user)
        NozzleSale.objects.create(
            sales_invoice=invoice, nozzle=self.nozzle,
            previous_meter=Decimal("0"), new_meter=Decimal("100"), test=Decimal("0"),
            sales_rate=Decimal("1200"),
        )
        # Explicit range around the working day (2026-08-01) rather than
        # relying on the view's "current month" default, which tracks
        # wall-clock time and would otherwise make this test flaky as
        # real time moves away from the seeded date.
        resp = self.client.get(
            "/reports/nozzle-ledger/"
            "?nozzle_id=1&start_date=2026-07-25&end_date=2026-08-05"
        )
        self.assertContains(resp, "100")  # operation, mechanical_sales, daily_total, cumulative_total (all same on day 1 since test=0)

    def test_nozzle_ledger_date_range_filter(self):
        invoice = SalesInvoice.objects.create(working_day=self.wd, operator=self.user)
        NozzleSale.objects.create(
            sales_invoice=invoice, nozzle=self.nozzle,
            previous_meter=Decimal("0"), new_meter=Decimal("100"), test=Decimal("0"),
            sales_rate=Decimal("1200"),
        )
        resp = self.client.get(
            "/reports/nozzle-ledger/"
            "?nozzle_id=1&start_date=2026-08-02&end_date=2026-08-31"
        )
        self.assertNotContains(resp, "100")  # outside range

    def test_nozzle_monthly_renders(self):
        resp = self.client.get("/reports/nozzle-monthly/?year=1405&month=5")
        self.assertEqual(resp.status_code, 200)

    def test_nozzle_monthly_aggregates_correctly(self):
        invoice = SalesInvoice.objects.create(working_day=self.wd, operator=self.user)
        NozzleSale.objects.create(
            sales_invoice=invoice, nozzle=self.nozzle,
            previous_meter=Decimal("0"), new_meter=Decimal("100"), test=Decimal("0"),
            sales_rate=Decimal("1200"),
        )
        # working_day date 2026-08-01 is Jalali 1405/05/10 -- year/month
        # here are Jalali, so this queries the Jalali month containing it.
        resp = self.client.get("/reports/nozzle-monthly/?year=1405&month=5")
        self.assertContains(resp, "100")  # total operation and total sales_amount
        self.assertContains(resp, "120000")  # total total_amount (100 * 1200)

    def test_nozzle_monthly_excludes_other_months(self):
        invoice = SalesInvoice.objects.create(working_day=self.wd, operator=self.user)
        NozzleSale.objects.create(
            sales_invoice=invoice, nozzle=self.nozzle,
            previous_meter=Decimal("0"), new_meter=Decimal("100"), test=Decimal("0"),
            sales_rate=Decimal("1200"),
        )
        # 1405/06 is a different Jalali month from the working day's 1405/05.
        resp = self.client.get("/reports/nozzle-monthly/?year=1405&month=6")
        self.assertNotContains(resp, "100")

    def test_petroleum_ledger_renders(self):
        resp = self.client.get("/reports/petroleum-ledger/?tank_id=1")
        self.assertEqual(resp.status_code, 200)

    def test_petroleum_ledger_shows_aggregations(self):
        PurchaseInvoice.objects.create(
            working_day=self.wd, tank=self.tank, quantity=Decimal("100"),
            purchase_rate=Decimal("1000"),
        )
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("0"),
            effective_month=datetime.date(2026, 8, 1),
        )
        TankInventory.objects.create(
            tank=self.tank, working_day=self.wd, actual_inventory=Decimal("100"),
        )
        # Explicit range -- see test_nozzle_ledger_shows_nozzle_data above
        # for why this can't rely on the view's "current month" default.
        resp = self.client.get(
            "/reports/petroleum-ledger/"
            "?tank_id=1&start_date=2026-07-25&end_date=2026-08-05"
        )
        self.assertContains(resp, "100")  # daily purchase

    def test_petroleum_monthly_renders(self):
        resp = self.client.get("/reports/petroleum-monthly/?year=1405&month=5")
        self.assertEqual(resp.status_code, 200)

    def test_petroleum_monthly_aggregates_purchases(self):
        PurchaseInvoice.objects.create(
            working_day=self.wd, tank=self.tank, quantity=Decimal("100"),
            purchase_rate=Decimal("1000"),
        )
        # working_day date 2026-08-01 is Jalali 1405/05/10.
        resp = self.client.get("/reports/petroleum-monthly/?year=1405&month=5")
        self.assertContains(resp, "100")  # total purchase

    def test_report_reflects_live_data_changes(self):
        """
        Verify that reports are truly derived views: changing source data
        immediately updates the report, no caching or duplication.
        """
        # Explicit range around the working day (2026-08-01) rather than
        # the view's "current month" default -- see
        # test_nozzle_ledger_shows_nozzle_data above.
        url = (
            "/reports/nozzle-ledger/"
            "?nozzle_id=1&start_date=2026-07-25&end_date=2026-08-05"
        )

        # First state: no sales -- the ledger's own empty-state message
        # (not a date string, which can coincidentally also appear in
        # the page header's global date control).
        resp1 = self.client.get(url)
        self.assertContains(resp1, "اطلاعاتی یافت نشد")

        # Add a sale
        invoice = SalesInvoice.objects.create(working_day=self.wd, operator=self.user)
        NozzleSale.objects.create(
            sales_invoice=invoice, nozzle=self.nozzle,
            previous_meter=Decimal("0"), new_meter=Decimal("100"), test=Decimal("0"),
            sales_rate=Decimal("1200"),
        )

        # Report immediately shows the new data
        resp2 = self.client.get(url)
        self.assertContains(resp2, "100.00")  # operation, mechanical_sales, daily_total, cumulative_total

        # Edit the sale
        sale = NozzleSale.objects.get(nozzle=self.nozzle)
        sale.new_meter = Decimal("150")
        sale.save()

        # Report immediately reflects the change in the table data
        resp3 = self.client.get(url)
        self.assertContains(resp3, "150.00")  # operation, mechanical_sales, daily_total, cumulative_total (updated)


# ---------------------------------------------------------------------------
# Phase 7 verification tests: focused checks against Architecture v3 rules
# that were not yet covered (beginning/end-of-month meter, Daily Total 1/2,
# beginning/ending monthly inventory, first-accounting-month backfill,
# frozen historical sales rate, shortage/overage consistency with
# TankInventory, and report recalculation after editing source data).
# ---------------------------------------------------------------------------

class Phase7RuleComplianceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="op2", password="testpass123")
        # Mid-month activation: 2026-08-15 is Jalali 1405/05/24 -- the
        # accounting start must be day 1 of THAT Jalali month, which is
        # Gregorian 2026-07-23 (Jalali 1405/05/01), not the 1st of the
        # Gregorian calendar month (2026-08-01).
        License.objects.create(start_date=datetime.date(2026, 8, 15), duration_days=365)
        station = Station.objects.create(name="S2", province="P", city="C")
        self.product = Product.objects.create(name="Regular2")
        self.tank = Tank.objects.create(station=station, product=self.product, capacity=50000)
        self.nozzle = Nozzle.objects.create(tank=self.tank, number=1)
        self.client.login(username="op2", password="testpass123")

    def _make_day(self, iso_date):
        return DailyWorkingDay.objects.create(date=datetime.date.fromisoformat(iso_date))

    def _make_sale(self, wd, previous_meter, new_meter, test=Decimal("0"), rate=Decimal("1200")):
        invoice = SalesInvoice.objects.get_or_create(working_day=wd, defaults={"operator": self.user})[0]
        return NozzleSale.objects.create(
            sales_invoice=invoice, nozzle=self.nozzle,
            previous_meter=previous_meter, new_meter=new_meter, test=test, sales_rate=rate,
        )

    # --- Rule 5: first-accounting-month backfill ---

    def test_monthly_reports_cover_full_calendar_month_despite_mid_month_activation(self):
        # Activation was 2026-08-15 (Jalali 1405/05/24), but the operator
        # backfills from 2026-07-23 (Jalali 1405/05/01) onward.
        # year/month args to nozzle_performance_monthly are Jalali.
        wd1 = self._make_day("2026-07-23")
        self._make_sale(wd1, Decimal("0"), Decimal("50"))
        from apps.reports import services as report_services
        report = report_services.nozzle_performance_monthly(self.nozzle, 1405, 5)
        self.assertIsNotNone(report)
        self.assertEqual(report["beginning_of_month_meter"], Decimal("0"))
        self.assertEqual(report["total_operation"], Decimal("50"))

    def test_accounting_start_is_jalali_month_day_1_not_activation_date(self):
        from apps.workday import services as workday_services
        start = workday_services.get_accounting_start_date()
        self.assertEqual(start, datetime.date(2026, 7, 23))

    # --- Rule 2: beginning/end-of-month meter ---

    def test_beginning_of_month_meter_is_first_accounting_month_day1_reading(self):
        # 2026-07-23 is Jalali 1405/05/01 -- day 1 of the accounting month.
        wd1 = self._make_day("2026-07-23")
        self._make_sale(wd1, Decimal("100"), Decimal("150"))
        from apps.reports import services as report_services
        report = report_services.nozzle_performance_monthly(self.nozzle, 1405, 5)
        self.assertEqual(report["beginning_of_month_meter"], Decimal("100"))

    def test_end_of_month_meter_is_latest_registered_reading(self):
        # Both dates are within Jalali 1405/05.
        wd1 = self._make_day("2026-07-23")
        wd2 = self._make_day("2026-07-24")
        self._make_sale(wd1, Decimal("100"), Decimal("150"))
        self._make_sale(wd2, Decimal("150"), Decimal("220"))
        from apps.reports import services as report_services
        report = report_services.nozzle_performance_monthly(self.nozzle, 1405, 5)
        self.assertEqual(report["end_of_month_meter"], Decimal("220"))

    def test_beginning_of_month_meter_for_second_month_uses_prior_months_ending_meter(self):
        # 2026-08-22 is the LAST day of Jalali 1405/05 (1405/05/31);
        # 2026-08-23 is the FIRST day of Jalali 1405/06 (1405/06/01) --
        # these straddle a real Jalali month boundary.
        wd_prev_month = self._make_day("2026-08-22")
        self._make_sale(wd_prev_month, Decimal("900"), Decimal("1000"))
        wd_next_month = self._make_day("2026-08-23")
        self._make_sale(wd_next_month, Decimal("1000"), Decimal("1050"))
        from apps.reports import services as report_services
        report = report_services.nozzle_performance_monthly(self.nozzle, 1405, 6)
        self.assertEqual(report["beginning_of_month_meter"], Decimal("1000"))

    def test_beginning_of_month_meter_not_hardcoded_reflects_actual_data(self):
        # Different starting meter must produce a different result --
        # proves this is derived, not a hardcoded/default value.
        # 2026-07-23 is Jalali 1405/05/01.
        wd1 = self._make_day("2026-07-23")
        self._make_sale(wd1, Decimal("54321"), Decimal("54400"))
        from apps.reports import services as report_services
        report = report_services.nozzle_performance_monthly(self.nozzle, 1405, 5)
        self.assertEqual(report["beginning_of_month_meter"], Decimal("54321"))

    # --- Rule 1: frozen historical sales rate reflected in reports ---

    def test_ledger_uses_frozen_historical_sales_rate_not_current_default(self):
        wd1 = self._make_day("2026-07-23")
        self._make_sale(wd1, Decimal("0"), Decimal("100"), rate=Decimal("1000"))
        # A later purchase/sale changes the "current" rate elsewhere, but
        # this historical record's rate must remain frozen at 1000.
        wd2 = self._make_day("2026-07-24")
        nozzle2 = Nozzle.objects.create(tank=self.tank, number=2)
        invoice2 = SalesInvoice.objects.create(working_day=wd2, operator=self.user)
        NozzleSale.objects.create(
            sales_invoice=invoice2, nozzle=nozzle2,
            previous_meter=Decimal("0"), new_meter=Decimal("50"), test=Decimal("0"),
            sales_rate=Decimal("1500"),
        )
        from apps.reports import services as report_services
        rows = report_services.nozzle_performance_ledger(
            self.nozzle, datetime.date(2026, 7, 23), datetime.date(2026, 8, 22)
        )
        self.assertEqual(rows[0]["sales_rate"], Decimal("1000"))
        self.assertEqual(rows[0]["total_amount"], Decimal("100000"))  # 100 * 1000

    # --- Rule 3: F6 Daily Total 1 / Daily Total 2, shortage/overage consistency ---

    def test_f6_daily_total_1_and_2_match_formula(self):
        wd1 = self._make_day("2026-07-23")
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("1000"),
            effective_month=datetime.date(2026, 7, 23),
        )
        PurchaseInvoice.objects.create(
            working_day=wd1, tank=self.tank, quantity=Decimal("100"),
            purchase_rate=Decimal("1200"),
        )
        self._make_sale(wd1, Decimal("0"), Decimal("205"), test=Decimal("5"))
        TankInventory.objects.create(tank=self.tank, working_day=wd1, actual_inventory=Decimal("905"))

        from apps.reports import services as report_services
        from apps.inventory import services as inventory_services

        rows = report_services.petroleum_inventory_operations_ledger(
            self.tank, datetime.date(2026, 7, 23), datetime.date(2026, 7, 23)
        )
        row = rows[0]

        total, theoretical, shortage, overage = inventory_services.compute_tank_inventory(self.tank, wd1)

        expected_total_1 = row["daily_purchase"] + row["test_return"] + overage
        expected_total_2 = row["daily_sales"] + row["test_return"] + shortage + Decimal("905")

        self.assertEqual(row["daily_total_1"], expected_total_1)
        self.assertEqual(row["daily_total_2"], expected_total_2)
        # Shortage/overage in the report must be identical to
        # TankInventory's own computation -- no second calculation.
        self.assertEqual(row["shortage"], shortage)
        self.assertEqual(row["overage"], overage)

    # --- Rule 4: beginning/ending monthly inventory, OpeningInventory=0 and non-zero ---

    def test_monthly_beginning_inventory_uses_opening_inventory_zero(self):
        wd1 = self._make_day("2026-07-23")
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("0"),
            effective_month=datetime.date(2026, 7, 23),
        )
        TankInventory.objects.create(tank=self.tank, working_day=wd1, actual_inventory=Decimal("0"))
        from apps.reports import services as report_services
        report = report_services.petroleum_inventory_monthly(self.tank, 1405, 5)
        self.assertEqual(report["beginning_inventory"], Decimal("0"))

    def test_monthly_beginning_inventory_uses_non_zero_opening_inventory(self):
        wd1 = self._make_day("2026-07-23")
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("5000"),
            effective_month=datetime.date(2026, 7, 23),
        )
        TankInventory.objects.create(tank=self.tank, working_day=wd1, actual_inventory=Decimal("5000"))
        from apps.reports import services as report_services
        report = report_services.petroleum_inventory_monthly(self.tank, 1405, 5)
        self.assertEqual(report["beginning_inventory"], Decimal("5000"))

    def test_monthly_beginning_inventory_second_month_uses_prior_months_ending_actual(self):
        # 2026-08-22 is the LAST day of Jalali 1405/05; 2026-08-23 is the
        # FIRST day of Jalali 1405/06 -- see the identical comment on
        # test_beginning_of_month_meter_for_second_month_uses_prior_months_ending_meter
        # above.
        wd_prev_month = self._make_day("2026-08-22")
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("0"),
            effective_month=datetime.date(2026, 7, 23),
        )
        TankInventory.objects.create(tank=self.tank, working_day=wd_prev_month, actual_inventory=Decimal("777"))
        wd_next_month = self._make_day("2026-08-23")
        TankInventory.objects.create(tank=self.tank, working_day=wd_next_month, actual_inventory=Decimal("800"))

        from apps.reports import services as report_services
        report = report_services.petroleum_inventory_monthly(self.tank, 1405, 6)
        self.assertEqual(report["beginning_inventory"], Decimal("777"))

    def test_monthly_ending_inventory_is_last_registered_actual_never_manual(self):
        wd1 = self._make_day("2026-07-23")
        wd2 = self._make_day("2026-07-24")
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("0"),
            effective_month=datetime.date(2026, 7, 23),
        )
        TankInventory.objects.create(tank=self.tank, working_day=wd1, actual_inventory=Decimal("100"))
        TankInventory.objects.create(tank=self.tank, working_day=wd2, actual_inventory=Decimal("250"))

        from apps.reports import services as report_services
        report = report_services.petroleum_inventory_monthly(self.tank, 1405, 5)
        self.assertEqual(report["ending_inventory"], Decimal("250"))

    # --- Rule 6 + item 7: report recalculation after editing source data ---

    def test_f6_ledger_recalculates_after_editing_actual_inventory(self):
        wd1 = self._make_day("2026-07-23")
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("0"),
            effective_month=datetime.date(2026, 7, 23),
        )
        inv_row = TankInventory.objects.create(
            tank=self.tank, working_day=wd1, actual_inventory=Decimal("10")
        )
        from apps.reports import services as report_services

        rows_before = report_services.petroleum_inventory_operations_ledger(
            self.tank, datetime.date(2026, 7, 23), datetime.date(2026, 7, 23)
        )
        self.assertEqual(rows_before[0]["overage"], Decimal("10"))

        inv_row.actual_inventory = Decimal("0")
        inv_row.save()

        rows_after = report_services.petroleum_inventory_operations_ledger(
            self.tank, datetime.date(2026, 7, 23), datetime.date(2026, 7, 23)
        )
        self.assertEqual(rows_after[0]["overage"], Decimal("0"))

    def test_monthly_statement_recalculates_after_deleting_purchase(self):
        wd1 = self._make_day("2026-07-23")
        purchase = PurchaseInvoice.objects.create(
            working_day=wd1, tank=self.tank, quantity=Decimal("500"),
            purchase_rate=Decimal("1000"),
        )
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("0"),
            effective_month=datetime.date(2026, 7, 23),
        )
        TankInventory.objects.create(tank=self.tank, working_day=wd1, actual_inventory=Decimal("500"))

        from apps.reports import services as report_services
        report_before = report_services.petroleum_inventory_monthly(self.tank, 1405, 5)
        self.assertEqual(report_before["total_purchase"], Decimal("500"))

        purchase.delete()

        report_after = report_services.petroleum_inventory_monthly(self.tank, 1405, 5)
        self.assertEqual(report_after["total_purchase"], Decimal("0"))

class NozzleLedgerNewColumnsTests(TestCase):
    """
    Covers the نازل‌ها daily ledger's reworked columns: کنتور قبلی,
    آزمایش, کنتور جدید are the raw NozzleSale values; جمع روزانه =
    فروش مکانیکی + آزمایش; جمع کل is the running sum of جمع روزانه
    across the selected date range.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="op3", password="testpass123")
        License.objects.create(start_date=datetime.date(2026, 8, 1), duration_days=365)
        station = Station.objects.create(name="S3", province="P", city="C")
        product = Product.objects.create(name="Regular3")
        self.tank = Tank.objects.create(station=station, product=product, capacity=50000)
        self.nozzle = Nozzle.objects.create(tank=self.tank, number=1)

    def _make_day(self, iso_date):
        return DailyWorkingDay.objects.create(date=datetime.date.fromisoformat(iso_date))

    def _make_sale(self, wd, previous_meter, new_meter, test=Decimal("0"), rate=Decimal("1200")):
        invoice = SalesInvoice.objects.get_or_create(working_day=wd, defaults={"operator": self.user})[0]
        return NozzleSale.objects.create(
            sales_invoice=invoice, nozzle=self.nozzle,
            previous_meter=previous_meter, new_meter=new_meter, test=test, sales_rate=rate,
        )

    def test_row_exposes_previous_meter_test_and_new_meter_verbatim(self):
        wd = self._make_day("2026-08-01")
        self._make_sale(wd, previous_meter=Decimal("100"), new_meter=Decimal("160"), test=Decimal("5"))
        from apps.reports import services as report_services
        rows = report_services.nozzle_performance_ledger(
            self.nozzle, datetime.date(2026, 8, 1), datetime.date(2026, 8, 1)
        )
        self.assertEqual(rows[0]["previous_meter"], Decimal("100"))
        self.assertEqual(rows[0]["new_meter"], Decimal("160"))
        self.assertEqual(rows[0]["test"], Decimal("5"))

    def test_daily_total_equals_mechanical_sales_plus_test(self):
        wd = self._make_day("2026-08-01")
        # operation = 60, test = 5 -> mechanical_sales = 55 -> daily_total = 55 + 5 = 60
        self._make_sale(wd, previous_meter=Decimal("100"), new_meter=Decimal("160"), test=Decimal("5"))
        from apps.reports import services as report_services
        rows = report_services.nozzle_performance_ledger(
            self.nozzle, datetime.date(2026, 8, 1), datetime.date(2026, 8, 1)
        )
        self.assertEqual(rows[0]["mechanical_sales"], Decimal("55"))
        self.assertEqual(rows[0]["daily_total"], Decimal("60"))

    def test_daily_total_with_no_test_matches_ui_zero_convention(self):
        wd = self._make_day("2026-08-01")
        self._make_sale(wd, previous_meter=Decimal("0"), new_meter=Decimal("50"))  # test defaults to 0
        from apps.reports import services as report_services
        rows = report_services.nozzle_performance_ledger(
            self.nozzle, datetime.date(2026, 8, 1), datetime.date(2026, 8, 1)
        )
        self.assertEqual(rows[0]["test"], Decimal("0"))
        self.assertEqual(rows[0]["daily_total"], Decimal("50"))

    def test_cumulative_total_on_first_available_day_equals_its_own_daily_total(self):
        wd = self._make_day("2026-08-01")
        self._make_sale(wd, previous_meter=Decimal("0"), new_meter=Decimal("50"))
        from apps.reports import services as report_services
        rows = report_services.nozzle_performance_ledger(
            self.nozzle, datetime.date(2026, 8, 1), datetime.date(2026, 8, 1)
        )
        self.assertEqual(rows[0]["cumulative_total"], rows[0]["daily_total"])
        self.assertEqual(rows[0]["cumulative_total"], Decimal("50"))

    def test_cumulative_total_accumulates_across_multiple_days(self):
        wd1 = self._make_day("2026-08-01")
        wd2 = self._make_day("2026-08-02")
        wd3 = self._make_day("2026-08-03")
        self._make_sale(wd1, previous_meter=Decimal("0"), new_meter=Decimal("50"))       # daily_total 50
        self._make_sale(wd2, previous_meter=Decimal("50"), new_meter=Decimal("120"), test=Decimal("10"))  # op=70, mech=60, daily_total=70
        self._make_sale(wd3, previous_meter=Decimal("120"), new_meter=Decimal("150"))     # daily_total 30

        from apps.reports import services as report_services
        rows = report_services.nozzle_performance_ledger(
            self.nozzle, datetime.date(2026, 8, 1), datetime.date(2026, 8, 3)
        )
        self.assertEqual(rows[0]["cumulative_total"], Decimal("50"))
        self.assertEqual(rows[1]["cumulative_total"], Decimal("120"))   # 50 + 70
        self.assertEqual(rows[2]["cumulative_total"], Decimal("150"))   # 120 + 30

    def test_cumulative_total_ignores_days_outside_the_selected_range(self):
        # A day before the range must not silently contribute to the
        # first in-range day's cumulative total.
        wd0 = self._make_day("2026-07-31")
        wd1 = self._make_day("2026-08-01")
        self._make_sale(wd0, previous_meter=Decimal("0"), new_meter=Decimal("9999"))
        self._make_sale(wd1, previous_meter=Decimal("9999"), new_meter=Decimal("10049"))  # daily_total 50

        from apps.reports import services as report_services
        rows = report_services.nozzle_performance_ledger(
            self.nozzle, datetime.date(2026, 8, 1), datetime.date(2026, 8, 1)
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cumulative_total"], Decimal("50"))

    def test_operation_and_sales_rate_unchanged_by_the_rework(self):
        wd = self._make_day("2026-08-01")
        self._make_sale(wd, previous_meter=Decimal("100"), new_meter=Decimal("160"), test=Decimal("5"), rate=Decimal("1200"))
        from apps.reports import services as report_services
        rows = report_services.nozzle_performance_ledger(
            self.nozzle, datetime.date(2026, 8, 1), datetime.date(2026, 8, 1)
        )
        self.assertEqual(rows[0]["operation"], Decimal("60"))
        self.assertEqual(rows[0]["sales_rate"], Decimal("1200"))

    def test_new_columns_render_on_the_ledger_page(self):
        self.client.login(username="op3", password="testpass123")
        wd1 = self._make_day("2026-08-01")
        wd2 = self._make_day("2026-08-02")
        self._make_sale(wd1, previous_meter=Decimal("100"), new_meter=Decimal("160"), test=Decimal("5"))
        self._make_sale(wd2, previous_meter=Decimal("160"), new_meter=Decimal("210"))

        resp = self.client.get(
            f"/reports/nozzle-ledger/?nozzle_id={self.nozzle.id}"
            "&start_date=2026-08-01&end_date=2026-08-02"
        )
        content = resp.content.decode()

        # All 9 required columns, in the exact right-to-left order given.
        for label in [
            "تاریخ", "کنتور قبلی", "آزمایش", "فروش مکانیکی",
            "جمع روزانه", "جمع کل", "کنتور جدید", "عملکرد", "نرخ",
        ]:
            self.assertIn(label, content)

        # The removed column must be gone from the ledger page.
        self.assertNotIn("مبلغ کل", content)

        # Day 1: daily_total = 55 (mech) + 5 (test) = 60, cumulative = 60.
        # Day 2: daily_total = 50, cumulative = 60 + 50 = 110.
        self.assertContains(resp, "60.00")
        self.assertContains(resp, "110.00")
