"""
Printing is a presentation/output layer only. Every printable report
pulls its data exclusively from reports/services.py (or, for the metadata
block, the Station model) -- this module NEVER recalculates a business
formula, NEVER stores a PDF-specific summary, and NEVER introduces a
second source of truth.

Each function here returns a template-ready context dict built entirely
from calls into the existing service layer.
"""

from apps.reports import services as report_services
from apps.stations.models import Station


def get_station_metadata() -> dict:
    """
    Station identity block required on every printed report (name,
    province, city). Pulled live from the Station row -- never hardcoded
    strings in the printing layer, so a station rename is reflected
    automatically.
    """
    station = Station.objects.first()
    return {
        "name": station.name if station else "",
        "province": station.province if station else "",
        "city": station.city if station else "",
    }


def build_nozzle_ledger_context(nozzle, start_date, end_date) -> dict:
    """
    Reuses reports.services.nozzle_performance_ledger() verbatim -- the
    printed table is the exact same per-day rows shown on the on-screen
    ledger. The on-screen ledger has no totals row, so the print version
    must not invent one either (that would be a second, print-only
    calculation living outside reports/services.py).
    """
    rows = report_services.nozzle_performance_ledger(nozzle, start_date, end_date)
    return {
        "station": get_station_metadata(),
        "nozzle": nozzle,
        "start_date": start_date,
        "end_date": end_date,
        "rows": rows,
    }


def build_nozzle_monthly_context(year: int, month: int) -> dict:
    """Reuses reports.services.nozzle_performance_monthly() per nozzle --
    identical rows/totals to the on-screen monthly report."""
    from apps.stations.models import Nozzle

    nozzles = Nozzle.objects.select_related("tank__product").order_by("number")
    rows = []
    for nozzle in nozzles:
        report = report_services.nozzle_performance_monthly(nozzle, year, month)
        if report:
            rows.append(report)

    return {
        "station": get_station_metadata(),
        "year": year,
        "month": month,
        "rows": rows,
    }


def build_petroleum_ledger_context(tank, start_date, end_date) -> dict:
    """Reuses reports.services.petroleum_inventory_operations_ledger()
    verbatim -- includes Daily Total 1/2, shortage/overage exactly as
    computed by inventory/services.py, no recalculation."""
    rows = report_services.petroleum_inventory_operations_ledger(tank, start_date, end_date)
    return {
        "station": get_station_metadata(),
        "tank": tank,
        "start_date": start_date,
        "end_date": end_date,
        "rows": rows,
    }


def build_petroleum_monthly_context(year: int, month: int) -> dict:
    """Reuses reports.services.petroleum_inventory_monthly() per tank --
    identical beginning/ending inventory and totals to the on-screen
    monthly tank statement."""
    from apps.stations.models import Tank

    tanks = Tank.objects.select_related("product").order_by("product__name")
    rows = []
    for tank in tanks:
        report = report_services.petroleum_inventory_monthly(tank, year, month)
        if report:
            rows.append(report)

    return {
        "station": get_station_metadata(),
        "year": year,
        "month": month,
        "rows": rows,
    }
