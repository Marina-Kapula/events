import pytest
from django.core.management import call_command

# makemigrations compares the migration history with the database.
pytestmark = pytest.mark.django_db


def test_models_and_migrations_agree() -> None:
    call_command("makemigrations", "--check", "--dry-run")
