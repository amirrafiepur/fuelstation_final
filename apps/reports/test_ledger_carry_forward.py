"""
دفتر موجودی و عملیات: جمع کل رسیده across months.

  First working month : جمع کل رسیده = موجودی افتتاحیه + جمع روزانه‌ی رسیده (unchanged).
  Second month onward : on the month's FIRST working day,
                        جمع کل رسیده = last جمع کل رسیده of the previous month + that day's جمع روزانه‌ی رسیده.

Hand-worked data (Regular tank, opening 100,000; Super tank, opening 50,000). Per day,
    total = previous actual + purchases + test + previous overage
    theoretical = total - sales(op - test) ; overage = max(actual - theoretical, 0)
    جمع روزانه‌ی رسیده = purchases + test + overage

 Regular   date        purchases  test  sales  actual   overage  daily received  جمع کل رسیده
 month 05  07-24 (d1)   10,000     10     990  109,020     0        10,010       100,000+10,010 = 110,010
           07-25 (d2)        0      5     495  108,560    30            35       110,045
 month 06  08-25 (d3)    8,000      0     700  115,890     0         8,000       110,045+8,000  = 118,045   <- 1st working day (not the 1st of the month: 08-23)
           08-26 (d4)        0     20     300  115,620    10            30       118,075
 month 07  09-28 (d5)    5,000      0     400  120,230     0         5,000       118,075+5,000  = 123,075
           09-29 (d6)  1,000+500    2     100  121,639     7         1,509       124,584
 Super     07-24 (d1)    2,000      0     300   51,700     0         2,000       50,000+2,000   =  52,000
           08-25 (d3)    1,000      0     100   52,600     0         1,000       52,000+1,000   =  53,000   <- carried into month 06
"""

import datetime
import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.core.jalali import jalali_month_bounds
from apps.core.test_number_display import numeric_cells, pdf_text, render_pdf_with_html
from apps.inventory import services as inventory_services
from apps.inventory.models import OpeningInventory, TankInventory
from apps.license.models import License
from apps.purchases import services as purchase_services
from apps.purchases.models import PurchaseInvoice
from apps.reports import services as report_services
from apps.sales.models import NozzleSale, SalesInvoice
from apps.stations.models import Nozzle, Tank
from apps.workday.models import DailyWorkingDay

User = get_user_model()
D = Decimal
d = datetime.date

D1, D2, D3, D4, D5, D6 = d(2026, 7, 24), d(2026, 7, 25), d(2026, 8, 25), d(2026, 8, 26), d(2026, 9, 28), d(2026, 9, 29)
REGULAR_CUMULATIVE = {D1: 110010, D2: 110045, D3: 118045, D4: 118075, D5: 123075, D6: 124584}
REGULAR_DAILY = {D1: 10010, D2: 35, D3: 8000, D4: 30, D5: 5000, D6: 1509}
MONTH_DAYS = {5: [D1, D2], 6: [D3, D4], 7: [D5, D6]}


class CarryForwardBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="op1", password="testpass123")
        License.objects.create(start_date=d(2026, 7, 23), duration_days=365)
        call_command("seed_station", stdout=io.StringIO())
        self.regular = Tank.objects.get(product__name="Regular")
        self.super = Tank.objects.get(product__name="Super")
        for tank, opening in ((self.regular, 100000), (self.super, 50000)):
            OpeningInventory.objects.update_or_create(
                tank=tank, effective_month=d(2026, 7, 23), defaults={"opening_quantity": D(opening)})
        self.client.login(username="op1", password="testpass123")

        # (day, nozzle, previous, new, test, purchases, actual inventory)
        for day, number, prev, new, test, purchases, actual, tank in (
            (D1, 1, 0, 1000, 10, [10000], "109020", self.regular),
            (D2, 1, 1000, 1500, 5, [], "108560", self.regular),
            (D3, 1, 1500, 2200, 0, [8000], "115890", self.regular),
            (D4, 1, 2200, 2520, 20, [], "115620", self.regular),
            (D5, 1, 2520, 2920, 0, [5000], "120230", self.regular),
            (D6, 1, 2920, 3022, 2, [1000, 500], "121639", self.regular),
            (D1, 19, 0, 300, 0, [2000], "51700", self.super),
            (D3, 19, 300, 400, 0, [1000], "52600", self.super),
        ):
            wd, _ = DailyWorkingDay.objects.get_or_create(date=day)
            inv, _ = SalesInvoice.objects.get_or_create(working_day=wd, defaults={"operator": self.user})
            NozzleSale.objects.create(sales_invoice=inv, nozzle=Nozzle.objects.get(number=number),
                                      previous_meter=D(prev), new_meter=D(new), test=D(test), sales_rate=D(1200))
            for quantity in purchases:
                PurchaseInvoice.objects.create(working_day=wd, tank=tank, quantity=quantity, purchase_rate=D(1200),
                                               program_number="1", tanker_number="T")
            TankInventory.objects.create(tank=tank, working_day=wd, actual_inventory=D(actual))

    def ledger(self, tank, start, end):
        return report_services.petroleum_inventory_operations_ledger(tank, start, end)

    def month(self, tank, month):
        first, last = jalali_month_bounds(1405, month)
        return self.ledger(tank, first, last)

    @staticmethod
    def cumulative(rows):
        return {r["date"]: r["cumulative_received"] for r in rows if r["daily_received"] is not None}

    @staticmethod
    def daily(rows):
        return {r["date"]: r["daily_received"] for r in rows if r["daily_received"] is not None}


