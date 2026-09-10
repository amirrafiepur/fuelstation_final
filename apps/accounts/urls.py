from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import OperatorLoginView, first_operator_setup

app_name = "accounts"

urlpatterns = [
    path("login/", OperatorLoginView.as_view(), name="login"),
    path("first-setup/", first_operator_setup, name="first_setup"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
