"""
A day's سرک must not change the کسری of the following days, nor therefore their
جمع روزانه‌ی خارج شده / جمع کل خارج شده on دفتر موجودی و عملیات.

Regular tank, opening 100,000. The operator enters the TRUE tank level each day, i.e. the
previous level + purchases - mechanical sales (+ 14 liters of real surplus found on day 2).
  total = previous actual + purchases + test ; theoretical = total - (sales + test)

 day  purchases  test  sales  actual    سرک  کسری  dispatched(day)  dispatched(total)  received(total)
 d1    10,000     10     990  109,010     0    0        1,000            1,000            110,010
 d2         0      5     495  108,529    14    0          500            1,500            110,029   (108,515 + 14 surplus)
 d3     8,000      0     700  115,829     0    0          700            2,200            118,029   (was: کسری 14, dispatched 714 / 2,214)
 d4         0     20     300  115,529     0    0          320            2,520            118,049   (was: dispatched total 2,534)
and from the first day on:  جمع کل رسیده - جمع کل خارج شده = موجودی واقعی.
"""

import datetime
import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.inventory.models import OpeningInventory, TankInventory
from apps.license.models import License
from apps.purchases.models import PurchaseInvoice
from apps.reports import services as report_services
from apps.sales.models import NozzleSale, SalesInvoice
from apps.stations.models import Nozzle, Tank
from apps.workday.models import DailyWorkingDay

D = Decimal
d = datetime.date
DAYS = [d(2026, 7, 24), d(2026, 7, 25), d(2026, 7, 26), d(2026, 7, 27)]


class OverageIsNotCarriedIntoTheNextDaysShortageTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="op1", password="testpass123")
        License.objects.create(start_date=d(2026, 7, 23), duration_days=365)
        call_command("seed_station", stdout=io.StringIO())
        self.tank = Tank.objects.get(product__name="Regular")
        OpeningInventory.objects.update_or_create(
            tank=self.tank, effective_month=d(2026, 7, 23), defaults={"opening_quantity": D(100000)})
        meter = 0
        # (operation, test, purchase, real surplus found that day)
        for day, (operation, test, purchase, surplus), actual in zip(
            DAYS,
            ((1000, 10, 10000, 0), (500, 5, 0, 14), (700, 0, 8000, 0), (320, 20, 0, 0)),
            ("109010", "108529", "115829", "115529"),
        ):
            wd = DailyWorkingDay.objects.create(date=day)
            invoice = SalesInvoice.objects.create(working_day=wd, operator=user)
            NozzleSale.objects.create(
                sales_invoice=invoice, nozzle=Nozzle.objects.get(number=1), previous_meter=D(meter),
                new_meter=D(meter + operation), test=D(test), sales_rate=D(1200))
            meter += operation
            if purchase:
                PurchaseInvoice.objects.create(
                    working_day=wd, tank=self.tank, quantity=purchase, purchase_rate=D(1200),
                    program_number="1", tanker_number="T")
            TankInventory.objects.create(tank=self.tank, working_day=wd, actual_inventory=D(actual))
        rows = report_services.petroleum_inventory_operations_ledger(self.tank, DAYS[0], DAYS[-1])
        self.rows = {r["date"]: r for r in rows if r["daily_dispatched"] is not None}

    def test_only_the_day_that_found_the_overage_shows_it(self):
        overage = {day: self.rows[day]["overage"] for day in DAYS}
        shortage = {day: self.rows[day]["shortage"] for day in DAYS}
        self.assertEqual(overage, {DAYS[0]: D(0), DAYS[1]: D(14), DAYS[2]: D(0), DAYS[3]: D(0)})
        self.assertEqual(shortage, {day: D(0) for day in DAYS})          # day 3 used to show a false کسری of 14

    def test_dispatched_totals_follow_sales_plus_test_only(self):
        self.assertEqual([self.rows[day]["daily_dispatched"] for day in DAYS], [D(1000), D(500), D(700), D(320)])
        self.assertEqual([self.rows[day]["cumulative_dispatched"] for day in DAYS], [D(1000), D(1500), D(2200), D(2520)])

    def test_total_received_minus_total_dispatched_is_the_actual_inventory(self):
        for day in DAYS:
            actual = TankInventory.objects.get(tank=self.tank, working_day__date=day).actual_inventory
            self.assertEqual(self.rows[day]["cumulative_received"] - self.rows[day]["cumulative_dispatched"], actual, day)
