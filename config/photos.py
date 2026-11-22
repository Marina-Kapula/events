from io import BytesIO
from typing import Any, override

from django import forms
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.base import ContentFile
from PIL import Image, ImageOps

MAX_BYTES = 10 * 1024 * 1024
MAX_SIDE = 1024


class PhotoField(forms.ImageField):
    @override
    def to_python(self, data: File[Any] | None) -> File[Any] | None:
        if data and data.size > MAX_BYTES:
            raise ValidationError("The photo is bigger than 10 MB.", code="too_big")
        photo = super().to_python(data)
        if photo is None:
            return None
        with Image.open(photo) as image:
            upright = ImageOps.exif_transpose(image)
            upright.thumbnail((MAX_SIDE, MAX_SIDE))
            output = BytesIO()
            upright.convert("RGB").save(output, format="JPEG", quality=85)
        return ContentFile(output.getvalue(), name="photo.jpg")