class MonthRuleTests(CarryForwardBase):
    def test_the_hand_data_itself(self):
        """Sanity-check my arithmetic against the live per-day daily totals."""
        whole = self.ledger(self.regular, D1, D6)
        self.assertEqual({k: int(v) for k, v in self.daily(whole).items()}, REGULAR_DAILY)

    def test_first_working_month_is_unchanged(self):
        rows = self.month(self.regular, 5)
        self.assertEqual({k: int(v) for k, v in self.cumulative(rows).items()}, {D1: 110010, D2: 110045})
        # opening balance + that day's daily received on the first working day
        self.assertEqual(self.cumulative(rows)[D1], D(100000) + self.daily(rows)[D1])

    def test_second_month_starts_from_the_previous_months_last_total(self):
        rows = self.month(self.regular, 6)
        self.assertEqual(rows[0]["date"], D3)                       # first working day, not the month's 1st calendar day (08-23)
        self.assertEqual({k: int(v) for k, v in self.cumulative(rows).items()}, {D3: 118045, D4: 118075})
        previous_last = self.cumulative(self.month(self.regular, 5))[D2]
        self.assertEqual(self.cumulative(rows)[D3], previous_last + self.daily(rows)[D3])      # the rule, literally
        self.assertEqual(self.cumulative(rows)[D3], D(110045) + D(8000))

    def test_third_consecutive_month_chains_on_the_second(self):
        rows = self.month(self.regular, 7)
        self.assertEqual({k: int(v) for k, v in self.cumulative(rows).items()}, {D5: 123075, D6: 124584})
        previous_last = self.cumulative(self.month(self.regular, 6))[D4]
        self.assertEqual(self.cumulative(rows)[D5], previous_last + self.daily(rows)[D5])
        self.assertEqual(self.daily(rows)[D6], D(1509))             # two purchases that day + test + overage

    def test_opening_balance_is_carried_through_every_month(self):
        """Month 1's last total = opening + all of month 1's daily totals; months 2 and 3 only ever add on top."""
        opening = D(100000)
        for months, expected_last in (([5], D(110045)), ([5, 6], D(118075)), ([5, 6, 7], D(124584))):
            total = opening + sum(sum(self.daily(self.month(self.regular, m)).values()) for m in months)
            last_month = self.month(self.regular, months[-1])
            self.assertEqual(max(self.cumulative(last_month).items())[1], total)
            self.assertEqual(total, expected_last)

    def test_each_month_view_agrees_with_one_continuous_view(self):
        whole = self.cumulative(self.ledger(self.regular, D1, D6))
        self.assertEqual({k: int(v) for k, v in whole.items()}, REGULAR_CUMULATIVE)
        for month, days in MONTH_DAYS.items():
            month_view = self.cumulative(self.month(self.regular, month))
            self.assertEqual({k: month_view[k] for k in days}, {k: whole[k] for k in days}, month)

    def test_a_two_month_range_is_continuous(self):
        rows = self.ledger(self.regular, jalali_month_bounds(1405, 5)[0], jalali_month_bounds(1405, 6)[1])
        self.assertEqual({k: int(v) for k, v in self.cumulative(rows).items()}, {D1: 110010, D2: 110045, D3: 118045, D4: 118075})

    def test_each_tank_carries_its_own_total(self):
        super_05 = self.cumulative(self.month(self.super, 5))
        super_06 = self.cumulative(self.month(self.super, 6))
        self.assertEqual({k: int(v) for k, v in super_05.items()}, {D1: 52000})             # 50,000 + 2,000
        self.assertEqual({k: int(v) for k, v in super_06.items()}, {D3: 53000})             # 52,000 + 1,000
        self.assertEqual(self.cumulative(self.month(self.regular, 6))[D3], D(118045))        # Regular unaffected by Super

    def test_first_working_day_without_an_inventory_entry_carries_into_the_next_recorded_day(self):
        TankInventory.objects.filter(tank=self.regular, working_day__date=D3).delete()
        rows = self.month(self.regular, 6)
        # d4 now follows d2: total 108,560+0+20+30 = 108,610; theoretical 108,310; actual 115,620 -> overage 7,310;
        # daily received 20+7,310 = 7,330; carried in 110,045 -> 117,375.
        self.assertEqual({k: int(v) for k, v in self.cumulative(rows).items()}, {D4: 117375})

    def test_range_starting_mid_month_keeps_the_existing_convention(self):
        """Not a month's first working day: unchanged -- starts from that day's own total."""
        rows = self.ledger(self.regular, D4, D6)
        self.assertEqual({k: int(v) for k, v in self.cumulative(rows).items()}, {D4: 30, D5: 5030, D6: 6539})

    def test_dispatched_total_and_other_columns_are_untouched(self):
        rows = self.month(self.regular, 6)
        first = rows[0]
        self.assertEqual(first["daily_dispatched"], first["cumulative_dispatched"])        # still not carried forward
        self.assertEqual(first["daily_dispatched"], D(700))                                # sales 700 + test 0 + shortage 0
        self.assertEqual((first["daily_purchase"], first["daily_sales"], first["actual_inventory"], first["overage"]),
                         (D(8000), D(700), D("115890"), D(0)))


