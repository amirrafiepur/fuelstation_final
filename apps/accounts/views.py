"""Single-operator authentication and first-run account activation."""

from django.contrib.auth import get_user_model, login as auth_login
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.shortcuts import redirect, render

from apps.core.models import AppConfig
from apps.license import services as license_services
from .forms import FirstOperatorSetupForm, OperatorLoginForm
from .models import Operator


User = get_user_model()


class OperatorLoginView(LoginView):
    template_name = "accounts/login.html"
    form_class = OperatorLoginForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["first_run"] = first_run_required()
        return context

    def get_initial(self):
        initial = super().get_initial()
        config = AppConfig.get_solo()
        if config.last_logged_in_username:
            initial["username"] = config.last_logged_in_username
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        config = AppConfig.get_solo()
        config.last_logged_in_username = form.get_user().get_username()
        config.save(update_fields=["last_logged_in_username"])
        return response


def first_run_required() -> bool:
    """A fresh installation is identified by having no Django User rows."""
    return not User.objects.exists()


def first_operator_setup(request):
    """
    Create the only operator on a fresh installation.

    The first successful account creation atomically creates the Operator
    profile and starts the 365-day license. Once any User exists, this route
    is permanently unavailable for that installation.
    """
    if not first_run_required():
        return redirect("accounts:login")

    if request.method == "POST":
        form = FirstOperatorSetupForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                Operator.objects.create(user=user)
                license_services.activate_license(duration_days=365)

            auth_login(request, user)
            config = AppConfig.get_solo()
            config.last_logged_in_username = user.get_username()
            config.save(update_fields=["last_logged_in_username"])
            return redirect("core:dashboard")
    else:
        form = FirstOperatorSetupForm()

    return render(request, "accounts/first_setup.html", {"form": form})
