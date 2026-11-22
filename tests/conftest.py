import itertools
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from django.test import override_settings

from accounts.models import User

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
