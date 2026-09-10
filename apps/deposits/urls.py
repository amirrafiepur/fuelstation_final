from django.urls import path

from . import views

app_name = "deposits"

urlpatterns = [
    path("", views.deposit_list, name="deposit_list"),
    path("new/", views.deposit_create, name="deposit_create"),
    path("<int:pk>/edit/", views.deposit_edit, name="deposit_edit"),
    path("<int:pk>/delete/", views.deposit_delete, name="deposit_delete"),
]
