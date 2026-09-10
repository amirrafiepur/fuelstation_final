from django.urls import path

from . import views

app_name = "purchases"

urlpatterns = [
    path("", views.choose_working_date, name="choose_date"),
    path("<str:date>/", views.invoice_list_for_day, name="invoice_list_for_day"),
    path("<str:date>/tank/<int:tank_id>/new/", views.purchase_entry, name="purchase_entry"),
    path("<str:date>/invoice/<int:pk>/edit/", views.purchase_edit, name="purchase_edit"),
]
