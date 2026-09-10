"""
Seal views: add/edit/delete/list. NozzleSeal has no chronology dependency
(it's event-based, not a daily working-day record), so these views don't
touch workday/services.py at all -- unlike sales/purchases/inventory.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import NozzleSealForm
from .models import NozzleSeal


@login_required
def seal_list(request):
    seals = NozzleSeal.objects.select_related("nozzle__tank__product").order_by("-date")
    return render(request, "seals/seal_list.html", {"seals": seals})


@login_required
def seal_create(request):
    if request.method == "POST":
        form = NozzleSealForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "پلمپ ثبت شد.")
            return redirect("seals:seal_list")
    else:
        form = NozzleSealForm()

    return render(request, "seals/seal_form.html", {"form": form, "editing": False})


@login_required
def seal_edit(request, pk):
    seal = get_object_or_404(NozzleSeal, pk=pk)

    if request.method == "POST":
        form = NozzleSealForm(request.POST, instance=seal)
        if form.is_valid():
            form.save()
            messages.success(request, "پلمپ بروزرسانی شد.")
            return redirect("seals:seal_list")
    else:
        form = NozzleSealForm(instance=seal)

    return render(request, "seals/seal_form.html", {"form": form, "editing": True, "seal": seal})


@login_required
def seal_delete(request, pk):
    """
    Deletion is destructive and requires strong confirmation, per the
    project-wide editing/deletion rule -- this view only deletes on POST,
    never on GET, and the template requires an explicit confirm click.
    """
    seal = get_object_or_404(NozzleSeal, pk=pk)

    if request.method == "POST":
        seal.delete()
        messages.success(request, "پلمپ حذف شد.")
        return redirect("seals:seal_list")

    return render(request, "seals/seal_confirm_delete.html", {"seal": seal})
