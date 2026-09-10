"""purchases/services.py -- purchase-side aggregation logic."""

from decimal import Decimal

from django.db.models import Sum

from .models import PurchaseInvoice


def get_daily_purchase_total(tank, working_day) -> Decimal:
    """Sum of all PurchaseInvoice.quantity for this tank/day -- multiple
    invoices per day are expected and all contribute."""
    result = PurchaseInvoice.objects.filter(
        tank=tank, working_day=working_day
    ).aggregate(total=Sum("quantity"))["total"]
    return result if result is not None else Decimal("0")


def get_most_recent_rate(tank) -> Decimal | None:
    """Most recently used purchase rate for this tank's product, suggested
    as the default for the next purchase entry."""
    last = (
        PurchaseInvoice.objects.filter(tank=tank)
        .order_by("-working_day__date", "-id")
        .first()
    )
    return last.purchase_rate if last else None


def get_monthly_unloading_count(tank, year: int, month: int) -> int:
    """Monthly tanker count = number of unloading EVENTS, not unique
    plates -- one tanker unloading three times counts as 3."""
    return PurchaseInvoice.objects.filter(
        tank=tank,
        working_day__date__year=year,
        working_day__date__month=month,
    ).count()
