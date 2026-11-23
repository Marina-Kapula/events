from typing import Any, override

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from accounts.models import User
from config.photos import PhotoField


class EmailAuthenticationForm(AuthenticationForm):
    @override
    def clean(self) -> dict[str, object]:
        username = self.cleaned_data.get("username")
        if isinstance(username, str):
            self.cleaned_data["username"] = username.strip().lower()
        return super().clean()


class ProfileForm(forms.ModelForm[User]):
    photo = PhotoField()

    class Meta:
        model = User
        fields = ("full_name", "photo", "nationality", "age", "gender")

    @override
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # The model allows them blank for staff; a student fills in every field.
        for name in ("nationality", "age", "gender"):
            self.fields[name].required = True
