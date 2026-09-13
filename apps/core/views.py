"""
Main dashboard. Aggregates just enough context from other apps' services
to render the two-column tank/nozzle layout and license status -- no
accounting logic lives here, only orchestration.
"""

import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from apps.license import services as license_services
from apps.stations.models import Tank, Nozzle
from apps.workday import services as workday_services


@login_required
def dashboard(request):
    tanks = Tank.objects.select_related("product").order_by("product__name")
    nozzles = Nozzle.objects.select_related("tank__product").order_by("number")

    lic = license_services.get_current_license()
    show_warning = license_services.should_show_expiry_warning()
    days_remaining = license_services.days_until_expiry() if lic else None

    next_required_date = workday_services.get_next_required_date()
    incomplete_count = len(workday_services.get_incomplete_days())

    context = {
        "tanks": tanks,
        "nozzles": nozzles,
        "license_valid": lic is not None and lic.is_valid(),
        "license_warning": show_warning,
        "license_days_remaining": days_remaining,
        "next_required_date": next_required_date,
        "incomplete_days_count": incomplete_count,
    }
    return render(request, "core/dashboard.html", context)


@login_required
def set_global_date(request):
    """
    Target of the header's date-selector form (visible on every page via
    templates/base.html). Only ever updates the session's global working
    date -- never touches accounting data -- then returns to whatever
    page the operator submitted it from, so the effect is "the date
    changed" rather than "I got sent somewhere new."

    Chronology (can_enter_date) is intentionally NOT enforced here: this
    endpoint only records what the operator wants to look at next. Each
    app's own detail view already checks can_enter_date() and redirects
    to its choose_date screen with an explanation if the date turns out
    to be out of scope -- this stays consistent with how every other
    date entry point in the app already behaves, instead of duplicating
    that check a second time here.
    """
    if request.method == "POST":
        raw = request.POST.get("date", "")
        try:
            date = datetime.date.fromisoformat(raw)
        except ValueError:
            messages.error(request, "تاریخ واردشده معتبر نیست.")
        else:
            workday_services.set_global_date(request, date)

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse("core:dashboard")
    return HttpResponseRedirect(next_url)
