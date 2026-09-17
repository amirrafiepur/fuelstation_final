"""
Seal forms. NozzleSeal is event-based, not a daily record -- this form
carries no chronology/working-day dependency, unlike sales/purchases/
inventory.
"""

from django import forms

from apps.core.jalali import JalaliDateField, JalaliDateWidget

from .models import NozzleSeal


class NozzleSealForm(forms.ModelForm):
    # Declared explicitly, same reasoning as DepositForm: NozzleSeal.date
    # is a plain models.DateField, and ModelForm would otherwise generate
    # a Gregorian-only forms.DateField for it.
    date = JalaliDateField(label="تاریخ", widget=JalaliDateWidget())

    class Meta:
        model = NozzleSeal
        fields = ["nozzle", "section", "date", "seal_number"]
        widgets = {
            "nozzle": forms.Select(attrs={"class": "form-input"}),
            "section": forms.Select(attrs={"class": "form-input"}),
            "seal_number": forms.TextInput(attrs={"class": "form-input", "autofocus": True}),
        }
        labels = {
            "nozzle": "نازل",
            "section": "بخش",
            "seal_number": "شماره پلمپ",
        }
