"""config/settings.py: database options and environment-driven values."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings

BASE_DIR: Path = settings.BASE_DIR


def settings_value(
    expression: str, cwd: Path = BASE_DIR, **env: str
) -> subprocess.CompletedProcess[str]:
    """Import the settings in a fresh interpreter with `env` set explicitly, so
    neither pytest-django nor `.env` can supply the values the test cares about."""
    environ = {**os.environ, **env}
    return subprocess.run(
        [
            sys.executable,
            "-c",
            f"import config.settings as s; print({expression})",
        ],
        cwd=cwd,
        env=environ,
        capture_output=True,
        text=True,
        check=False,
    )


def test_default_database_options() -> None:
    # NAME is not asserted: the test runner replaces it.
    default = settings.DATABASES["default"]

    assert default["OPTIONS"]["transaction_mode"] == "IMMEDIATE"
    assert default["OPTIONS"]["timeout"] == 20
    init_command = default["OPTIONS"]["init_command"]
    assert "PRAGMA journal_mode=WAL;" in init_command
    assert "PRAGMA synchronous=NORMAL;" in init_command


def test_db_path_is_created(tmp_path: Path) -> None:
    db_path = tmp_path / "a" / "b" / "db.sqlite3"

    result = settings_value(
        "s.DATABASES['default']['NAME']",
        DJANGO_DEBUG="true",
        DJANGO_SECRET_KEY="x",
        DJANGO_DB_PATH=str(db_path),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(db_path)
    assert db_path.parent.is_dir()


def test_relative_db_path_resolves_against_base_dir(tmp_path: Path) -> None:
    result = settings_value(
        "s.DATABASES['default']['NAME']",
        # Not BASE_DIR, so a path resolved against the cwd would fail.
        cwd=tmp_path,
        PYTHONPATH=str(BASE_DIR),
        DJANGO_DEBUG="true",
        DJANGO_SECRET_KEY="x",
        DJANGO_DB_PATH="var/x.sqlite3",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(BASE_DIR / "var" / "x.sqlite3")


@pytest.mark.parametrize("secret_key", ["", "   "])
def test_settings_refuse_to_load_without_secret_key_when_not_debug(
    secret_key: str,
) -> None:
    result = settings_value(
        "s.SECRET_KEY", DJANGO_DEBUG="false", DJANGO_SECRET_KEY=secret_key
    )

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr


def test_email_defaults_to_smtp() -> None:
    # Empty counts as unset, and `.env` can't fill a variable that is already set.
    result = settings_value(
        "s.MAILERS['default']['BACKEND'], s.MAILERS['default']['OPTIONS']['host']",
        DJANGO_DEBUG="true",
        DJANGO_SECRET_KEY="x",
        EMAIL_BACKEND="",
        EMAIL_HOST="",
    )

    assert result.returncode == 0, result.stderr
    # print() gets the backend and the host as two arguments.
    assert result.stdout.split() == [
        "django.core.mail.backends.smtp.EmailBackend",
        "localhost",
    ]


def test_file_based_email_goes_to_var_mail() -> None:
    result = settings_value(
        "s.MAILERS['default']['OPTIONS']['file_path']",
        DJANGO_DEBUG="true",
        DJANGO_SECRET_KEY="x",
        EMAIL_BACKEND="django.core.mail.backends.filebased.EmailBackend",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(BASE_DIR / "var" / "mail")


def test_unknown_email_backend_refuses_to_load() -> None:
    result = settings_value(
        "s.MAILERS",
        DJANGO_DEBUG="true",
        DJANGO_SECRET_KEY="x",
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    )

    assert result.returncode != 0
    assert "KeyError" in result.stderr


def test_site_url_defaults_to_the_dev_server() -> None:
    result = settings_value(
        "s.SITE_URL", DJANGO_DEBUG="true", DJANGO_SECRET_KEY="x", DJANGO_SITE_URL=""
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "http://127.0.0.1:8000"


def test_site_url_loses_its_trailing_slash() -> None:
    result = settings_value(
        "s.SITE_URL",
        DJANGO_DEBUG="true",
        DJANGO_SECRET_KEY="x",
        DJANGO_SITE_URL="https://meetups.example.com/",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "https://meetups.example.com"


def test_default_from_email_comes_from_the_environment() -> None:
    result = settings_value(
        "s.DEFAULT_FROM_EMAIL",
        DJANGO_DEBUG="true",
        DJANGO_SECRET_KEY="x",
        DJANGO_DEFAULT_FROM_EMAIL="meetups@example.com",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "meetups@example.com"