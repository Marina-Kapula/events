from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils._os import safe_join


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "home.html")


def media(request: HttpRequest, path: str) -> FileResponse:
    file = Path(safe_join(settings.MEDIA_ROOT, path))
    if not file.is_file():
        raise Http404
    return FileResponse(file.open("rb"))
