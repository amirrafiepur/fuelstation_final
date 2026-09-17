"""
Centralized Gregorian <-> Jalali (Persian/Shamsi) date conversion.

Architecture (see project handoff doc, "Convert Application Dates from
Gregorian to Jalali"):
  - The database, all business logic, chronology, and internal date
    comparisons continue to use plain Gregorian datetime.date objects.
    Nothing here ever touches a model field or a stored value.
  - Only the presentation layer (templates, print templates, and the
    two form widgets that let an operator type/pick a date) converts
    to/from Jalali. Every other date-touching module is unaffected.
  - This is the single place that import/use jdatetime, so there is
    exactly one conversion implementation to test and maintain --
    nothing else in the codebase should import jdatetime directly.

Library choice: jdatetime (pure Python, zero dependencies, actively
maintained) -- a good fit for the packaged desktop build's low-resource
Windows target, unlike heavier alternatives that pull in C extensions.
"""

from __future__ import annotations

import datetime

import jdatetime
from django import forms

JALALI_DATE_FORMAT = "%Y/%m/%d"


def to_jalali(value: datetime.date | None) -> jdatetime.date | None:
    """Gregorian -> Jalali. Accepts date or datetime; returns None for None."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        value = value.date()
    return jdatetime.date.fromgregorian(date=value)


def to_gregorian(value: jdatetime.date | None) -> datetime.date | None:
    """Jalali -> Gregorian. Returns None for None."""
    if value is None:
        return None
    return value.togregorian()


def format_jalali(value: datetime.date | None) -> str:
    """Gregorian date -> 'YYYY/MM/DD' Jalali string for display. Empty
    string for None so templates don't need a separate null check."""
    j = to_jalali(value)
    if j is None:
        return ""
    return j.strftime(JALALI_DATE_FORMAT)


def parse_jalali(text: str) -> datetime.date:
    """
    'YYYY/MM/DD' or 'YYYY-MM-DD' Jalali string -> Gregorian date.
    Raises ValueError on anything else, matching datetime.date.fromisoformat's
    contract so callers (form field .clean(), JS-submitted values) can
    handle it the same way they already handle Gregorian parse errors.
    """
    text = (text or "").strip()
    normalized = text.replace("-", "/")
    parts = normalized.split("/")
    if len(parts) != 3:
        raise ValueError(f"Invalid Jalali date: {text!r}")
    year, month, day = (int(p) for p in parts)
    j = jdatetime.date(year, month, day)
    return j.togregorian()


class JalaliDateWidget(forms.TextInput):
    """
    A plain text input that displays and accepts Jalali dates
    ('YYYY/MM/DD'), backed by the same client-side calendar widget used
    for the global Date Control (static/js/jalali.js). The value that
    ends up in the widget's HTML is Jalali text for the operator to
    read/type; JalaliDateField below converts it to/from a Gregorian
    date object at the form boundary, so views and models never see
    anything but ordinary Gregorian dates.
    """

    def __init__(self, attrs=None):
        default_attrs = {"class": "form-input jalali-date-field", "inputmode": "numeric", "autocomplete": "off"}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)

    def format_value(self, value):
        if value is None or value == "":
            return ""
        if isinstance(value, str):
            # Re-displaying a bound/invalid submission: show back exactly
            # what the operator typed rather than silently altering it.
            return value
        return format_jalali(value)

    class Media:
        js = ("js/jalali.js", "js/jalali_date_field.js")


class JalaliDateField(forms.DateField):
    """
    Drop-in replacement for forms.DateField that reads/writes Jalali text
    but produces an ordinary Gregorian datetime.date in cleaned_data --
    exactly like forms.DateField already does internally, just with a
    Jalali-aware widget and parser instead of Gregorian ISO parsing.
    """

    widget = JalaliDateWidget

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, datetime.date):
            return value
        try:
            return parse_jalali(value)
        except (ValueError, TypeError) as exc:
            raise forms.ValidationError(self.error_messages["invalid"], code="invalid") from exc
