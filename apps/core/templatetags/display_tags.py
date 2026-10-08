"""
Template-side entry point for presentation-only display formatting.
See apps/core/display.py for the actual logic and why it exists.

Usage:
  {{ product.name|persian_product }} -> "بنزین معمولی"
  {{ sale.total_amount|trim_zeros }}  -> "35" instead of "35.00"
"""

from django import template

from apps.core.display import persian_product_name, trim_trailing_zeros

register = template.Library()


@register.filter(name="persian_product")
def persian_product(value):
    """Product.name -> Persian display label. Falls back to the raw
    value unchanged for anything not in the known mapping."""
    return persian_product_name(value)


@register.filter(name="trim_zeros")
def trim_zeros(value):
    """Drops an unnecessary trailing .00 (or similar) from a displayed
    number. Display-only -- see trim_trailing_zeros()'s docstring."""
    return trim_trailing_zeros(value)
