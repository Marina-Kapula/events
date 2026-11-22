from io import BytesIO

from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.datastructures import MultiValueDict
from PIL import ExifTags, Image

from config.photos import MAX_BYTES, PhotoField


class PhotoForm(forms.Form):
    photo = PhotoField()


def jpeg(width: int, height: int, exif: Image.Exif | None = None) -> bytes:
    output = BytesIO()
    image = Image.new("RGB", (width, height), "orange")
    image.save(output, format="JPEG", exif=exif or Image.Exif())
    return output.getvalue()


def upload(content: bytes) -> PhotoForm:
    photo = SimpleUploadedFile("IMG_0042.jpg", content)
    form = PhotoForm(files=MultiValueDict({"photo": [photo]}))
    form.is_valid()
    return form


def cleaned_image(form: PhotoForm) -> Image.Image:
    return Image.open(form.cleaned_data["photo"])


def test_a_big_photo_is_shrunk_to_1024_px() -> None:
    image = cleaned_image(upload(jpeg(4000, 3000)))

    assert image.size == (1024, 768)
    assert image.format == "JPEG"


def test_exif_and_the_gps_position_are_removed() -> None:
    exif = Image.Exif()
    exif[ExifTags.Base.Make] = "Phone Maker"
    exif[ExifTags.IFD.GPSInfo] = {
        ExifTags.GPS.GPSLatitudeRef: "N",
        ExifTags.GPS.GPSLatitude: (42.0, 1.0, 51.0),
    }
    original = jpeg(800, 600, exif)
    assert Image.open(BytesIO(original)).getexif().get_ifd(ExifTags.IFD.GPSInfo)

    image = cleaned_image(upload(original))

    assert not image.getexif()


def test_a_sideways_phone_photo_is_turned_upright() -> None:
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = 6

    image = cleaned_image(upload(jpeg(400, 300, exif)))

    assert image.size == (300, 400)


def test_a_photo_over_10_mb_is_refused() -> None:
    form = upload(b"x" * (MAX_BYTES + 1))

    assert form.errors["photo"] == ["The photo is bigger than 10 MB."]


def test_a_file_that_is_not_an_image_is_refused() -> None:
    form = upload(b"%PDF-1.7 not a photo")

    assert form.errors["photo"] == [
        "Upload a valid image. The file you uploaded was either not an image or a "
        "corrupted image."
    ]
