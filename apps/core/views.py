"""
Main dashboard. Aggregates just enough context from other apps' services
to render the two-column tank/nozzle layout and license status -- no
accounting logic lives here, only orchestration.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

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
