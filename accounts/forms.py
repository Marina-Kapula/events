from typing import Any, override

from django import forms
from django.contrib.auth.forms import AuthenticationForm, BaseUserCreationForm
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.html import format_html

from accounts.models import User
from config.photos import PhotoField

# Any image. The editor (templates/photo_editor.html) finds it by data-photo-input.
# No capture attribute: it would open only the camera, never the gallery.
PHOTO_INPUT = {"accept": "image/*", "data-photo-input": ""}


class EmailAuthenticationForm(AuthenticationForm):
    @override
    def clean(self) -> dict[str, object]:
        username = self.cleaned_data.get("username")
        if isinstance(username, str):
            self.cleaned_data["username"] = username.strip().lower()
        return super().clean()


class ProfileForm(forms.ModelForm[User]):
    # A plain file input: the page shows the current photo itself, not its file name.
    photo = PhotoField(widget=forms.FileInput(attrs=PHOTO_INPUT))

    class Meta:
        model = User
        fields = ("full_name", "photo", "nationality", "age", "gender")

    @override
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # The model allows them blank for staff; a student fills in every field.
        for name in ("nationality", "age", "gender"):
            self.fields[name].required = True


class RegistrationForm(BaseUserCreationForm[User]):
    # On a phone, the photo field offers the camera or the gallery.
    photo = PhotoField(widget=forms.FileInput(attrs=PHOTO_INPUT))

    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ("full_name", "email", "photo", "nationality", "age", "gender")

    @override
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # The model allows them blank for staff; a student fills in every field.
        for name in ("nationality", "age", "gender"):
            self.fields[name].required = True

    def clean_email(self) -> str:
        email: str = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError(
                format_html(
                    "This email is already registered. "
                    '<a href="{}">Log in</a>, <a href="{}">reset your password</a> '
                    'or <a href="{}">resend the verification email</a>, '
                    "or ask the AMFI staff.",
                    reverse("login"),
                    reverse("password_reset"),
                    reverse("resend_verification"),
                ),
                code="registered",
            )
        return email


class ResendVerificationForm(forms.Form):
    email = forms.EmailField()

    def clean_email(self) -> str:
        email: str = self.cleaned_data["email"]
        return email.lower()
