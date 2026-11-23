import itertools
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from django.test import override_settings
from django.utils import timezone

from accounts.models import RegistrationWindow, User
from events.models import Event, Participation

PASSWORD = "s3cret-pass"


@pytest.fixture(autouse=True)
def _static_files_without_collectstatic() -> Iterator[None]:
    # Tests render pages with DEBUG off but never run collectstatic: the manifest
    # storage would refuse every file, and WhiteNoise would warn that STATIC_ROOT is
    # missing unless it looks files up per request, as in development.
    with override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        },
        WHITENOISE_AUTOREFRESH=True,
    ):
        yield


@pytest.fixture(autouse=True)
def _media_root_in_tmp_path(tmp_path: Path) -> Iterator[None]:
    with override_settings(MEDIA_ROOT=tmp_path / "media"):
        yield


@pytest.fixture(autouse=True)
def _fast_password_hashing() -> Iterator[None]:
    # Django's default hasher is slow on purpose; tests create many users.
    with override_settings(
        PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
    ):
        yield


@pytest.fixture
def make_student(db: None) -> Callable[..., User]:
    numbers = itertools.count(1)

    def make(email: str | None = None, **overrides: object) -> User:
        n = next(numbers)
        fields: dict[str, object] = {
            "full_name": f"Student {n}",
            "photo": "photos/users/student.jpg",
            "nationality": "ES",
            "age": 22,
            "gender": User.Gender.FEMALE,
            "is_active": True,
            **overrides,
        }
        return User.objects.create_user(
            email or f"student{n}@example.com", PASSWORD, **fields
        )

    return make


@pytest.fixture
def make_staff(db: None) -> Callable[..., User]:
    numbers = itertools.count(1)

    def make(**overrides: object) -> User:
        n = next(numbers)
        fields: dict[str, object] = {"full_name": f"Staff {n}", **overrides}
        return User.objects.create_superuser(
            f"staff{n}@example.com", PASSWORD, **fields
        )

    return make


@pytest.fixture
def admin_user(make_staff: Callable[..., User]) -> User:
    return make_staff()


@pytest.fixture
def make_window(make_staff: Callable[..., User]) -> Callable[..., RegistrationWindow]:
    def make(**overrides: object) -> RegistrationWindow:
        fields: dict[str, object] = {
            "opened_by": make_staff(),
            "expires_at": timezone.now() + timedelta(minutes=30),
            **overrides,
        }
        window = RegistrationWindow(**fields)
        window.full_clean()
        window.save()
        return window

    return make


@pytest.fixture
def make_event(make_student: Callable[..., User]) -> Callable[..., Event]:
    numbers = itertools.count(1)

    def make(**overrides: object) -> Event:
        n = next(numbers)
        fields: dict[str, object] = {
            "title": f"Event {n}",
            "description": "We meet at the fountain.",
            # A file name is enough for the model; a test that uploads makes an image.
            "photo": "photos/events/event.jpg",
            "city": "Avezzano",
            "place": "Piazza Risorgimento",
            "starts_at": timezone.now() + timedelta(days=7),
            "type": Event.Type.FOOD,
            "max_people": 8,
            # Most tests need an event everyone can see; pass status= for the others.
            "status": Event.Status.APPROVED,
            **overrides,
        }
        if "organizer" not in fields:
            fields["organizer"] = make_student()
        event = Event(**fields)
        event.full_clean()
        event.save()
        return event

    return make


@pytest.fixture
def make_participation(
    make_student: Callable[..., User],
) -> Callable[..., Participation]:
    def make(event: Event, **overrides: object) -> Participation:
        fields: dict[str, object] = {"status": Participation.Status.GOING, **overrides}
        if "user" not in fields:
            fields["user"] = make_student()
        participation = Participation(event=event, **fields)
        participation.full_clean()
        participation.save()
        return participation

    return make
