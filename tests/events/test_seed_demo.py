import io

import pytest
from django.core.management import CommandError, call_command
from pytest_django import Settings

from accounts.models import User
from events.models import Event, EventChange, Participation

pytestmark = pytest.mark.django_db


@pytest.fixture
def debug(settings: Settings) -> None:
    settings.DEBUG = True  # pytest-django runs tests with DEBUG off


@pytest.mark.usefixtures("debug")
def test_seed_demo_makes_students_and_events_in_every_state() -> None:
    out = io.StringIO()

    call_command("seed_demo", stdout=out)

    assert User.objects.filter(is_staff=False, is_active=True).count() == 8
    assert {event.status for event in Event.objects.all()} == set(Event.Status)
    assert EventChange.objects.count() == 1
    assert Participation.objects.filter(status=Participation.Status.WAITING).exists()
    assert "student1@example.com" in out.getvalue()


@pytest.mark.usefixtures("debug")
def test_seed_demo_runs_again_only_with_reset() -> None:
    call_command("seed_demo", stdout=io.StringIO())

    with pytest.raises(CommandError, match="--reset"):
        call_command("seed_demo", stdout=io.StringIO())
    call_command("seed_demo", "--reset", stdout=io.StringIO())

    assert User.objects.filter(email="student1@example.com").count() == 1


def test_seed_demo_refuses_without_debug() -> None:
    with pytest.raises(CommandError, match="DJANGO_DEBUG"):
        call_command("seed_demo", stdout=io.StringIO())

    assert not User.objects.exists()
