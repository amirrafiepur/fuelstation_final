"""
Template-side entry point for presentation-only display-name mapping.
See apps/core/display.py for the actual mapping and why it exists.

Usage: {{ product.name|persian_product }} -> "بنزین معمولی"
"""

from django import template

from apps.core.display import persian_product_name

register = template.Library()


@register.filter(name="persian_product")
def persian_product(value):
    """Product.name -> Persian display label. Falls back to the raw
    value unchanged for anything not in the known mapping."""
    return persian_product_name(value)
