"""
Purchase views: choosing a working date (reuses the same chronology rules
as sales -- rule 10), entering a purchase for a tank/product (rule 1: any
number of these per day), and a purchase invoice list with derived daily
totals (rule 7).

No business math lives here -- only orchestration of purchases/services.py
and workday/services.py, per rule 9.
"""

import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.sales.forms import WorkingDateForm
from apps.stations.models import Tank
from apps.workday import services as workday_services
from apps.workday.models import DailyWorkingDay

from . import services as purchase_services
from .forms import PurchaseInvoiceForm
from .models import PurchaseInvoice


def _parse_date(date_str: str) -> datetime.date:
    return datetime.date.fromisoformat(date_str)


@login_required
def choose_working_date(request):
    """
    Entry point for "خرید" in the nav. Purchases obey the same chronology
    system as sales (rule 10) -- this deliberately reuses
    workday_services.can_enter_date() rather than introducing a separate
    date system, and reuses sales' WorkingDateForm since the shape is
    identical (a single date field).
    """
    next_required = workday_services.get_next_required_date()
    initial = {"date": next_required} if next_required else {}

    if request.method == "POST":
        form = WorkingDateForm(request.POST)
        if form.is_valid():
            date = form.cleaned_data["date"]
            allowed, reason = workday_services.can_enter_date(date)
            if not allowed:
                form.add_error("date", reason)
            else:
                return redirect("purchases:invoice_list_for_day", date=date.isoformat())
    else:
        form = WorkingDateForm(initial=initial)

    context = {
        "form": form,
        "next_required_date": next_required,
        "incomplete_days": workday_services.get_incomplete_days(),
    }
    return render(request, "purchases/choose_date.html", context)


@login_required
def invoice_list_for_day(request, date):
    """
    Lists all PurchaseInvoice records for this working day (rule 1: there
    may be zero, one, or many), grouped by tank/product, with the derived
    daily total per tank (rule 7). Purchases are optional -- an empty list
    here is a valid, complete state, never a blocking condition (rule 8).
    """
    working_day, _ = DailyWorkingDay.objects.get_or_create(date=_parse_date(date))
    allowed, reason = workday_services.can_enter_date(working_day.date)
    if not allowed:
        messages.error(request, reason)
        return redirect("purchases:choose_date")

    tanks = Tank.objects.select_related("product").order_by("product__name")
    tank_rows = []
    for tank in tanks:
        invoices = PurchaseInvoice.objects.filter(
            tank=tank, working_day=working_day
        ).order_by("id")
        tank_rows.append({
            "tank": tank,
            "invoices": invoices,
            "daily_total": purchase_services.get_daily_purchase_total(tank, working_day),
        })

    return render(
        request, "purchases/invoice_list_for_day.html",
        {"working_day": working_day, "tank_rows": tank_rows},
    )


@login_required
def purchase_entry(request, date, tank_id):
    """
    Creates a new PurchaseInvoice for this tank/day. Never edits/replaces
    an existing one implicitly -- each unloading event is its own record
    (rule 1), so this view only ever adds; editing a specific invoice is a
    separate view (purchase_edit) that never changes its working_day.
    """
    working_day, _ = DailyWorkingDay.objects.get_or_create(date=_parse_date(date))
    allowed, reason = workday_services.can_enter_date(working_day.date)
    if not allowed:
        messages.error(request, reason)
        return redirect("purchases:choose_date")

    tank = get_object_or_404(Tank, pk=tank_id)

    # Rate suggestion: most recently used rate for this PRODUCT (via this
    # tank, since each tank has exactly one product) -- rules 5 and 6.
    # Regular and Super are naturally independent here because each is a
    # separate Tank row; nothing shares a rate across products.
    suggested_rate = purchase_services.get_most_recent_rate(tank)
    initial = {"purchase_rate": suggested_rate} if suggested_rate is not None else {}

    if request.method == "POST":
        form = PurchaseInvoiceForm(request.POST)
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.working_day = working_day
            invoice.tank = tank
            invoice.save()
            messages.success(request, "فاکتور خرید ثبت شد.")
            return redirect("purchases:invoice_list_for_day", date=date)
    else:
        form = PurchaseInvoiceForm(initial=initial)

    return render(
        request, "purchases/purchase_entry.html",
        {"form": form, "working_day": working_day, "tank": tank},
    )


@login_required
def purchase_edit(request, date, pk):
    """
    Edits an existing PurchaseInvoice. Its working_day and original
    entry are never reassigned here -- only the editable business fields
    change, consistent with the project-wide editing rule that a
    record's original working date is never altered by an edit.
    """
    working_day, _ = DailyWorkingDay.objects.get_or_create(date=_parse_date(date))
    invoice = get_object_or_404(PurchaseInvoice, pk=pk, working_day=working_day)

    allowed, reason = workday_services.can_enter_date(working_day.date)
    if not allowed:
        messages.error(request, reason)
        return redirect("purchases:choose_date")

    if request.method == "POST":
        form = PurchaseInvoiceForm(request.POST, instance=invoice)
        if form.is_valid():
            form.save()
            messages.success(request, "فاکتور خرید بروزرسانی شد.")
            return redirect("purchases:invoice_list_for_day", date=date)
    else:
        form = PurchaseInvoiceForm(instance=invoice)

    return render(
        request, "purchases/purchase_entry.html",
        {"form": form, "working_day": working_day, "tank": invoice.tank, "editing": True},
    )
