import mimetypes
from pathlib import Path
from typing import override

from django.conf import settings
from django.contrib.auth import views as auth_views
from django.core.files.storage import FileSystemStorage, default_storage
from django.http import FileResponse, Http404, HttpRequest
from django.urls import reverse
from django.utils._os import safe_join

from accounts.models import User


def media(request: HttpRequest, path: str) -> FileResponse:
    storage = default_storage
    if isinstance(storage, FileSystemStorage):
        file = Path(safe_join(settings.MEDIA_ROOT, path))
        if not file.is_file():
            raise Http404
        return FileResponse(file.open("rb"))
    # Photos kept in the database (files.storage.DatabaseStorage), as on Render.
    try:
        stored = storage.open(path)
    except FileNotFoundError:
        raise Http404 from None
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return FileResponse(stored, content_type=content_type)


class LoginView(auth_views.LoginView):
    """Staff land in the admin after logging in, students on the event list."""

    @override
    def get_default_redirect_url(self) -> str:
        user = self.request.user
        if isinstance(user, User) and user.is_staff:
            return reverse("admin:index")
        return super().get_default_redirect_url()
