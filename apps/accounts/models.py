"""
Operator extends Django's built-in User (authentication is Django's own
built-in system -- not custom) purely to identify which User is an
operator of this station. The actual "last used username" for login-field
prefill is a single global value (not per-user), stored on
apps.core.models.AppConfig, since it must reflect whichever operator most
recently logged in across the whole application.
"""

from django.conf import settings
from django.db import models


class Operator(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="operator_profile"
    )

    class Meta:
        verbose_name = "Operator"
        verbose_name_plural = "Operators"

    def __str__(self):
        return self.user.get_username()
