from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Operator
from apps.license.models import License
from apps.license import services as license_services


User = get_user_model()


class SingleOperatorFirstRunTests(TestCase):
    def test_fresh_install_allows_first_setup(self):
        response = self.client.get(reverse("accounts:first_setup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "اولین حساب کاربری")
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(License.objects.count(), 0)

    def test_first_setup_creates_only_operator_and_starts_license(self):
        before = timezone.localdate()
        response = self.client.post(
            reverse("accounts:first_setup"),
            {"username": "operator", "password1": "StrongPass123!", "password2": "StrongPass123!"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)
        user = User.objects.get(username="operator")
        self.assertTrue(user.check_password("StrongPass123!"))
        self.assertTrue(Operator.objects.filter(user=user).exists())
        self.assertEqual(License.objects.count(), 1)
        self.assertEqual(License.objects.get().start_date, before)
        self.assertTrue(license_services.is_license_valid())
        self.assertIn("کارکرد مخازن", response.content.decode())

    def test_first_setup_does_not_reset_an_existing_license(self):
        user = User.objects.create_user(username="operator", password="StrongPass123!")
        Operator.objects.create(user=user)
        old_start = timezone.localdate() - timezone.timedelta(days=30)
        License.objects.create(start_date=old_start, duration_days=365)

        response = self.client.post(
            reverse("accounts:first_setup"),
            {"username": "second", "password1": "StrongPass123!", "password2": "StrongPass123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(License.objects.get().start_date, old_start)
        self.assertEqual(User.objects.count(), 1)

    def test_first_setup_is_unavailable_after_first_account(self):
        user = User.objects.create_user(username="operator", password="StrongPass123!")
        Operator.objects.create(user=user)
        License.objects.create(start_date=timezone.localdate(), duration_days=365)

        response = self.client.get(reverse("accounts:first_setup"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith("/accounts/login/"))

    def test_second_account_cannot_be_created_through_first_setup(self):
        User.objects.create_user(username="operator", password="StrongPass123!")
        License.objects.create(start_date=timezone.localdate(), duration_days=365)

        response = self.client.post(
            reverse("accounts:first_setup"),
            {"username": "second", "password1": "StrongPass123!", "password2": "StrongPass123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(User.objects.filter(username="second").exists())

    def test_login_is_available_on_fresh_install_without_license(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)

    def test_first_setup_activates_license_only_once(self):
        self.client.post(
            reverse("accounts:first_setup"),
            {"username": "operator", "password1": "StrongPass123!", "password2": "StrongPass123!"},
        )
        first_start = License.objects.get().start_date
        license_services.activate_license(as_of=first_start + timezone.timedelta(days=10))
        self.assertEqual(License.objects.count(), 1)
        self.assertEqual(License.objects.get().start_date, first_start)

    def test_renewal_without_a_license_does_not_activate_one(self):
        self.assertFalse(license_services.renew_license("any-password"))
        self.assertEqual(License.objects.count(), 0)

    def test_login_does_not_create_a_user(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "operator", "password": "StrongPass123!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 0)
