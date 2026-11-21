# Upload photos, and show them to logged-in users only

Status: todo · Opened: 2026-11-21 · Milestone: M1 · Depends on: 002

## Why

Every student has a photo of their face, and every event has a photo (SPEC.md §2 #10, §5). Two
problems come with them:

- **Privacy.** The usual Django setup lets the web server hand out every uploaded file to anyone
  who has the URL. These are students' faces (personal data under the GDPR), so photos must stay
  behind the login like everything else (SPEC.md §2 #13, #14).
- **What a phone photo carries.** It is 3–8 MB, often 4000 px wide, and it holds **EXIF** data:
  the phone model, the time, and often the **GPS position** where it was taken. A selfie taken
  at home tells everyone where the student lives.

So this issue builds two small pieces that every later upload uses: a form field that checks,
shrinks and cleans each photo, and a view that serves photos to logged-in users only.

## What you'll build

- The media settings: uploads are stored in `var/media/` (git-ignored, and on the server inside
  the storage mount, so they survive deploys).
- `config/photos.py` with `PhotoField`, a form field that refuses files over 10 MB and anything
  that isn't an image, turns sideways phone photos upright, shrinks them to at most 1024 px, and
  re-saves them as JPEG without EXIF.
- `/media/<path>`: a view that sends a photo to a logged-in user, and nothing outside
  `var/media/` to anybody.
- Tests for both.

Not in this issue: the forms that use the field. Registration (008), the profile page (009), the
event form (010) and the admin use it, each in its own issue (step 6 shows how).

## Before you start

Read:
- SPEC.md §2 #13, #14; §6.8 (Photos); §9 (Media).
- AGENTS.md: Typing, and Views and templates.
- `docs/deployment/deploy-to-dokku.md`, part 8: the storage mount and the 10 MB upload limit.
- `docs/learn/hypermedia-and-forms.md` ("Files") and `docs/learn/how-a-django-request-works.md`
  (the status codes 400, 404 and 413), if forms or status codes are new to you.
- [Django: File uploads](https://docs.djangoproject.com/en/6.1/topics/http/file-uploads/) (how
  `request.FILES` and forms work together) and
  [Django security: user-uploaded content](https://docs.djangoproject.com/en/6.1/topics/security/#user-uploaded-content).

Words you'll meet:
- **Media files**: files users upload, as opposed to static files (CSS, JS) that you write.
  Django stores them under `MEDIA_ROOT` and links them under `MEDIA_URL`.
- **EXIF**: data a camera writes inside a JPEG: model, date, orientation, often the GPS position.
- **Pillow**: the Python imaging library behind Django's `ImageField` (installed in 002).
- **Path traversal**: asking for `/media/../../.env` to read a file outside the media folder.
  `safe_join` refuses such paths.
- **`FileResponse`**: a response that sends a file in chunks, without reading it all into memory.

## Steps

### 1. Media settings

In `config/settings.py`, next to the static files settings:

```python
# Uploaded photos: inside var/, the storage mount on Dokku, so they survive deploys.
# Served only to logged-in users, by config.views.media (SPEC.md §6.8).
MEDIA_ROOT: Path = BASE_DIR / "var" / "media"
MEDIA_URL: str = "media/"
```

Without `MEDIA_ROOT`, Django saves uploads in the folder you started the server from: on Dokku
that is inside the container, which is thrown away on the next deploy. `var/` is already in
`.gitignore`: photos never go into git.

`MEDIA_URL` is relative, like `STATIC_URL`: Django puts a `/` in front, so `{{ user.photo.url }}`
gives `/media/photos/users/photo.jpg`.

- [ ] `MEDIA_ROOT` and `MEDIA_URL` as above.

### 2. The photo field

`config/photos.py`:

```python
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
    """An image upload, shrunk and re-saved as a JPEG without its EXIF data."""

    @override
    def to_python(self, data: File[Any] | None) -> File[Any] | None:
        if data and data.size > MAX_BYTES:
            raise ValidationError("The photo is bigger than 10 MB.", code="too_big")
        # Django's ImageField checks that Pillow can open the file.
        photo = super().to_python(data)
        if photo is None:
            return None
        with Image.open(photo) as image:
            # Phones store "turn me" in EXIF: apply it before EXIF is dropped.
            upright = ImageOps.exif_transpose(image)
            upright.thumbnail((MAX_SIDE, MAX_SIDE))
            output = BytesIO()
            # Saving without exif= drops the EXIF data, GPS position included.
            upright.convert("RGB").save(output, format="JPEG", quality=85)
        # A fixed name: the original one may say who or where. Django's storage adds
        # a random suffix when photo.jpg already exists.
        return ContentFile(output.getvalue(), name="photo.jpg")
```

Why each piece is there:

- **`to_python`** is the step of a form field that turns the raw input into a Python value
  ([how form validation works](https://docs.djangoproject.com/en/6.1/ref/forms/validation/)).
  Whatever it returns ends up in `form.cleaned_data["photo"]`, and `form.save()` stores that
  file. So the original photo is never saved.
- **The size check comes first**, before Pillow reads anything.
- **`super().to_python(data)`** is Django's `ImageField`: it asks Pillow to open the file and
  raises "Upload a valid image" if it can't. A PDF renamed to `.jpg` stops here.
- **`exif_transpose`**: a phone saves a portrait photo lying on its side, plus an EXIF note
  "rotate me". Browsers follow the note. Once EXIF is gone the note is gone too, so the pixels
  must be turned first, or every portrait photo shows sideways.
- **`thumbnail((1024, 1024))`** shrinks so the long side is at most 1024 px, keeps the
  proportions, and never enlarges a small photo.
- **`convert("RGB")`**: JPEG has no transparency, so a PNG with a transparent background is
  flattened first (Pillow refuses to save RGBA as JPEG).
- **Re-saving as a new JPEG** drops EXIF, and it also means the server only ever stores files it
  made itself: a "photo" with something else hidden inside doesn't survive (Django's security
  docs explain why that matters).

- **`File[Any] | None`** in the signature is copied from django-stubs, so pyrefly accepts the
  override.

- [ ] `config/photos.py` as above.

### 3. Test the field

A test form with one `PhotoField`, and photos made with Pillow in memory: no image files in the
repo.

`tests/config/test_photos.py`:

```python
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
    exif[ExifTags.Base.Orientation] = 6  # "rotate 90° clockwise to display"

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
```

- The GPS test first checks that the original *has* a GPS position, so it can't pass by
  accident.
- `files=MultiValueDict(...)` is what a real request's `request.FILES` is; django-stubs wants that
  type.

- [ ] The five tests pass. Try removing the `exif_transpose` line: the sideways test must fail.

### 4. Serve photos to logged-in users

`config/views.py`, with the new view below `home`:

```python
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils._os import safe_join


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "home.html")


def media(request: HttpRequest, path: str) -> FileResponse:
    # safe_join refuses a path that leaves MEDIA_ROOT, such as ../../.env.
    file = Path(safe_join(settings.MEDIA_ROOT, path))
    if not file.is_file():
        raise Http404
    return FileResponse(file.open("rb"))
```

and the URL to `config/urls.py`:

```python
urlpatterns: list[URLPattern | URLResolver] = [
    # ... the URLs that are already there ...
    path("media/<path:path>", views.media, name="media"),
]
```

How it works:
- **No login code here.** `LoginRequiredMiddleware` (SPEC.md §9) already sends anonymous visitors
  to the login page, for every view that isn't marked `@login_not_required`.
- **`<path:path>`** matches the rest of the URL, slashes included (`photos/users/photo.jpg`).
- **`safe_join`** joins `MEDIA_ROOT` and the path, and raises `SuspiciousFileOperation` if the
  result is outside `MEDIA_ROOT`. Django turns that exception into a **400 Bad Request** and logs a
  warning in the `django.security` logger: no `try/except` needed. The module name starts with
  `_` (Django-internal), but it is the same function Django's own `django.views.static.serve`
  uses, and it has been there for many versions.
- **`is_file()`**: a missing file, or a folder, is a 404.
- **`FileResponse`** guesses the `Content-Type` from the file name and closes the file when it is
  done.

Why not the usual ways? Django's docs show `static(settings.MEDIA_URL, ...)` in `urls.py`: it only
works with `DEBUG` on, and serves every file to anyone. nginx serving `/media/` would be fast but
public too (SPEC.md §2 #13, "Not chosen"). Our app is small; Django sending a 100 KB JPEG is fine.

- [ ] The view and the URL exist.

### 5. Test the view, and keep test uploads out of `var/media/`

Every later test that saves a form with a photo would write a real file into your `var/media/`.
Send them to a temporary folder instead, for every test at once, with an autouse fixture in
`tests/conftest.py`, next to the static files one:

```python
@pytest.fixture(autouse=True)
def _media_root_in_tmp_path(tmp_path: Path) -> Iterator[None]:
    # Photos saved by tests go to a temporary folder, not to var/media/.
    with override_settings(MEDIA_ROOT=tmp_path / "media"):
        yield
```

(`from pathlib import Path` at the top.) Then `tests/config/test_media.py`:

```python
from collections.abc import Callable
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client

from accounts.models import User

pytestmark = pytest.mark.django_db

PHOTO = b"\xff\xd8 pretend this is a JPEG"


@pytest.fixture(autouse=True)
def _files() -> None:
    # One photo in MEDIA_ROOT (a temporary folder, tests/conftest.py), and a secret
    # file next to MEDIA_ROOT that must never be served.
    media_root = Path(settings.MEDIA_ROOT)
    (media_root / "photos" / "users").mkdir(parents=True)
    (media_root / "photos" / "users" / "photo.jpg").write_bytes(PHOTO)
    (media_root.parent / ".env").write_text("DJANGO_SECRET_KEY=not-for-you")


def test_anonymous_users_are_sent_to_login(client: Client) -> None:
    response = client.get("/media/photos/users/photo.jpg")

    assert response.status_code == 302
    assert response["Location"].startswith("/accounts/login/?next=/media/")


def test_logged_in_users_get_the_photo(
    client: Client, make_student: Callable[..., User]
) -> None:
    client.force_login(make_student())

    response = client.get("/media/photos/users/photo.jpg")

    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"
    assert response.getvalue() == PHOTO


def test_a_missing_photo_is_404(
    client: Client, make_student: Callable[..., User]
) -> None:
    client.force_login(make_student())

    assert client.get("/media/photos/users/nobody.jpg").status_code == 404
    assert client.get("/media/photos/users/").status_code == 404


@pytest.mark.parametrize("path", ["/media/../.env", "/media/photos/../../.env"])
def test_paths_outside_media_root_are_refused(
    client: Client, make_student: Callable[..., User], path: str
) -> None:
    client.force_login(make_student())

    response = client.get(path)

    # Django answers a SuspiciousFileOperation with 400 and logs it.
    assert response.status_code == 400
    assert b"not-for-you" not in response.content
```

Then try it by hand: put any `.jpg` in `var/media/photos/` and open
`http://127.0.0.1:8000/media/photos/<name>.jpg`. Logged in, you see it; in a private window, you
land on the login page.

- [ ] The tests pass, and `scripts/check.sh` passes.
- [ ] By hand: the photo shows when logged in, and the login page shows when not.

### 6. How the later issues use it

Nothing to do here; this is for 008, 009, 010 and the admin. A `ModelForm` declares the field
itself, so Django uses ours instead of the plain `ImageField`:

```python
class ProfileForm(forms.ModelForm[User]):
    photo = PhotoField()

    class Meta:
        model = User
        fields = ("full_name", "photo", "nationality", "age", "gender")
```

The view passes the files too, `ProfileForm(request.POST, request.FILES, instance=...)`, and the
`<form>` tag needs `enctype="multipart/form-data"`. A template shows a photo with
`<img src="{{ student.photo.url }}" alt="{{ student.full_name }}">`.

In the admin, one line makes every image field of a `ModelAdmin` a `PhotoField` (needs
`from typing import ClassVar` and `from django.db import models`):

```python
formfield_overrides: ClassVar = {models.ImageField: {"form_class": PhotoField}}
```

## Done when

- [ ] `MEDIA_ROOT` is `var/media/` and `MEDIA_URL` is `media/`.
- [ ] `PhotoField` refuses files over 10 MB and non-images, turns photos upright, shrinks them to
      at most 1024 px, and drops EXIF (tests in `tests/config/test_photos.py`).
- [ ] `/media/<path>` sends a photo to logged-in users only, 404s for missing files, and refuses
      paths outside `MEDIA_ROOT` (tests in `tests/config/test_media.py`).
- [ ] Tests never write into `var/media/`.
- [ ] `scripts/check.sh` passes.
- [ ] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 006-photos
```

Suggested commits (each one passes `scripts/check.sh`):
1. `Add the media settings and a temporary MEDIA_ROOT for tests`
2. `Add PhotoField that shrinks photos and drops EXIF`
3. `Serve photos to logged-in users only`
4. `Close 006 in the issue`

Open a pull request titled "Upload photos, and show them to logged-in users only". Ask the
reviewer to read `PhotoField` line by line, and to try `/media/../.env` themselves.

## Watch out

- **Don't add `static(settings.MEDIA_URL, ...)` to `urls.py`**, even though many tutorials do: it
  serves photos to everyone, and only while `DEBUG` is on.
- **A form with a file needs both** `enctype="multipart/form-data"` on the `<form>` tag and
  `request.FILES` in the view. Without them the photo never arrives, and the form says "This field
  is required."
- **Path traversal answers 400, not 404.** That's Django's choice for a `SuspiciousOperation`;
  don't catch it.
- **nginx refuses requests over 10 MB first** (deploy guide, part 8), with its own "413 Request
  Entity Too Large" page. The form's "bigger than 10 MB" message shows on your laptop, and on the
  server only for files just under the limit.
- **iPhones store photos as HEIC**, which Pillow can't open. Safari usually converts them to JPEG
  when a website asks for a photo; if a student sees "Upload a valid image", that's the reason
  (they can take a screenshot of the photo and upload that).
- **Old photos stay on disk** when a student uploads a new one (SPEC.md §6.8: accepted, the app is
  small).
- **Photos are personal data**: they live in `var/` (never in git, never in the Docker image), and
  the backups of `var/media/` come in issue 019.

## Worked example

- [03, what a phone photo tells](../docs/examples/03-photo-exif.md): after step 2, read a photo's
  EXIF and GPS position, send it through `PhotoField`, and check what is left.

## Further reading

- [Django: Managing files](https://docs.djangoproject.com/en/6.1/topics/files/) and
  [File uploads](https://docs.djangoproject.com/en/6.1/topics/http/file-uploads/).
- [Django: `ImageField` (forms)](https://docs.djangoproject.com/en/6.1/ref/forms/fields/#imagefield),
  [`FileResponse`](https://docs.djangoproject.com/en/6.1/ref/request-response/#fileresponse-objects),
  [`MEDIA_ROOT`](https://docs.djangoproject.com/en/6.1/ref/settings/#media-root).
- [Django: `SuspiciousOperation`](https://docs.djangoproject.com/en/6.1/ref/exceptions/#suspiciousoperation).
- Pillow: [`ImageOps.exif_transpose`](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html#PIL.ImageOps.exif_transpose),
  [`Image.thumbnail`](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.thumbnail).
- OWASP: [File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
  and [Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal).
- [MDN: `<input type="file">`](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/input/file):
  `accept` and `capture`, and why the browser's checks don't replace the server's.
- [Pillow tutorial](https://pillow.readthedocs.io/en/stable/handbook/tutorial.html): open an
  image, make a thumbnail, save it as JPEG: the steps of `PhotoField`, on their own.
- [Pillow: JPEG saving options](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#jpeg):
  what `quality=85` means, and the `exif` option we don't pass.
- [Wikipedia: Exif, privacy and security](https://en.wikipedia.org/wiki/Exif#Privacy_and_security):
  what a photo can tell about where and when it was taken.
