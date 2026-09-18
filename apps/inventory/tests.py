"""
Tank inventory tests -- covering the corrected non-circular Overage
carry-forward rule and the opening-inventory chain, using the worked
example from the implementation spec (§60).
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.inventory import services
from apps.inventory.models import TankInventory, OpeningInventory
from apps.license.models import License
from apps.purchases.models import PurchaseInvoice
from apps.sales.models import SalesInvoice, NozzleSale
from apps.stations.models import Station, Product, Tank, Nozzle
from apps.workday.models import DailyWorkingDay

User = get_user_model()


class TankInventoryChainTests(TestCase):
    def setUp(self):
        # 2026-08-01 is Jalali 1405/05/10 -- the accounting start (day 1
        # of that Jalali month) is Gregorian 2026-07-23.
        License.objects.create(start_date=datetime.date(2026, 8, 1), duration_days=365)
        self.station = Station.objects.create(name="Test Station", province="P", city="C")
        self.product = Product.objects.create(name="Regular")
        self.tank = Tank.objects.create(station=self.station, product=self.product, capacity=50000)
        self.nozzle = Nozzle.objects.create(tank=self.tank, number=1)
        self.user = User.objects.create_user(username="op1", password="x")

        self.day1 = DailyWorkingDay.objects.create(date=datetime.date(2026, 7, 23))
        self.day2 = DailyWorkingDay.objects.create(date=datetime.date(2026, 7, 24))

    def _make_nozzle_sale(self, working_day, previous_meter, new_meter, test):
        invoice, _ = SalesInvoice.objects.get_or_create(
            working_day=working_day, defaults={"operator": self.user}
        )
        return NozzleSale.objects.create(
            sales_invoice=invoice,
            nozzle=self.nozzle,
            previous_meter=previous_meter,
            new_meter=new_meter,
            test=test,
            sales_rate=Decimal("1200"),
        )

    def test_day_one_uses_opening_inventory_and_matches_spec_example(self):
        # Spec §60 worked example:
        # Opening Inventory = 1000, Purchase = 100, Test = 5, Sales = 200,
        # Actual Inventory = 905 -> Total=1105, Theoretical=905, Shortage=0, Overage=0
        OpeningInventory.objects.create(
            tank=self.tank, opening_quantity=Decimal("1000"), effective_month=datetime.date(2026, 7, 23)
        )
        PurchaseInvoice.objects.create(
            working_day=self.day1, tank=self.tank, quantity=100, purchase_rate=Decimal("1200")
        )
        # Sales of 200 with test of 5: operation - test = mechanical sales.
        # previous=0, new=205, test=5 -> operation=205, mechanical_sales=200.
        self._make_nozzle_sale(self.day1, previous_meter=Decimal("0"), new_meter=Decimal("205"), test=Decimal("5"))

        TankInventory.objects.create(
            working_day=self.day1, tank=self.tank, actual_inventory=Decimal("905")
        )

        total, theoretical, shortage, overage = services.compute_tank_inventory(self.tank, self.day1)
        self.assertEqual(total, Decimal("1105"))
        self.assertEqual(theoretical, Decimal("905"))
        self.assertEqual(shortage, Decimal("0"))
        self.assertEqual(overage, Decimal("0"))

    def test_day_two_uses_day_ones_actual_and_overage_not_its_own(self):
        # Day 1: no opening inventory row (defaults to 0), no purchase/sales,
        # Actual = 10 -> Theoretical = 0 -> Overage = 10.
        TankInventory.objects.create(
            working_day=self.day1, tank=self.tank, actual_inventory=Decimal("10")
        )
        total1, theoretical1, shortage1, overage1 = services.compute_tank_inventory(
            self.tank, self.day1
        )
        self.assertEqual(overage1, Decimal("10"))

        # Day 2: no purchase/sales either. Previous Balance = 10 (day1 actual),
        # Previous Overage = 10 (day1's own overage, carried forward).
        # Total = 10 + 0 + 0 + 10 = 20. If Actual = 20 -> Theoretical = 20 ->
        # shortage=overage=0, proving day 2 did NOT use its own (zero) overage
        # circularly but correctly carried day 1's.
        TankInventory.objects.create(
            working_day=self.day2, tank=self.tank, actual_inventory=Decimal("20")
        )
        total2, theoretical2, shortage2, overage2 = services.compute_tank_inventory(
            self.tank, self.day2
        )
        self.assertEqual(total2, Decimal("20"))
        self.assertEqual(theoretical2, Decimal("20"))
        self.assertEqual(shortage2, Decimal("0"))
        self.assertEqual(overage2, Decimal("0"))

    def test_missing_actual_inventory_raises(self):
        with self.assertRaises(ValueError):
            services.compute_tank_inventory(self.tank, self.day1)

    def test_shortage_and_overage_never_both_nonzero(self):
        TankInventory.objects.create(
            working_day=self.day1, tank=self.tank, actual_inventory=Decimal("0")
        )
        total, theoretical, shortage, overage = services.compute_tank_inventory(
            self.tank, self.day1
        )
        self.assertTrue(shortage == 0 or overage == 0)
        self.assertGreaterEqual(shortage, 0)
        self.assertGreaterEqual(overage, 0)


# ---------------------------------------------------------------------------
# HTTP-level integration tests for the Phase 6 tank inventory workflow.
# ---------------------------------------------------------------------------

from django.test import TestCase as _TestCase

User_ = get_user_model()


class InventoryWorkflowHttpTests(_TestCase):
    def setUp(self):
        self.user = User_.objects.create_user(username="op1", password="testpass123")
        # 2026-08-01 is Jalali 1405/05/10 -- accounting start (day 1 of
        # that Jalali month) is Gregorian 2026-07-23, so that's the date
        # that must trigger the "day 1" opening-inventory prompt below.
        License.objects.create(start_date=datetime.date(2026, 8, 1), duration_days=365)
        station = Station.objects.create(name="S", province="P", city="C")
        self.product = Product.objects.create(name="Regular")
        self.tank = Tank.objects.create(station=station, product=self.product, capacity=50000)
        self.client.login(username="op1", password="testpass123")
        self.day1 = "2026-07-23"
        self.day2 = "2026-07-24"

    def test_day_detail_prompts_for_opening_inventory_on_first_day(self):
        resp = self.client.get(f"/inventory/{self.day1}/")
        self.assertContains(resp, "موجودی افتتاحیه")

    def test_opening_inventory_defaults_to_zero_and_is_not_forced(self):
        resp = self.client.get(f"/inventory/{self.day1}/tank/{self.tank.id}/opening/")
        self.assertContains(resp, 'value="0"')

    def test_can_submit_opening_inventory_of_zero(self):
        resp = self.client.post(
            f"/inventory/{self.day1}/tank/{self.tank.id}/opening/",
            {"opening_quantity": "0"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            OpeningInventory.objects.filter(tank=self.tank, opening_quantity=Decimal("0")).exists()
        )

    def test_can_submit_a_real_opening_inventory_value(self):
        self.client.post(
            f"/inventory/{self.day1}/tank/{self.tank.id}/opening/",
            {"opening_quantity": "1000"},
        )
        opening = OpeningInventory.objects.get(tank=self.tank)
        self.assertEqual(opening.opening_quantity, Decimal("1000"))

    def test_actual_inventory_prompt_shown_when_missing(self):
        self.client.post(
            f"/inventory/{self.day1}/tank/{self.tank.id}/opening/",
            {"opening_quantity": "1000"},
        )
        resp = self.client.get(f"/inventory/{self.day1}/")
        self.assertContains(resp, "موجودی واقعی برای این مخزن")

    def test_full_first_day_flow_matches_spec_example(self):
        # Reproduces the architecture doc's worked example (§60):
        # Opening=1000, Purchase=100, Test=5(via sales), Sales=200,
        # Actual=905 -> Total=1105, Theoretical=905, Shortage=0, Overage=0.
        self.client.post(
            f"/inventory/{self.day1}/tank/{self.tank.id}/opening/",
            {"opening_quantity": "1000"},
        )
        PurchaseInvoice.objects.create(
            working_day=DailyWorkingDay.objects.get(date=self.day1),
            tank=self.tank, quantity=100, purchase_rate=Decimal("1200"),
        )
        nozzle = Nozzle.objects.create(tank=self.tank, number=1)
        invoice = SalesInvoice.objects.create(
            working_day=DailyWorkingDay.objects.get(date=self.day1), operator=self.user
        )
        NozzleSale.objects.create(
            sales_invoice=invoice, nozzle=nozzle,
            previous_meter=Decimal("0"), new_meter=Decimal("205"), test=Decimal("5"),
            sales_rate=Decimal("1200"),
        )
        self.client.post(
            f"/inventory/{self.day1}/tank/{self.tank.id}/actual/",
            {"actual_inventory": "905"},
        )
        resp = self.client.get(f"/inventory/{self.day1}/")
        self.assertContains(resp, "1105")  # total inventory
        self.assertContains(resp, "905")   # theoretical inventory + actual

    def test_day_two_does_not_prompt_for_opening_inventory(self):
        # Day 2 is not day 1 of the accounting month -- no opening prompt.
        self.client.post(
            f"/inventory/{self.day1}/tank/{self.tank.id}/opening/",
            {"opening_quantity": "0"},
        )
        self.client.post(
            f"/inventory/{self.day1}/tank/{self.tank.id}/actual/",
            {"actual_inventory": "0"},
        )
        resp = self.client.get(f"/inventory/{self.day2}/")
        self.assertNotContains(resp, "موجودی افتتاحیه مخزن")

    def test_day_two_uses_day_ones_actual_and_carried_overage_not_own(self):
        # Mirrors the service-level circularity regression test, but
        # exercised through the actual HTTP views end to end.
        self.client.post(
            f"/inventory/{self.day1}/tank/{self.tank.id}/opening/",
            {"opening_quantity": "0"},
        )
        self.client.post(
            f"/inventory/{self.day1}/tank/{self.tank.id}/actual/",
            {"actual_inventory": "10"},  # theoretical=0 -> overage=10
        )
        self.client.post(
            f"/inventory/{self.day2}/tank/{self.tank.id}/actual/",
            {"actual_inventory": "20"},  # prev balance=10 + prev overage=10 = 20
        )
        total, theoretical, shortage, overage = services.compute_tank_inventory(
            self.tank, DailyWorkingDay.objects.get(date=self.day2)
        )
        self.assertEqual(total, Decimal("20"))
        self.assertEqual(shortage, Decimal("0"))
        self.assertEqual(overage, Decimal("0"))

    def test_shortage_displayed_when_theoretical_exceeds_actual(self):
        self.client.post(
            f"/inventory/{self.day1}/tank/{self.tank.id}/opening/",
            {"opening_quantity": "1000"},
        )
        self.client.post(
            f"/inventory/{self.day1}/tank/{self.tank.id}/actual/",
            {"actual_inventory": "900"},  # theoretical=1000 -> shortage=100
        )
        resp = self.client.get(f"/inventory/{self.day1}/")
        self.assertContains(resp, "100")

    def test_future_date_inventory_entry_blocked(self):
        resp = self.client.post(
            f"/inventory/2099-01-01/tank/{self.tank.id}/actual/",
            {"actual_inventory": "100"},
            follow=True,
        )
        self.assertContains(resp, "آینده")
        self.assertEqual(TankInventory.objects.count(), 0)

    def test_editing_actual_inventory_does_not_duplicate_row(self):
        self.client.post(
            f"/inventory/{self.day1}/tank/{self.tank.id}/opening/",
            {"opening_quantity": "0"},
        )
        self.client.post(
            f"/inventory/{self.day1}/tank/{self.tank.id}/actual/",
            {"actual_inventory": "100"},
        )
        self.client.post(
            f"/inventory/{self.day1}/tank/{self.tank.id}/actual/",
            {"actual_inventory": "150"},
        )
        self.assertEqual(
            TankInventory.objects.filter(tank=self.tank, working_day__date=self.day1).count(), 1
        )
        self.assertEqual(
            TankInventory.objects.get(tank=self.tank, working_day__date=self.day1).actual_inventory,
            Decimal("150"),
        )
