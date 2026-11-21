from collections.abc import Iterator

import pytest
from django.test import override_settings


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
def _fast_password_hashing() -> Iterator[None]:
    # Django's default hasher is slow on purpose; tests create many users.
    with override_settings(
        PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
    ):
        yield
