"""
Presentation-layer display-name helpers.

These translate how certain existing database values are SHOWN to the
user, without changing the stored values, model choices, internal
identifiers, or any business/calculation logic that reads those values
directly -- per this project's Persianization task, which is explicit
that only the user-facing display changes.
"""

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
