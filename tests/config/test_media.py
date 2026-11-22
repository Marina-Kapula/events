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

    assert response.status_code == 400
    assert b"not-for-you" not in response.content
