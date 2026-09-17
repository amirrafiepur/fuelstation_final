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
