from django.urls import path

from . import views

app_name = "printing"

urlpatterns = [
    path("nozzle-ledger/<int:nozzle_id>/", views.nozzle_ledger_print, name="nozzle_ledger_print"),
    path("nozzle-monthly/", views.nozzle_monthly_print, name="nozzle_monthly_print"),
    path("petroleum-ledger/<int:tank_id>/", views.petroleum_ledger_print, name="petroleum_ledger_print"),
    path("petroleum-monthly/", views.petroleum_monthly_print, name="petroleum_monthly_print"),
    path("purchases-ledger/", views.purchases_ledger_print, name="purchases_ledger_print"),
]
