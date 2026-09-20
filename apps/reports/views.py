"""
Report views: read-only derived views that call reports/services.py
aggregations and render them without any business logic in the template.
"""

import datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.jalali import current_jalali_year_month, jalali_month_bounds
from apps.stations.models import Nozzle, Product, Tank
from apps.workday import services as workday_services

from . import services as report_services


@login_required
def nozzle_performance_ledger(request, nozzle_id=None):
    """
    Nozzle Performance Ledger (F5): per-nozzle daily breakdown showing
    Operation/Mechanical Sales/Sales/Total Amount for a date range.
    """
    today = workday_services.get_today()
    accounting_start = workday_services.get_accounting_start_date()

    # Default date range: the current JALALI month (the period the
    # operator actually thinks in), not the Gregorian calendar month --
    # start_date is day 1 of the current Jalali month, converted to
    # Gregorian for the query, so its Jalali display is correctly
    # "1405/06/01" rather than a mid-month Gregorian date reinterpreted
    # as Jalali.
    jalali_year, jalali_month = current_jalali_year_month(today)
    start_date, _ = jalali_month_bounds(jalali_year, jalali_month)
    end_date = today

    if request.GET.get("nozzle_id"):
        nozzle_id = int(request.GET.get("nozzle_id"))
    if request.GET.get("start_date"):
        start_date = datetime.date.fromisoformat(request.GET.get("start_date"))
    if request.GET.get("end_date"):
        end_date = datetime.date.fromisoformat(request.GET.get("end_date"))

    nozzles = Nozzle.objects.select_related("tank__product").order_by("number")
    selected_nozzle = None
    rows = []

    if nozzle_id:
        selected_nozzle = Nozzle.objects.get(pk=nozzle_id)
        rows = report_services.nozzle_performance_ledger(
            selected_nozzle, start_date, end_date
        )

    return render(
        request, "reports/nozzle_performance_ledger.html",
        {
            "nozzles": nozzles,
            "selected_nozzle": selected_nozzle,
            "rows": rows,
            "start_date": start_date,
            "end_date": end_date,
        },
    )


@login_required
def all_nozzles_performance(request):
    """
    کارکرد تمام نازل‌ها: one row per working day, each the SUM across
    every nozzle -- a deliberately separate view/URL from
    nozzle_performance_ledger() above (which is untouched), per that
    report's own requirement not to reuse the per-nozzle view.
    """
    today = workday_services.get_today()

    # Default date range: current JALALI month -- identical convention
    # to nozzle_performance_ledger()/petroleum_inventory_operations_ledger()
    # above.
    jalali_year, jalali_month = current_jalali_year_month(today)
    start_date, _ = jalali_month_bounds(jalali_year, jalali_month)
    end_date = today

    if request.GET.get("start_date"):
        start_date = datetime.date.fromisoformat(request.GET.get("start_date"))
    if request.GET.get("end_date"):
        end_date = datetime.date.fromisoformat(request.GET.get("end_date"))

    rows = report_services.all_nozzles_performance_summary(start_date, end_date)

    # Products in a stable order (matches the ordering used elsewhere,
    # e.g. the per-nozzle ledger's own dropdown) -- never hardcoded names,
    # so "فروش فرآورده معمولی"/"فروش فرآورده سوپر" map to whichever two
    # products actually exist, in this order. Each row gets its
    # per-product totals attached as a same-order list ("product_totals")
    # so the template can iterate rows/products in parallel without
    # needing a dict-by-variable-key template filter.
    products = Product.objects.order_by("name")
    for row in rows:
        row["product_totals"] = [
            row["by_product"].get(product.id, Decimal("0")) for product in products
        ]

    return render(
        request, "reports/all_nozzles_performance.html",
        {
            "rows": rows,
            "products": products,
            "start_date": start_date,
            "end_date": end_date,
        },
    )


@login_required
def nozzle_performance_monthly(request):
    """
    Monthly Nozzle Performance Report: per-nozzle monthly totals for a
    chosen year/month.

    year/month here are JALALI (the operator picks/reads e.g. 1405/06,
    not a Gregorian month) -- see reports/services.py's
    nozzle_performance_monthly() docstring.
    """
    today = workday_services.get_today()
    default_year, default_month = current_jalali_year_month(today)
    year = int(request.GET.get("year", default_year))
    month = int(request.GET.get("month", default_month))

    nozzles = Nozzle.objects.select_related("tank__product").order_by("number")
    rows = []

    for nozzle in nozzles:
        report = report_services.nozzle_performance_monthly(nozzle, year, month)
        if report:
            rows.append(report)

    return render(
        request, "reports/nozzle_performance_monthly.html",
        {"rows": rows, "year": year, "month": month},
    )


@login_required
def petroleum_inventory_operations_ledger(request, tank_id=None):
    """
    Petroleum Inventory & Operations Ledger (F6): per-tank daily breakdown
    showing Purchases/Test Returns/Sales/Inventory computations for a date
    range.
    """
    today = workday_services.get_today()
    accounting_start = workday_services.get_accounting_start_date()

    # Default date range: current JALALI month -- see the identical
    # comment in nozzle_performance_ledger() above.
    jalali_year, jalali_month = current_jalali_year_month(today)
    start_date, _ = jalali_month_bounds(jalali_year, jalali_month)
    end_date = today

    if request.GET.get("tank_id"):
        tank_id = int(request.GET.get("tank_id"))
    if request.GET.get("start_date"):
        start_date = datetime.date.fromisoformat(request.GET.get("start_date"))
    if request.GET.get("end_date"):
        end_date = datetime.date.fromisoformat(request.GET.get("end_date"))

    tanks = Tank.objects.select_related("product").order_by("product__name")
    selected_tank = None
    rows = []

    if tank_id:
        selected_tank = Tank.objects.get(pk=tank_id)
        rows = report_services.petroleum_inventory_operations_ledger(
            selected_tank, start_date, end_date
        )

    return render(
        request, "reports/petroleum_inventory_ledger.html",
        {
            "tanks": tanks,
            "selected_tank": selected_tank,
            "rows": rows,
            "start_date": start_date,
            "end_date": end_date,
        },
    )


@login_required
def petroleum_inventory_monthly(request):
    """
    Monthly Tank Statement: per-tank monthly totals for a chosen year/month.

    year/month here are JALALI -- see
    reports/services.py's petroleum_inventory_monthly() docstring.
    """
    today = workday_services.get_today()
    default_year, default_month = current_jalali_year_month(today)
    year = int(request.GET.get("year", default_year))
    month = int(request.GET.get("month", default_month))

    tanks = Tank.objects.select_related("product").order_by("product__name")
    rows = []

    for tank in tanks:
        report = report_services.petroleum_inventory_monthly(tank, year, month)
        if report:
            rows.append(report)

    return render(
        request, "reports/petroleum_inventory_monthly.html",
        {"rows": rows, "year": year, "month": month},
    )
