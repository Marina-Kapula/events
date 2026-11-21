from typing import override

from django.contrib.auth.forms import AuthenticationForm


class EmailAuthenticationForm(AuthenticationForm):
    @override
    def clean(self) -> dict[str, object]:
        username = self.cleaned_data.get("username")
        if isinstance(username, str):
            self.cleaned_data["username"] = username.strip().lower()
        return super().clean()
