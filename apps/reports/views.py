"""
Report views: read-only derived views that call reports/services.py
aggregations and render them without any business logic in the template.
"""

import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.stations.models import Nozzle, Tank
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

    # Default date range: current month
    end_date = today
    start_date = datetime.date(today.year, today.month, 1)

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
def nozzle_performance_monthly(request):
    """
    Monthly Nozzle Performance Report: per-nozzle monthly totals for a
    chosen year/month.
    """
    today = workday_services.get_today()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))

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

    # Default date range: current month
    end_date = today
    start_date = datetime.date(today.year, today.month, 1)

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
    """
    today = workday_services.get_today()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))

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
