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
    Day 1 of the JALALI month containing the license's start_date (the
    first activation date). Returns None if no license has been activated
    yet (first-run setup not yet completed).

    This must be the 1st of the operator's Jalali month, not the 1st of
    the Gregorian calendar month: the accounting backfill sequence, the
    dashboard's "N incomplete days, continue from <date>" warning, and
    the global Date Control all ultimately start counting from this
    value and display it through the Jalali filter. A Gregorian
    replace(day=1) here produces a Gregorian date that, once displayed
    in Jalali, looks like a nonsensical mid-month date (e.g. "1405/06/10"
    instead of the real month start "1405/06/01") -- see
    apps/core/jalali.py's jalali_month_start() docstring for the full
    explanation of this bug class.
    """
    lic = license_services.get_current_license()
    if lic is None:
        return None
    from apps.core.jalali import jalali_month_start
    return jalali_month_start(lic.start_date)


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


# ---------------------------------------------------------------------
# Global date context
#
# The header date selector lets the operator pick one working date that
# stays in effect across sales/purchases/inventory as they navigate --
# without it, each app's own choose_working_date defaults back to
# get_next_required_date() every time, so switching sections silently
# resets whatever date the operator was just looking at.
#
# Stored in the session (not the DB): this is a per-session UI
# convenience, not accounting data, and the app is single-operator with
# one session per run -- there is nothing to share across users/machines
# here. Session storage also means it plays no part in chronology
# enforcement itself; can_enter_date() and get_incomplete_days() are
# completely unaffected by it.
# ---------------------------------------------------------------------

GLOBAL_DATE_SESSION_KEY = "global_working_date"


def get_global_date(request) -> datetime.date:
    """
    The operator's current global working date. Falls back to the next
    chronologically-required date, or today if every required day is
    already complete, whenever nothing has been explicitly selected yet
    this session.
    """
    raw = request.session.get(GLOBAL_DATE_SESSION_KEY)
    if raw:
        try:
            return datetime.date.fromisoformat(raw)
        except ValueError:
            pass  # fall through to the default below

    return get_next_required_date() or get_today()


def set_global_date(request, date: datetime.date) -> None:
    """Persist the operator's chosen date as the session-wide default for
    sales/purchases/inventory until they pick a different one."""
    request.session[GLOBAL_DATE_SESSION_KEY] = date.isoformat()
