"""
core holds cross-cutting, single-row configuration -- values that belong
to the application as a whole rather than to any one bounded business
concept.
"""

from django.db import models


class AppConfig(models.Model):
    """
    Singleton row (always pk=1) for small global values that don't warrant
    their own app/table. Use AppConfig.get_solo() to fetch-or-create it.
    """

    last_logged_in_username = models.CharField(max_length=150, blank=True)

    class Meta:
        verbose_name = "Application Configuration"
        verbose_name_plural = "Application Configuration"

    def __str__(self):
        return "Application configuration"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
