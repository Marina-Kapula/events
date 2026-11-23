from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest
from django.utils._os import safe_join


def media(request: HttpRequest, path: str) -> FileResponse:
    file = Path(safe_join(settings.MEDIA_ROOT, path))
    if not file.is_file():
        raise Http404
    return FileResponse(file.open("rb"))
