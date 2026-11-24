from typing import IO, Any, override
from urllib.parse import urljoin

from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

from files.models import StoredFile


@deconstructible
class DatabaseStorage(Storage):
    """Keeps uploaded files in the database instead of on the disk.

    Photos are shrunk to at most 1024 px before saving (config/photos.py), so each row
    stays small. They are served by config.views.media, as on the disk.
    """

    # _open and _save are Storage's hooks, missing from the type stubs.
    def _open(self, name: str, mode: str = "rb") -> File[Any]:
        stored = StoredFile.objects.filter(name=name).first()
        if stored is None:
            raise FileNotFoundError(name)
        file = ContentFile(bytes(stored.content), name=name)
        return file

    def _save(self, name: str, content: File[Any] | IO[Any]) -> str:
        if isinstance(content, File):
            content.seek(0)
        data = content.read()
        if isinstance(data, str):
            data = data.encode()
        StoredFile.objects.create(name=name, content=data, size=len(data))
        return name

    @override
    def exists(self, name: str) -> bool:
        return StoredFile.objects.filter(name=name).exists()

    @override
    def delete(self, name: str) -> None:
        StoredFile.objects.filter(name=name).delete()

    @override
    def size(self, name: str) -> int:
        stored = StoredFile.objects.filter(name=name).only("size").first()
        if stored is None:
            raise FileNotFoundError(name)
        return stored.size

    @override
    def url(self, name: str | None) -> str:
        return urljoin(settings.MEDIA_URL, name or "")
