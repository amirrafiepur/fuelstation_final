"""
workday/services.py -- chronology enforcement.

Key rule (see architecture doc, "Accounting month start vs. license
activation"): the required accounting sequence for the FIRST calendar
month starts on day 1 of the calendar month containing the license
activation date, NOT on the activation date itself. From the second
accounting month onward, this distinction no longer matters -- every
calendar day is simply required in order.
"""

import calendar
import datetime

from django.utils import timezone

from .models import DailyWorkingDay
from apps.license import services as license_services


def get_accounting_start_date() -> datetime.date | None:
    """
    Day 1 of the calendar month containing the license's start_date (the
    first activation date). Returns None if no license has been activated
    yet (first-run setup not yet completed).
    """
    lic = license_services.get_current_license()
    if lic is None:
        return None
    return lic.start_date.replace(day=1)


def get_today() -> datetime.date:
    """The Windows system date, as seen by this machine."""
    return timezone.localdate()


def can_enter_date(date: datetime.date) -> tuple[bool, str]:
    """
    Returns (allowed, reason). A date is only enterable if:
      - it is not in the future, and
      - it is not before the accounting start date.
    Chronological ordering (earlier missing days first) is enforced by
    get_incomplete_days()/the calling view, not here -- this function only
    answers "is this date even in scope."
    """
    today = get_today()
    if date > today:
        return False, "تاریخ آینده قابل ثبت نیست."

    start = get_accounting_start_date()
    if start is not None and date < start:
        return False, "این تاریخ خارج از محدوده تاریخچه حسابداری برنامه است."
    return True, ""


def get_incomplete_days(up_to: datetime.date | None = None) -> list[datetime.date]:
    """
    Every calendar date from the accounting start date through `up_to`
    (default: today) that does NOT have a DailyWorkingDay row with status
    'complete', in chronological order. Used to drive the "you must
    complete these days first" flow.
    """
    start = get_accounting_start_date()
    if start is None:
        return []

    up_to = up_to or get_today()
    if up_to < start:
        return []

    complete_dates = set(
        DailyWorkingDay.objects.filter(
            status=DailyWorkingDay.COMPLETE, date__gte=start, date__lte=up_to
        ).values_list("date", flat=True)
    )

    missing = []
    current = start
    one_day = datetime.timedelta(days=1)
    while current <= up_to:
        if current not in complete_dates:
            missing.append(current)
        current += one_day
    return missing


def get_next_required_date() -> datetime.date | None:
    """The earliest incomplete day the user must work on next, or None if
    everything through today is already complete."""
    missing = get_incomplete_days()
    return missing[0] if missing else None


def close_day(date: datetime.date) -> DailyWorkingDay:
    """
    Marks a DailyWorkingDay complete. Callers (sales/purchases/inventory
    views) must have already verified all completion requirements
    (required nozzle records, SalesInvoice, TankInventory for every
    required tank) before calling this -- this function only flips the
    status.
    """
    day, _ = DailyWorkingDay.objects.get_or_create(date=date)
    day.status = DailyWorkingDay.COMPLETE
    day.save(update_fields=["status"])
    return day


def reopen_day_on_delete(date: datetime.date) -> None:
    """
    Called after a destructive delete affecting `date`'s records. Reverts
    the day to incomplete so chronology enforcement correctly requires it
    to be re-entered before any later day can be finalized.
    """
    DailyWorkingDay.objects.filter(date=date).update(
        status=DailyWorkingDay.INCOMPLETE
    )


def last_day_of_month(any_date: datetime.date) -> datetime.date:
    """Helper used by report/decade logic elsewhere (e.g. deposits'
    3rd-decade boundary) to correctly handle 28/29/30/31-day months."""
    last_day_num = calendar.monthrange(any_date.year, any_date.month)[1]
    return any_date.replace(day=last_day_num)
