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


def build_all_nozzles_performance_context(start_date, end_date) -> dict:
    """
    Reuses reports.services.all_nozzles_performance_summary() verbatim --
    identical per-day station-wide totals to the on-screen کارکرد تمام
    نازل‌ها report. Products are ordered by name, same as the on-screen
    view, so the printed per-product columns line up with whatever the
    on-screen table shows -- never a hardcoded "Regular"/"Super" name
    anywhere in this layer either. Each row's per-product totals are
    attached as a same-order "product_totals" list, exactly mirroring
    reports/views.py:all_nozzles_performance()'s own context-shaping, so
    the print template needs no dict-by-variable-key lookup either.
    """
    from decimal import Decimal

    from apps.stations.models import Product

    rows = report_services.all_nozzles_performance_summary(start_date, end_date)
    products = Product.objects.order_by("name")
    for row in rows:
        row["product_totals"] = [
            row["by_product"].get(product.id, Decimal("0")) for product in products
        ]

    return {
        "station": get_station_metadata(),
        "products": products,
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


def build_purchases_ledger_context(start_date, end_date) -> dict:
    """
    Reuses purchases.services.get_purchase_invoices_in_range() verbatim,
    once per tank -- identical PurchaseInvoice rows to the on-screen
    Purchases date-range list, split the same way into one entry per
    product/tank so the print template can render Regular and Super as
    two separate tables in the same PDF.
    """
    from apps.purchases import services as purchase_services
    from apps.stations.models import Tank

    tanks = Tank.objects.select_related("product").order_by("product__name")
    tank_rows = [
        {
            "tank": tank,
            "invoices": purchase_services.get_purchase_invoices_in_range(tank, start_date, end_date),
        }
        for tank in tanks
    ]

    return {
        "station": get_station_metadata(),
        "tank_rows": tank_rows,
        "start_date": start_date,
        "end_date": end_date,
    }
