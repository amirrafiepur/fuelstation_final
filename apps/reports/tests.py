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
        resp = self.client.get("/reports/nozzle-ledger/?nozzle_id=1")
        self.assertContains(resp, "100")  # operation and sales_amount (both same since test=0)
        self.assertContains(resp, "120000")  # total_amount (100 * 1200)

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
        resp = self.client.get("/reports/nozzle-monthly/?year=2026&month=8")
        self.assertEqual(resp.status_code, 200)

    def test_nozzle_monthly_aggregates_correctly(self):
        invoice = SalesInvoice.objects.create(working_day=self.wd, operator=self.user)
        NozzleSale.objects.create(
            sales_invoice=invoice, nozzle=self.nozzle,
            previous_meter=Decimal("0"), new_meter=Decimal("100"), test=Decimal("0"),
            sales_rate=Decimal("1200"),
        )
        resp = self.client.get("/reports/nozzle-monthly/?year=2026&month=8")
        self.assertContains(resp, "100")  # total operation and total sales_amount
        self.assertContains(resp, "120000")  # total total_amount (100 * 1200)

    def test_nozzle_monthly_excludes_other_months(self):
        invoice = SalesInvoice.objects.create(working_day=self.wd, operator=self.user)
        NozzleSale.objects.create(
            sales_invoice=invoice, nozzle=self.nozzle,
            previous_meter=Decimal("0"), new_meter=Decimal("100"), test=Decimal("0"),
            sales_rate=Decimal("1200"),
        )
        resp = self.client.get("/reports/nozzle-monthly/?year=2026&month=9")
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
        resp = self.client.get("/reports/petroleum-ledger/?tank_id=1")
        self.assertContains(resp, "100")  # daily purchase

    def test_petroleum_monthly_renders(self):
        resp = self.client.get("/reports/petroleum-monthly/?year=2026&month=8")
        self.assertEqual(resp.status_code, 200)

    def test_petroleum_monthly_aggregates_purchases(self):
        PurchaseInvoice.objects.create(
            working_day=self.wd, tank=self.tank, quantity=Decimal("100"),
            purchase_rate=Decimal("1000"),
        )
        resp = self.client.get("/reports/petroleum-monthly/?year=2026&month=8")
        self.assertContains(resp, "100")  # total purchase

    def test_report_reflects_live_data_changes(self):
        """
        Verify that reports are truly derived views: changing source data
        immediately updates the report, no caching or duplication.
        """
        # First state: no sales
        resp1 = self.client.get("/reports/nozzle-ledger/?nozzle_id=1")
        self.assertNotContains(resp1, "2026/08/01")

        # Add a sale
        invoice = SalesInvoice.objects.create(working_day=self.wd, operator=self.user)
        NozzleSale.objects.create(
            sales_invoice=invoice, nozzle=self.nozzle,
            previous_meter=Decimal("0"), new_meter=Decimal("100"), test=Decimal("0"),
            sales_rate=Decimal("1200"),
        )

        # Report immediately shows the new data
        resp2 = self.client.get("/reports/nozzle-ledger/?nozzle_id=1")
        self.assertContains(resp2, "100.00")  # operation and mechanical_sales
        self.assertContains(resp2, "120000")  # total_amount (100 * 1200)

        # Edit the sale
        sale = NozzleSale.objects.get(nozzle=self.nozzle)
        sale.new_meter = Decimal("150")
        sale.save()

        # Report immediately reflects the change in the table data
        resp3 = self.client.get("/reports/nozzle-ledger/?nozzle_id=1")
        self.assertContains(resp3, "150.00")  # operation and mechanical_sales (updated)
        self.assertContains(resp3, "180000")  # total_amount (150 * 1200, updated)


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
        # Mid-month activation: Aug 15 -- accounting start must still be Aug 1.
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
        # Activation was Aug 15, but the operator backfills Aug 1 onward.
        wd1 = self._make_day("2026-08-01")
        self._make_sale(wd1, Decimal("0"), Decimal("50"))
        from apps.reports import services as report_services
        report = report_services.nozzle_performance_monthly(self.nozzle, 2026, 8)
        self.assertIsNotNone(report)
        self.assertEqual(report["beginning_of_month_meter"], Decimal("0"))
        self.assertEqual(report["total_operation"], Decimal("50"))

    def test_accounting_start_is_day_1_not_activation_date(self):
        from apps.workday import services as workday_services
        start = workday_services.get_accounting_start_date()
        self.assertEqual(start, datetime.date(2026, 8, 1))

    # --- Rule 2: beginning/end-of-month meter ---

    def test_beginning_of_month_meter_is_first_accounting_month_day1_reading(self):
        wd1 = self._make_day("2026-08-01")
        self._make_sale(wd1, Decimal("100"), Decimal("150"))
        from apps.reports import services as report_services
        report = report_services.nozzle_performance_monthly(self.nozzle, 2026, 8)
        self.assertEqual(report["beginning_of_month_meter"], Decimal("100"))

    def test_end_of_month_meter_is_latest_registered_reading(self):
        wd1 = self._make_day("2026-08-01")
        wd2 = self._make_day("2026-08-02")
        self._make_sale(wd1, Decimal("100"), Decimal("150"))
        self._make_sale(wd2, Decimal("150"), Decimal("220"))
        from apps.reports import services as report_services
        report = report_services.nozzle_performance_monthly(self.nozzle, 2026, 8)
        self.assertEqual(report["end_of_month_meter"], Decimal("220"))

    def test_beginning_of_month_meter_for_second_month_uses_prior_months_ending_meter(self):
        wd_aug = self._make_day("2026-08-31")
        self._make_sale(wd_aug, Decimal("900"), Decimal("1000"))
        wd_sep = self._make_day("2026-09-01")
        self._make_sale(wd_sep, Decimal("1000"), Decimal("1050"))
        from apps.reports import services as report_services
        report = report_services.nozzle_performance_monthly(self.nozzle, 2026, 9)
        self.assertEqual(report["beginning_of_month_meter"], Decimal("1000"))

    def test_beginning_of_month_meter_not_hardcoded_reflects_actual_data(self):
        # Different starting meter must produce a different result --
        # proves this is derived, not a hardcoded/default value.
        wd1 = self._make_day("2026-08-01")
        self._make_sale(wd1, Decimal("54321"), Decimal("54400"))
        from apps.reports import services as report_services
        report = report_services.nozzle_performance_monthly(self.nozzle, 2026, 8)
        self.assertEqual(report["beginning_of_month_meter"], Decimal("54321"))

    # --- Rule 1: frozen historical sales rate reflected in reports ---

    def test_ledger_uses_frozen_historical_sales_rate_not_current_default(self):
        wd1 = self._make_day("2026-08-01")
        self._make_sale(wd1, Decimal("0"), Decimal("100"), rate=Decimal("1000"))
        # A later purchase/sale changes the "current" rate elsewhere, but
        # this historical record's rate must remain frozen at 1000.
        wd2 = self._make_day("2026-08-02")
        nozzle2 = Nozzle.objects.create(tank=self.tank, number=2)
        invoice2 = SalesInvoice.objects.create(working_day=wd2, operator=self.user)
        NozzleSale.objects.create(
            sales_invoice=invoice2, nozzle=nozzle2,
            previous_meter=Decimal("0"), new_meter=Decimal("50"), test=Decimal("0"),
            sales_rate=Decimal("1500"),
        )
        from apps.reports import services as report_services
        rows = report_services.nozzle_performance_ledger(
            self.nozzle, datetime.date(2026, 8, 1), datetime.date(2026, 8, 31)
        )
        self.assertEqual(rows[0]["sales_rate"], Decimal("1000"))
        self.assertEqual(rows[0]["total_amount"], Decimal("100000"))  # 100 * 1000

    # --- Rule 3: F6 Daily Total 1 / Daily Total 2, shortage/overage consistency ---

    def test_f6_daily_total_1_and_2_match_formula(self):
        wd1 = self._make_day("2026-08-01")
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("1000"),
            effective_month=datetime.date(2026, 8, 1),
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
            self.tank, datetime.date(2026, 8, 1), datetime.date(2026, 8, 1)
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
        wd1 = self._make_day("2026-08-01")
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("0"),
            effective_month=datetime.date(2026, 8, 1),
        )
        TankInventory.objects.create(tank=self.tank, working_day=wd1, actual_inventory=Decimal("0"))
        from apps.reports import services as report_services
        report = report_services.petroleum_inventory_monthly(self.tank, 2026, 8)
        self.assertEqual(report["beginning_inventory"], Decimal("0"))

    def test_monthly_beginning_inventory_uses_non_zero_opening_inventory(self):
        wd1 = self._make_day("2026-08-01")
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("5000"),
            effective_month=datetime.date(2026, 8, 1),
        )
        TankInventory.objects.create(tank=self.tank, working_day=wd1, actual_inventory=Decimal("5000"))
        from apps.reports import services as report_services
        report = report_services.petroleum_inventory_monthly(self.tank, 2026, 8)
        self.assertEqual(report["beginning_inventory"], Decimal("5000"))

    def test_monthly_beginning_inventory_second_month_uses_prior_months_ending_actual(self):
        wd_aug = self._make_day("2026-08-31")
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("0"),
            effective_month=datetime.date(2026, 8, 1),
        )
        TankInventory.objects.create(tank=self.tank, working_day=wd_aug, actual_inventory=Decimal("777"))
        wd_sep = self._make_day("2026-09-01")
        TankInventory.objects.create(tank=self.tank, working_day=wd_sep, actual_inventory=Decimal("800"))

        from apps.reports import services as report_services
        report = report_services.petroleum_inventory_monthly(self.tank, 2026, 9)
        self.assertEqual(report["beginning_inventory"], Decimal("777"))

    def test_monthly_ending_inventory_is_last_registered_actual_never_manual(self):
        wd1 = self._make_day("2026-08-01")
        wd2 = self._make_day("2026-08-02")
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("0"),
            effective_month=datetime.date(2026, 8, 1),
        )
        TankInventory.objects.create(tank=self.tank, working_day=wd1, actual_inventory=Decimal("100"))
        TankInventory.objects.create(tank=self.tank, working_day=wd2, actual_inventory=Decimal("250"))

        from apps.reports import services as report_services
        report = report_services.petroleum_inventory_monthly(self.tank, 2026, 8)
        self.assertEqual(report["ending_inventory"], Decimal("250"))

    # --- Rule 6 + item 7: report recalculation after editing source data ---

    def test_f6_ledger_recalculates_after_editing_actual_inventory(self):
        wd1 = self._make_day("2026-08-01")
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("0"),
            effective_month=datetime.date(2026, 8, 1),
        )
        inv_row = TankInventory.objects.create(
            tank=self.tank, working_day=wd1, actual_inventory=Decimal("10")
        )
        from apps.reports import services as report_services

        rows_before = report_services.petroleum_inventory_operations_ledger(
            self.tank, datetime.date(2026, 8, 1), datetime.date(2026, 8, 1)
        )
        self.assertEqual(rows_before[0]["overage"], Decimal("10"))

        inv_row.actual_inventory = Decimal("0")
        inv_row.save()

        rows_after = report_services.petroleum_inventory_operations_ledger(
            self.tank, datetime.date(2026, 8, 1), datetime.date(2026, 8, 1)
        )
        self.assertEqual(rows_after[0]["overage"], Decimal("0"))

    def test_monthly_statement_recalculates_after_deleting_purchase(self):
        wd1 = self._make_day("2026-08-01")
        purchase = PurchaseInvoice.objects.create(
            working_day=wd1, tank=self.tank, quantity=Decimal("500"),
            purchase_rate=Decimal("1000"),
        )
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("0"),
            effective_month=datetime.date(2026, 8, 1),
        )
        TankInventory.objects.create(tank=self.tank, working_day=wd1, actual_inventory=Decimal("500"))

        from apps.reports import services as report_services
        report_before = report_services.petroleum_inventory_monthly(self.tank, 2026, 8)
        self.assertEqual(report_before["total_purchase"], Decimal("500"))

        purchase.delete()

        report_after = report_services.petroleum_inventory_monthly(self.tank, 2026, 8)
        self.assertEqual(report_after["total_purchase"], Decimal("0"))
