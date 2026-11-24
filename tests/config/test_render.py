"""What the Render deploy needs: email over Brevo's API, photos in the database, and
an admin made from environment variables (docs/deployment/render.md)."""

import io
import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.core.management import call_command
from django.test import Client, override_settings

from accounts.models import User
from config import brevo
from files.models import StoredFile

pytestmark = pytest.mark.django_db


@pytest.fixture
def requests(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    sent: list[Any] = []

    def urlopen(request: Any, timeout: float) -> io.BytesIO:
        sent.append(request)
        return io.BytesIO(b'{"messageId": "1"}')

    monkeypatch.setattr(brevo.urllib.request, "urlopen", urlopen)
    return sent


def test_brevo_posts_the_message_as_json(requests: list[Any]) -> None:
    message = EmailMultiAlternatives(
        subject="Hi",
        body="Plain text",
        from_email="AMFI Meetups <amfi@example.com>",
        to=["ann@example.com"],
    )
    message.attach_alternative("<p>Hi</p>", "text/html")

    sent = brevo.BrevoEmailBackend(api_key="key").send_messages([message])

    assert sent == 1
    request = requests[0]
    assert request.full_url == "https://api.brevo.com/v3/smtp/email"
    assert request.get_header("Api-key") == "key"
    assert json.loads(request.data) == {
        "sender": {"email": "amfi@example.com", "name": "AMFI Meetups"},
        "to": [{"email": "ann@example.com"}],
        "subject": "Hi",
        "textContent": "Plain text",
        "htmlContent": "<p>Hi</p>",
    }


def test_brevo_needs_a_key() -> None:
    with pytest.raises(ImproperlyConfigured, match="BREVO_API_KEY"):
        brevo.BrevoEmailBackend(api_key="")


def test_brevo_raises_when_the_api_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(request: Any, timeout: float) -> io.BytesIO:
        raise OSError("down")

    monkeypatch.setattr(brevo.urllib.request, "urlopen", urlopen)
    message = EmailMessage(subject="Hi", body="x", from_email="a@x.com", to=["b@x.com"])

    with pytest.raises(OSError, match="down"):
        brevo.BrevoEmailBackend(api_key="key").send_messages([message])
    assert (
        brevo.BrevoEmailBackend(api_key="k", fail_silently=True).send_messages(
            [message]
        )
        == 0
    )


@pytest.fixture
def media_in_db() -> Iterator[None]:
    with override_settings(
        STORAGES={
            "default": {"BACKEND": "files.storage.DatabaseStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        }
    ):
        yield


@pytest.mark.usefixtures("media_in_db")
def test_photos_are_kept_in_the_database_and_served(
    client: Client, make_student: Callable[..., User]
) -> None:
    name = default_storage.save("photos/users/me.jpg", ContentFile(b"\xff\xd8 jpeg"))
    again = default_storage.save("photos/users/me.jpg", ContentFile(b"\xff\xd8 two"))

    assert name == "photos/users/me.jpg"
    assert again != name  # a new name, as on the disk
    assert StoredFile.objects.count() == 2
    assert default_storage.size(name) == 7
    assert default_storage.url(name) == "/media/photos/users/me.jpg"

    client.force_login(make_student())
    response = client.get("/media/photos/users/me.jpg")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"
    assert response.getvalue() == b"\xff\xd8 jpeg"
    assert client.get("/media/photos/users/nobody.jpg").status_code == 404

    default_storage.delete(name)
    assert not default_storage.exists(name)


def test_ensure_admin_creates_the_admin_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DJANGO_ADMIN_EMAIL", "Boss@Example.com")
    monkeypatch.setenv("DJANGO_ADMIN_PASSWORD", "first-pass-123")

    call_command("ensure_admin")
    monkeypatch.setenv("DJANGO_ADMIN_PASSWORD", "second-pass-456")
    call_command("ensure_admin")

    admin = User.objects.get()
    assert admin.email == "boss@example.com"
    assert admin.is_superuser
    assert admin.check_password("first-pass-123")


def test_ensure_admin_without_variables_does_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DJANGO_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("DJANGO_ADMIN_PASSWORD", raising=False)

    call_command("ensure_admin")

    assert not User.objects.exists()
