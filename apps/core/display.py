"""
Presentation-layer display helpers.

These translate how certain existing database values are SHOWN to the
user, without changing the stored values, model choices, internal
identifiers, or any business/calculation logic that reads those values
directly -- per this project's Persianization task, which is explicit
that only the user-facing display changes. trim_trailing_zeros() below
follows the same rule for numeric display (see its own docstring).
"""

from decimal import Decimal, InvalidOperation

#: Product.name is free text (see apps/stations/models.py's Product
#: docstring: "Kept extensible -- product additions shouldn't require
#: code changes"), so this is a lookup, not a model-level choices list.
#: Any name not in this mapping (a future third product, say) is
#: returned unchanged -- this never breaks for products added later.
_PRODUCT_PERSIAN_DISPLAY = {
    "Regular": "بنزین معمولی",
    "Super": "بنزین سوپر",
}


def persian_product_name(name: str) -> str:
    """Map a Product.name value to its Persian display label."""
    return _PRODUCT_PERSIAN_DISPLAY.get(name, name)


def trim_trailing_zeros(value):
    """
    Display-only formatting for a stored DecimalField value: drops an
    unnecessary trailing ".00"/".50" tail of zeros (35.00 -> "35",
    100.00 -> "100", 1.50 -> "1.5") while leaving a genuine fractional
    value untouched (1.25 -> "1.25"). Never touches the stored value --
    this only ever formats a value already read from the database for
    display; the DecimalField's own precision/scale in the database is
    completely unaffected.

    Deliberately does NOT use Decimal.normalize(), which can flip into
    scientific notation for whole numbers (e.g. Decimal("100").normalize()
    -> Decimal('1E+2')) -- format(d, 'f') always yields a plain
    fixed-point string, which is then trimmed by hand.

    Anything that isn't a valid number (None, "", a non-numeric string)
    passes through unchanged, so this is always safe to apply broadly.
    """
    if value is None:
        return value
    try:
        d = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value

    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text if text not in ("", "-") else "0"
