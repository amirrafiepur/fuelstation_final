"""
Report aggregation services. All reports are read-only derived views over
existing source-of-truth data. No stored columns, no materialized summaries.

Each aggregation function returns raw data structures (lists of dicts) ready
for template rendering -- never stored in the database.
"""

from decimal import Decimal

from apps.sales.models import SalesInvoice, NozzleSale
from apps.purchases.models import PurchaseInvoice
from apps.inventory import services as inventory_services
from apps.inventory.models import TankInventory
from apps.stations.models import Nozzle, Tank
from apps.workday.models import DailyWorkingDay


def nozzle_performance_ledger(nozzle: Nozzle, start_date, end_date):
    """
    Nozzle Performance Ledger (F5): per nozzle, one row per working day
    from start_date through end_date. All derived from NozzleSale records
    -- previous_meter, test, and new_meter are the exact values entered
    on the sales form (apps/sales/models.py:NozzleSale); operation,
    mechanical_sales, sales_amount, and total_amount reuse that model's
    existing derived properties verbatim (no duplicate calculation here).

    daily_total ("جمع روزانه") = mechanical_sales + test. This is
    algebraically identical to operation (since mechanical_sales =
    operation - test by definition), which is expected, not a bug --
    both are shown as separate columns because they answer different
    questions (net sales-with-test-added-back vs. raw meter movement).

    cumulative_total ("جمع کل") is the running sum of daily_total across
    this row set, in date order: first row's cumulative_total equals its
    own daily_total, and each later row adds its daily_total to the
    previous row's cumulative_total. It resets to start fresh for each
    call (i.e. for each selected date range), and is computed purely
    from daily_total here -- no separate/duplicate accumulation logic.
    """
    rows = []
    cumulative_total = None
    for wd in DailyWorkingDay.objects.filter(
        date__gte=start_date, date__lte=end_date
    ).order_by("date"):
        sale = NozzleSale.objects.filter(
            nozzle=nozzle, sales_invoice__working_day=wd
        ).first()

        if sale:
            daily_total = sale.mechanical_sales + sale.test
            cumulative_total = (
                daily_total if cumulative_total is None else cumulative_total + daily_total
            )
            rows.append({
                "date": wd.date,
                "nozzle": nozzle,
                "previous_meter": sale.previous_meter,
                "new_meter": sale.new_meter,
                "test": sale.test,
                "operation": sale.operation,
                "mechanical_sales": sale.mechanical_sales,
                "daily_total": daily_total,
                "cumulative_total": cumulative_total,
                "sales_amount": sale.sales_amount,
                "sales_rate": sale.sales_rate,
                "total_amount": sale.total_amount,
            })
    return rows


def nozzle_performance_monthly(nozzle: Nozzle, year: int, month: int):
    """
    Monthly Nozzle Performance Report: one row per nozzle per month,
    showing totals plus beginning/end-of-month meter readings.

    `year`/`month` are the operator-facing JALALI year/month (e.g.
    1405/06) -- the report period the operator actually selects and
    reads is a Jalali month, not a Gregorian one. They are converted to
    a Gregorian [first_day, last_day] range via jalali_month_bounds()
    for the actual DB query; everything below this point continues to
    work in plain Gregorian dates exactly as before.

    Beginning-of-month meter = the previous month's ending meter for this
    nozzle, determined chronologically from actual NozzleSale records --
    never hardcoded. For the FIRST accounting month specifically, the
    beginning-of-month meter is instead this nozzle's meter reading on
    day 1 of that month (the first working day actually entered), since
    no prior month's records exist to carry forward from.

    End-of-month meter = the New Meter of the latest registered
    NozzleSale within the selected period.
    """
    from apps.core.jalali import jalali_month_bounds

    first_day, last_day = jalali_month_bounds(year, month)

    rows = NozzleSale.objects.filter(
        nozzle=nozzle,
        sales_invoice__working_day__date__gte=first_day,
        sales_invoice__working_day__date__lte=last_day,
    ).select_related("sales_invoice__working_day").order_by(
        "sales_invoice__working_day__date"
    )

    if not rows.exists():
        return None

    total_operation = sum(r.operation for r in rows) or Decimal("0")
    total_mechanical_sales = sum(r.mechanical_sales for r in rows) or Decimal("0")
    total_sales_amount = sum(r.sales_amount for r in rows) or Decimal("0")
    total_amount = sum(r.total_amount for r in rows) or Decimal("0")

    # End-of-month meter: New Meter of the latest working day in this
    # period that has a registered sale for this nozzle.
    end_of_month_meter = rows.last().new_meter

    # Beginning-of-month meter: determined chronologically, never
    # hardcoded. Normally this is the previous month's ending meter for
    # this nozzle -- found by looking at the latest NozzleSale strictly
    # before this period's first day. For the FIRST accounting month (no
    # such prior record exists for this nozzle), it falls back to this
    # nozzle's own first entry within the period -- its meter reading on
    # day 1 of that month, exactly as recorded by the operator.
    prior_sale = (
        NozzleSale.objects.filter(
            nozzle=nozzle,
            sales_invoice__working_day__date__lt=first_day,
        )
        .order_by("-sales_invoice__working_day__date")
        .first()
    )
    if prior_sale is not None:
        beginning_of_month_meter = prior_sale.new_meter
    else:
        beginning_of_month_meter = rows.first().previous_meter

    return {
        "nozzle": nozzle,
        "year": year,
        "month": month,
        "beginning_of_month_meter": beginning_of_month_meter,
        "end_of_month_meter": end_of_month_meter,
        "total_operation": total_operation,
        "total_mechanical_sales": total_mechanical_sales,
        "total_sales_amount": total_sales_amount,
        "total_amount": total_amount,
    }


