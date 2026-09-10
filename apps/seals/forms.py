"""
Seal forms. NozzleSeal is event-based, not a daily record -- this form
carries no chronology/working-day dependency, unlike sales/purchases/
inventory.
"""

from django import forms

from .models import NozzleSeal


class NozzleSealForm(forms.ModelForm):
    class Meta:
        model = NozzleSeal
        fields = ["nozzle", "section", "date", "seal_number"]
        widgets = {
            "nozzle": forms.Select(attrs={"class": "form-input"}),
            "section": forms.Select(attrs={"class": "form-input"}),
            "date": forms.DateInput(attrs={"type": "date", "class": "form-input"}),
            "seal_number": forms.TextInput(attrs={"class": "form-input", "autofocus": True}),
        }
        labels = {
            "nozzle": "نازل",
            "section": "بخش",
            "date": "تاریخ",
            "seal_number": "شماره پلمپ",
        }
