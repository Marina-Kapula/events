from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pytest_django import Settings

from accounts.models import RegistrationWindow, User

pytestmark = pytest.mark.django_db

NOON = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
CHANGELIST = "/admin/accounts/registrationwindow/"


def test_a_window_is_open_until_it_expires(
    make_window: Callable[..., RegistrationWindow],
) -> None:
    window = make_window(opened_at=NOON, expires_at=NOON + timedelta(minutes=30))

    assert window.is_open(now=NOON + timedelta(minutes=29))
    assert not window.is_open(now=NOON + timedelta(minutes=30))


def test_a_closed_window_is_not_open(
    make_window: Callable[..., RegistrationWindow],
) -> None:
    window = make_window(
        opened_at=NOON,
        expires_at=NOON + timedelta(minutes=30),
        closed_at=NOON + timedelta(minutes=5),
    )

    assert not window.is_open(now=NOON + timedelta(minutes=10))


def test_each_window_gets_its_own_random_code(
    make_window: Callable[..., RegistrationWindow],
) -> None:
    first, second = make_window(), make_window()

    assert len(first.code) == 22
    assert first.code != second.code


def test_admin_opens_a_window_for_the_chosen_duration(
    admin_client: Client, admin_user: User
) -> None:
    response = admin_client.post(f"{CHANGELIST}add/", {"duration": "60"})

    window = RegistrationWindow.objects.get()
    assert response.status_code == 302
    assert response["Location"] == f"{CHANGELIST}{window.pk}/change/"
    assert window.opened_by == admin_user
    assert window.expires_at - window.opened_at == timedelta(minutes=60)


def test_window_page_shows_the_qr_code_and_the_link(
    admin_client: Client,
    settings: Settings,
    make_window: Callable[..., RegistrationWindow],
) -> None:
    settings.SITE_URL = "https://meetups.example.com"
    window = make_window()

    response = admin_client.get(f"{CHANGELIST}{window.pk}/change/")

    assert response.status_code == 200
    assert b"<svg" in response.content
    url = f"https://meetups.example.com/register/{window.code}/"
    assert url.encode() in response.content


def test_window_page_lists_the_students_who_registered(
    admin_client: Client,
    make_window: Callable[..., RegistrationWindow],
    make_student: Callable[..., User],
) -> None:
    window = make_window()
    make_student(full_name="Student One", registration_window=window)
    make_student(full_name="Student Two")

    response = admin_client.get(f"{CHANGELIST}{window.pk}/change/")

    assert b"Student One" in response.content
    assert b"Student Two" not in response.content


def test_close_now_closes_the_selected_windows(
    admin_client: Client, make_window: Callable[..., RegistrationWindow]
) -> None:
    window = make_window()

    response = admin_client.post(
        CHANGELIST, {"action": "close_now", "_selected_action": [window.pk]}
    )

    window.refresh_from_db()
    assert response.status_code == 302
    assert window.closed_at is not None
    assert not window.is_open(now=timezone.now())


def test_register_page_is_public_while_the_window_is_open(
    client: Client, make_window: Callable[..., RegistrationWindow]
) -> None:
    window = make_window()

    response = client.get(reverse("register", args=(window.code,)))

    assert response.status_code == 200
    assert b"Registration is open" in response.content


@pytest.mark.parametrize(
    "overrides",
    [
        {"closed_at": timezone.now()},
        {"opened_at": NOON, "expires_at": NOON + timedelta(minutes=15)},
    ],
    ids=["closed", "expired"],
)
def test_register_page_says_closed_when_the_window_is_not_open(
    client: Client,
    make_window: Callable[..., RegistrationWindow],
    overrides: dict[str, object],
) -> None:
    window = make_window(**overrides)

    response = client.get(reverse("register", args=(window.code,)))

    assert response.status_code == 200
    assert b"Registration closed, ask the AMFI staff" in response.content


def test_unknown_code_is_a_404(client: Client) -> None:
    assert client.get("/register/not-a-code/").status_code == 404
