from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.forms import ProfileForm
from accounts.models import RegistrationWindow, User


@login_not_required
def register(request: HttpRequest, code: str) -> HttpResponse:
    window = get_object_or_404(RegistrationWindow, code=code)
    if not window.is_open(now=timezone.now()):
        return render(request, "accounts/register_closed.html")
    return render(request, "accounts/register.html", {"window": window})


def student_detail(request: HttpRequest, pk: int) -> HttpResponse:
    student = get_object_or_404(
        User, pk=pk, is_active=True, is_staff=False, deleted_at=None
    )
    return render(request, "accounts/student_detail.html", {"student": student})


def profile_edit(request: HttpRequest) -> HttpResponse:
    user = request.user
    if not isinstance(user, User) or user.is_staff:
        raise Http404
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile is saved.")
            return redirect("student_detail", pk=user.pk)
    else:
        form = ProfileForm(instance=user)
    return render(request, "accounts/profile_edit.html", {"form": form})