class CarriedInHelperTests(CarryForwardBase):
    def test_none_before_the_tanks_first_recorded_day(self):
        self.assertIsNone(report_services.received_cumulative_carried_in(self.regular, D1))
        self.assertIsNone(report_services.received_cumulative_carried_in(self.regular, d(2026, 1, 1)))

    def test_equals_the_last_total_of_the_continuous_ledger_before_each_date(self):
        whole = self.cumulative(self.ledger(self.regular, D1, D6))
        for before, last_day in ((D2, D1), (D3, D2), (D4, D3), (D5, D4), (D6, D5), (d(2026, 12, 1), D6)):
            self.assertEqual(report_services.received_cumulative_carried_in(self.regular, before), whole[last_day], before)

    def test_matches_the_existing_per_day_inventory_calculation_exactly(self):
        """The one-pass helper must agree with compute_tank_inventory() (the project's own calculation)."""
        for tank in (self.regular, self.super):
            rows = list(TankInventory.objects.filter(tank=tank).select_related("working_day").order_by("working_day__date"))
            opening, _ = inventory_services.get_previous_balance_and_overage(tank, rows[0].working_day)
            running = opening
            for row in rows:
                wd = row.working_day
                overage = inventory_services.compute_tank_inventory(tank, wd)[3]
                running += (purchase_services.get_daily_purchase_total(tank, wd)
                            + inventory_services.get_test_return(tank, wd) + overage)
                after = wd.date + datetime.timedelta(days=1)
                self.assertEqual(report_services.received_cumulative_carried_in(tank, after), running, (tank.id, wd.date))


class ScreenPdfAndMonthlyTests(CarryForwardBase):
    def url(self, month):
        first, last = jalali_month_bounds(1405, month)
        return f"tank_id={self.regular.id}&start_date={first.isoformat()}&end_date={last.isoformat()}"

    def test_screen_shows_the_carried_forward_totals(self):
        for month, expected in ((5, [110010, 110045]), (6, [118045, 118075]), (7, [123075, 124584])):
            html = self.client.get(f"/reports/petroleum-ledger/?{self.url(month)}").content.decode()
            cells = numeric_cells(html)
            for value in expected:
                self.assertIn(f"{value:,}", cells, (month, value))

    def test_pdf_shows_the_same_totals(self):
        for month, expected in ((5, [110010, 110045]), (6, [118045, 118075]), (7, [123075, 124584])):
            first, last = jalali_month_bounds(1405, month)
            resp, html = render_pdf_with_html(
                self.client, f"/print/petroleum-ledger/{self.regular.id}/?start_date={first}&end_date={last}")
            self.assertEqual(resp.status_code, 200)
            cells = numeric_cells(html)
            text = pdf_text(resp.content)
            for value in expected:
                self.assertIn(f"{value:,}", cells, (month, value))
                self.assertIn(f"{value:,}", text, (month, value))

    def test_monthly_tank_report_follows_the_same_totals(self):
        """گزارش ماهانه مخازن reuses the ledger's cumulative total verbatim, so it carries forward too."""
        for month, expected in ((5, 110045), (6, 118075), (7, 124584)):
            row = report_services.petroleum_inventory_monthly(self.regular, 1405, month)
            self.assertEqual(row["total_received"], D(expected), month)

    def test_viewing_changes_no_stored_data(self):
        before = (list(TankInventory.objects.values_list("actual_inventory", flat=True).order_by("id")),
                  list(PurchaseInvoice.objects.values_list("quantity", flat=True).order_by("id")),
                  list(OpeningInventory.objects.values_list("opening_quantity", flat=True).order_by("id")))
        for month in (5, 6, 7):
            self.client.get(f"/reports/petroleum-ledger/?{self.url(month)}")
        after = (list(TankInventory.objects.values_list("actual_inventory", flat=True).order_by("id")),
                 list(PurchaseInvoice.objects.values_list("quantity", flat=True).order_by("id")),
                 list(OpeningInventory.objects.values_list("opening_quantity", flat=True).order_by("id")))
        self.assertEqual(before, after)