def petroleum_inventory_operations_ledger(tank: Tank, start_date, end_date):
    """
    Petroleum Inventory & Operations Ledger (F6): per tank, one row per
    working day from start_date through end_date, showing Daily Purchase,
    Test Return, Daily Sales, Total Inventory, Theoretical Inventory,
    Shortage, Overage, and the two daily-total columns:

        Daily Total 1 = Received/Purchased + Test + Overage
        Daily Total 2 = Sales + Test Return + Shortage
                        + End-of-period Actual Inventory

    All values are pulled directly from the existing purchase/sales/
    inventory source data and TankInventory-derived shortage/overage --
    no second inventory calculation is performed here.
    """
    from apps.sales import services as sales_services
    from apps.purchases import services as purchase_services

    rows = []
    for wd in DailyWorkingDay.objects.filter(
        date__gte=start_date, date__lte=end_date
    ).order_by("date"):
        daily_purchase = purchase_services.get_daily_purchase_total(tank, wd)
        test_return = inventory_services.get_test_return(tank, wd)
        daily_sales = sales_services.get_daily_sales(tank, wd)

        try:
            total_inventory, theoretical_inventory, shortage, overage = (
                inventory_services.compute_tank_inventory(tank, wd)
            )
        except ValueError:
            # TankInventory missing -- skip this day
            total_inventory = theoretical_inventory = shortage = overage = None

        daily_total_1 = None
        daily_total_2 = None
        if overage is not None:
            actual_inventory = TankInventory.objects.filter(
                tank=tank, working_day=wd
            ).values_list("actual_inventory", flat=True).first()
            daily_total_1 = daily_purchase + test_return + overage
            daily_total_2 = daily_sales + test_return + shortage + actual_inventory

        rows.append({
            "date": wd.date,
            "tank": tank,
            "daily_purchase": daily_purchase,
            "test_return": test_return,
            "daily_sales": daily_sales,
            "total_inventory": total_inventory,
            "theoretical_inventory": theoretical_inventory,
            "shortage": shortage,
            "overage": overage,
            "daily_total_1": daily_total_1,
            "daily_total_2": daily_total_2,
        })
    return rows


def petroleum_inventory_monthly(tank: Tank, year: int, month: int):
    """
    Monthly Tank Statement: one row per tank per month.

    `year`/`month` are the operator-facing JALALI year/month, converted
    to a Gregorian [first_day, last_day] range via jalali_month_bounds()
    -- see nozzle_performance_monthly()'s docstring above for why.

    Beginning Inventory = previous month's ending Actual Inventory for
    this tank, determined chronologically from the latest TankInventory
    row strictly before this period. For the FIRST accounting month (no
    such prior row exists), Beginning Inventory = OpeningInventory for
    day 1 of that month (0 by default, or the operator's supplied value).

    Ending Inventory = the Actual Inventory of the last registered
    TankInventory row within the selected period -- never manually
    entered or computed at the monthly level.
    """
    from apps.core.jalali import jalali_month_bounds
    from apps.sales import services as sales_services
    from apps.purchases import services as purchase_services
    from apps.workday import services as workday_services

    first_day, last_day = jalali_month_bounds(year, month)

    working_days_in_period = DailyWorkingDay.objects.filter(
        date__gte=first_day, date__lte=last_day
    )

    if not working_days_in_period.exists():
        return None

    received_quantity_total = Decimal("0")
    test_return_total = Decimal("0")
    daily_sales_total = Decimal("0")
    shortage_total = Decimal("0")
    overage_total = Decimal("0")

    for wd in working_days_in_period:
        received_quantity_total += purchase_services.get_daily_purchase_total(tank, wd)
        test_return_total += inventory_services.get_test_return(tank, wd)
        daily_sales_total += sales_services.get_daily_sales(tank, wd)
        try:
            _, _, shortage, overage = inventory_services.compute_tank_inventory(tank, wd)
            shortage_total += shortage
            overage_total += overage
        except ValueError:
            pass

    # Beginning Inventory: previous month's ending Actual Inventory,
    # found chronologically -- the latest TankInventory row for this
    # tank strictly before this period's first day.
    prior_inventory_row = (
        TankInventory.objects.filter(tank=tank, working_day__date__lt=first_day)
        .order_by("-working_day__date")
        .first()
    )
    if prior_inventory_row is not None:
        beginning_inventory = prior_inventory_row.actual_inventory
    else:
        accounting_start = workday_services.get_accounting_start_date()
        opening = None
        if accounting_start is not None:
            from apps.inventory.models import OpeningInventory
            opening = OpeningInventory.objects.filter(
                tank=tank, effective_month=accounting_start
            ).first()
        beginning_inventory = opening.opening_quantity if opening else Decimal("0")

    # Ending Inventory: Actual Inventory of the last registered
    # TankInventory row within this period -- auto-derived, never
    # manually entered at the monthly-report level.
    last_inventory_row = (
        TankInventory.objects.filter(
            tank=tank, working_day__date__gte=first_day, working_day__date__lte=last_day
        )
        .order_by("-working_day__date")
        .first()
    )
    ending_inventory = last_inventory_row.actual_inventory if last_inventory_row else None

    return {
        "tank": tank,
        "year": year,
        "month": month,
        "beginning_inventory": beginning_inventory,
        "ending_inventory": ending_inventory,
        "total_purchase": received_quantity_total,
        "total_test_return": test_return_total,
        "total_sales": daily_sales_total,
        "total_shortage": shortage_total,
        "total_overage": overage_total,
    }
