import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.license.models import License
from apps.stations.models import Station, Product, Tank, Nozzle

from .models import NozzleSeal

User = get_user_model()


class SealHttpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="op1", password="testpass123")
        License.objects.create(start_date=datetime.date(2026, 8, 1), duration_days=365)
        station = Station.objects.create(name="S", province="P", city="C")
        product = Product.objects.create(name="Regular")
        tank = Tank.objects.create(station=station, product=product, capacity=50000)
        self.nozzle = Nozzle.objects.create(tank=tank, number=1)
        self.client.login(username="op1", password="testpass123")

    def test_seal_list_renders_empty(self):
        resp = self.client.get("/seals/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "پلمپی ثبت نشده است")

    def test_create_seal(self):
        resp = self.client.post("/seals/new/", {
            "nozzle": self.nozzle.id,
            "section": NozzleSeal.FLAG_DOOR_1,
            "date": "1405/05/10",
            "seal_number": "SN-001",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(NozzleSeal.objects.count(), 1)
        seal = NozzleSeal.objects.first()
        self.assertEqual(seal.seal_number, "SN-001")

    def test_seal_is_event_based_not_daily(self):
        """Multiple seals for the same nozzle on different (or the same)
        dates are all independently stored -- no daily uniqueness."""
        self.client.post("/seals/new/", {
            "nozzle": self.nozzle.id, "section": NozzleSeal.FLAG_DOOR_1,
            "date": "1405/05/10", "seal_number": "SN-001",
        })
        self.client.post("/seals/new/", {
            "nozzle": self.nozzle.id, "section": NozzleSeal.FLAG_DOOR_1,
            "date": "1405/05/10", "seal_number": "SN-002",
        })
        self.assertEqual(NozzleSeal.objects.filter(nozzle=self.nozzle).count(), 2)

    def test_edit_seal(self):
        seal = NozzleSeal.objects.create(
            nozzle=self.nozzle, section=NozzleSeal.PUMP_DOOR_1,
            date=datetime.date(2026, 8, 1), seal_number="OLD-001",
        )
        resp = self.client.post(f"/seals/{seal.pk}/edit/", {
            "nozzle": self.nozzle.id, "section": NozzleSeal.PUMP_DOOR_1,
            "date": "1405/05/10", "seal_number": "NEW-001",
        })
        self.assertEqual(resp.status_code, 302)
        seal.refresh_from_db()
        self.assertEqual(seal.seal_number, "NEW-001")

    def test_delete_seal_requires_post_confirmation(self):
        seal = NozzleSeal.objects.create(
            nozzle=self.nozzle, section=NozzleSeal.PUMP_DOOR_1,
            date=datetime.date(2026, 8, 1), seal_number="SN-001",
        )
        # GET shows confirmation, does not delete.
        resp_get = self.client.get(f"/seals/{seal.pk}/delete/")
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(NozzleSeal.objects.count(), 1)

        # POST actually deletes.
        resp_post = self.client.post(f"/seals/{seal.pk}/delete/")
        self.assertEqual(resp_post.status_code, 302)
        self.assertEqual(NozzleSeal.objects.count(), 0)

    def test_seal_list_shows_created_seal(self):
        NozzleSeal.objects.create(
            nozzle=self.nozzle, section=NozzleSeal.FLAG_DOOR_2,
            date=datetime.date(2026, 8, 1), seal_number="SN-777",
        )
        resp = self.client.get("/seals/")
        self.assertContains(resp, "SN-777")


class SealFormPersianizationTests(TestCase):
    """
    2.3: the نازل dropdown must show "نازل N" (not the model's internal
    "Nozzle N" __str__). 2.4: the بخش field's options must be Persian,
    while the stored values (flag_door_1 etc.) are unchanged.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="op_seal_disp", password="testpass123")
        License.objects.create(start_date=datetime.date(2026, 8, 1), duration_days=365)
        station = Station.objects.create(name="S2", province="P", city="C")
        product = Product.objects.create(name="Regular")
        tank = Tank.objects.create(station=station, product=product, capacity=50000)
        self.nozzle = Nozzle.objects.create(tank=tank, number=5)
        self.client.login(username="op_seal_disp", password="testpass123")

    def test_nozzle_dropdown_shows_persian_label_not_english(self):
        resp = self.client.get("/seals/new/")
        content = resp.content.decode()
        self.assertIn("نازل 5", content)
        self.assertNotIn("Nozzle 5", content)

    def test_section_field_options_are_persian(self):
        resp = self.client.get("/seals/new/")
        content = resp.content.decode()
        for label in ["درب پرچمی 1", "درب پرچمی 2", "درب تلمبه 1", "درب تلمبه 2"]:
            self.assertIn(label, content)
        for old_label in ["Flag Door 1", "Flag Door 2", "Pump Door 1", "Pump Door 2"]:
            self.assertNotIn(old_label, content)

    def test_section_stored_value_unchanged_after_submit(self):
        resp = self.client.post("/seals/new/", {
            "nozzle": self.nozzle.id, "section": NozzleSeal.FLAG_DOOR_1,
            "date": "1405/06/05", "seal_number": "SEAL-1",
        })
        self.assertEqual(resp.status_code, 302)
        seal = NozzleSeal.objects.get()
        self.assertEqual(seal.section, "flag_door_1")
