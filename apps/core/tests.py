import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.license.models import License
from apps.stations.models import Station, Product, Tank, Nozzle

User = get_user_model()


class DashboardSmokeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="op1", password="testpass123")
        License.objects.create(start_date=datetime.date.today(), duration_days=365)
        station = Station.objects.create(name="140 Jahan Pour", province="Razavi Khorasan", city="Mashhad")
        regular = Product.objects.create(name="Regular")
        super_ = Product.objects.create(name="Super")
        self.regular_tank = Tank.objects.create(station=station, product=regular, capacity=50000)
        self.super_tank = Tank.objects.create(station=station, product=super_, capacity=30000)
        for n in list(range(1, 19)) + [25, 26]:
            Nozzle.objects.create(tank=self.regular_tank, number=n)
        for n in range(19, 25):
            Nozzle.objects.create(tank=self.super_tank, number=n)

    def test_login_page_loads(self):
        resp = self.client.get("/accounts/login/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="username"')

    def test_login_prefills_last_used_username(self):
        self.client.post("/accounts/login/", {"username": "op1", "password": "testpass123"})
        self.client.logout()
        resp = self.client.get("/accounts/login/")
        self.assertContains(resp, 'value="op1"')

    def test_successful_login_redirects_to_dashboard(self):
        resp = self.client.post(
            "/accounts/login/", {"username": "op1", "password": "testpass123"}, follow=True
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "کارکرد مخازن")
        self.assertContains(resp, "کارکرد نازل\u200cها")

    def test_dashboard_shows_all_26_nozzles(self):
        self.client.login(username="op1", password="testpass123")
        resp = self.client.get("/")
        content = resp.content.decode()
        rendered_count = content.count('class="nozzle-grid__item"')
        self.assertEqual(rendered_count, 26)

    def test_dashboard_shows_license_valid_badge(self):
        self.client.login(username="op1", password="testpass123")
        resp = self.client.get("/")
        self.assertContains(resp, "لایسنس تا 365 روز دیگر معتبر است")

    def test_anonymous_user_redirected_to_login(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_expired_license_redirects_to_renewal(self):
        License.objects.all().delete()
        License.objects.create(
            start_date=datetime.date.today() - datetime.timedelta(days=400),
            duration_days=365,
        )
        self.client.login(username="op1", password="testpass123")
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/license/renew/", resp.url)

    def test_renewal_page_reachable_even_when_expired(self):
        License.objects.all().delete()
        License.objects.create(
            start_date=datetime.date.today() - datetime.timedelta(days=400),
            duration_days=365,
        )
        self.client.login(username="op1", password="testpass123")
        resp = self.client.get("/license/renew/")
        self.assertEqual(resp.status_code, 200)

    def test_correct_renewal_password_restores_access(self):
        License.objects.all().delete()
        License.objects.create(
            start_date=datetime.date.today() - datetime.timedelta(days=400),
            duration_days=365,
        )
        self.client.login(username="op1", password="testpass123")
        resp = self.client.post(
            "/license/renew/", {"password": "769112005a@"}, follow=True
        )
        self.assertContains(resp, "کارکرد مخازن")

    def test_each_nozzle_button_links_to_its_own_ledger(self):
        """
        Clicking a nozzle on the dashboard must take the operator to
        گزارش کارکرد هر نازل for THAT nozzle -- not to the sales entry
        screen. Checked for every one of the 26 seeded nozzles, not just
        one, since each button's link is built from that nozzle's own id.
        """
        self.client.login(username="op1", password="testpass123")
        resp = self.client.get("/")
        content = resp.content.decode()

        for nozzle in Nozzle.objects.all():
            expected_href = f'/reports/nozzle-ledger/?nozzle_id={nozzle.id}'
            self.assertIn(expected_href, content)

        # The old destination must be gone entirely.
        self.assertNotIn('sales/invoices/', content)

    def test_clicking_a_nozzle_shows_that_exact_nozzles_report(self):
        nozzle_1 = Nozzle.objects.get(tank=self.regular_tank, number=1)
        nozzle_19 = Nozzle.objects.get(tank=self.super_tank, number=19)

        self.client.login(username="op1", password="testpass123")

        resp1 = self.client.get(f"/reports/nozzle-ledger/?nozzle_id={nozzle_1.id}")
        self.assertContains(resp1, "نازل 1 (")

        resp19 = self.client.get(f"/reports/nozzle-ledger/?nozzle_id={nozzle_19.id}")
        self.assertContains(resp19, "نازل 19 (")
