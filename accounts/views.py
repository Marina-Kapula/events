import base64

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.forms import ProfileForm, RegistrationForm, ResendVerificationForm
from accounts.models import RegistrationWindow, User
from accounts.services import user_register, user_verify, verification_resend

# The session key of the photo kept after a registration form error.
KEPT_PHOTO = "register_photo"


@login_not_required
def register(request: HttpRequest, code: str) -> HttpResponse:
    window = get_object_or_404(RegistrationWindow, code=code)
    if not window.is_open(now=timezone.now()):
        return render(request, "accounts/register_closed.html")
    kept = request.session.get(KEPT_PHOTO)
    if request.method == "POST":
        files = request.FILES.copy()
        if "photo" not in files and kept:
            files["photo"] = SimpleUploadedFile(
                "photo.jpg", base64.b64decode(kept), content_type="image/jpeg"
            )
        form = RegistrationForm(request.POST, files)
        if form.is_valid():
            try:
                user_register(
                    user=form.save(commit=False), window=window, now=timezone.now()
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                request.session.pop(KEPT_PHOTO, None)
                return redirect("register_sent")
        # A file input comes back empty after an error: keep the checked photo so
        # the student doesn't pick it again for a typo in the password.
        photo = form.cleaned_data.get("photo")
        if isinstance(photo, File):
            photo.seek(0)
            kept = base64.b64encode(photo.read()).decode()
            request.session[KEPT_PHOTO] = kept
    else:
        form = RegistrationForm()
    if kept:
        form.fields["photo"].required = False  # no "required" attribute on the input
    context = {
        "form": form,
        "kept_photo": f"data:image/jpeg;base64,{kept}" if kept else "",
    }
    return render(request, "accounts/register.html", context)


@login_not_required
def register_sent(request: HttpRequest) -> HttpResponse:
    return render(request, "accounts/register_sent.html")


@login_not_required
def verify(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    try:
        user = user_verify(uidb64=uidb64, token=token)
    except ValidationError:
        return render(request, "accounts/verify_failed.html")
    login(request, user)
    messages.success(request, "Your email is verified. Welcome to AMFI Meetups!")
    return redirect("home")


@login_not_required
def resend_verification(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = ResendVerificationForm(request.POST)
        if form.is_valid():
            verification_resend(email=form.cleaned_data["email"])
            messages.info(
                request,
                "If that email is waiting for verification, a new link is on its way.",
            )
            return redirect("login")
    else:
        form = ResendVerificationForm()
    return render(request, "accounts/resend_verification.html", {"form": form})


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
