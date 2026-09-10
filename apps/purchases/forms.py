"""
Purchase forms.

Per the mandatory Phase 5 rules: no uniqueness validation is applied to
tanker_number or document_number (rule 2), and tanker_capacity carries no
restriction of any kind (rule 3) -- this form must never add validation
beyond what the model already omits.
"""

from django import forms

from .models import PurchaseInvoice


class PurchaseInvoiceForm(forms.ModelForm):
    class Meta:
        model = PurchaseInvoice
        fields = [
            "unloading_time", "program_number", "tanker_number",
            "tanker_capacity", "quantity", "purchase_rate", "document_number",
        ]
        widgets = {
            "unloading_time": forms.TimeInput(attrs={"type": "time", "class": "form-input"}),
            "program_number": forms.TextInput(attrs={"class": "form-input"}),
            "tanker_number": forms.TextInput(attrs={"class": "form-input"}),
            "tanker_capacity": forms.NumberInput(attrs={"class": "form-input numeric"}),
            "quantity": forms.NumberInput(attrs={"class": "form-input numeric", "autofocus": True}),
            "purchase_rate": forms.NumberInput(attrs={"class": "form-input numeric", "step": "0.01"}),
            "document_number": forms.TextInput(attrs={"class": "form-input"}),
        }
        labels = {
            "unloading_time": "زمان تخلیه",
            "program_number": "شماره برنامه",
            "tanker_number": "شماره تانکر",
            "tanker_capacity": "ظرفیت تانکر (لیتر)",
            "quantity": "مقدار خرید (لیتر)",
            "purchase_rate": "نرخ خرید",
            "document_number": "شماره سند/فاکتور",
        }
