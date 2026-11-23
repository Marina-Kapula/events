from collections.abc import Callable

import pytest
from django.test import Client
from pytest_django import DjangoAssertNumQueries

from accounts.models import User
from events.models import Event, Participation

pytestmark = pytest.mark.django_db


def test_join_and_leave_redirect_to_the_event_with_a_message(
    client: Client, make_student: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    event = make_event()
    student = make_student()
    client.force_login(student)

    response = client.post(f"/events/{event.pk}/join/", follow=True)

    assert response.redirect_chain == [(f"/events/{event.pk}/", 302)]
    assert b"You&#x27;re going" in response.content
    assert Participation.objects.get().user == student

    response = client.post(f"/events/{event.pk}/leave/", follow=True)

    assert b"You left the event." in response.content
    assert not Participation.objects.exists()


def test_a_broken_rule_comes_back_as_an_error_message(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event()
    client.force_login(event.organizer)

    response = client.post(f"/events/{event.pk}/join/", follow=True)

    assert b"You organize this event" in response.content
    assert not Participation.objects.exists()


@pytest.mark.parametrize("action", ["join", "leave"])
def test_get_changes_nothing(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    action: str,
) -> None:
    event = make_event()
    client.force_login(make_student())

    assert client.get(f"/events/{event.pk}/{action}/").status_code == 405


@pytest.mark.parametrize("action", ["join", "leave"])
def test_staff_get_a_404(
    client: Client,
    make_staff: Callable[..., User],
    make_event: Callable[..., Event],
    action: str,
) -> None:
    event = make_event()
    client.force_login(make_staff())

    assert client.post(f"/events/{event.pk}/{action}/").status_code == 404


def test_a_pending_event_cannot_be_joined(
    client: Client, make_student: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.PENDING)
    client.force_login(make_student())

    response = client.post(f"/events/{event.pk}/join/", follow=True)

    assert b"not open for sign-ups" in response.content
    assert not event.participations.exists()

    other = make_event(status=Event.Status.REJECTED)
    assert client.post(f"/events/{other.pk}/join/").status_code == 404


@pytest.mark.parametrize(
    ("mine", "full", "button"),
    [
        (None, False, b">Join</button>"),
        (None, True, b">Join the waiting list</button>"),
        (Participation.Status.GOING, False, b">Leave</button>"),
        (Participation.Status.WAITING, True, b">Leave the waiting list</button>"),
    ],
)
def test_the_event_page_shows_the_right_button(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mine: Participation.Status | None,
    full: bool,
    button: bytes,
) -> None:
    event = make_event(max_people=2)
    if full:
        make_participation(event, status=Participation.Status.GOING)
    student = make_student()
    if mine:
        make_participation(event, user=student, status=mine)
    client.force_login(student)

    response = client.get(f"/events/{event.pk}/")

    assert button in response.content


def test_the_organizer_sees_no_join_button(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event()
    client.force_login(event.organizer)

    response = client.get(f"/events/{event.pk}/")

    assert b"/join/" not in response.content


def test_the_event_page_lists_who_is_going(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    event = make_event(organizer=make_student(full_name="Organizer Person"))
    make_participation(event, user=make_student(full_name="Going Person"))
    make_participation(
        event,
        user=make_student(full_name="Waiting Person"),
        status=Participation.Status.WAITING,
    )
    client.force_login(make_student())

    content = client.get(f"/events/{event.pk}/").content.decode()

    assert "Going (2 of 8)" in content
    assert content.index("Organizer Person") < content.index("Going Person")
    assert "Waiting Person" not in content
    assert "Waiting: 1" in content


def test_a_cancelled_event_is_visible_to_the_people_on_it_only(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    event = make_event(status=Event.Status.CANCELLED)
    participation = make_participation(event)

    client.force_login(participation.user)
    response = client.get(f"/events/{event.pk}/")
    assert response.status_code == 200
    assert b"/leave/" not in response.content

    client.force_login(make_student())
    assert client.get(f"/events/{event.pk}/").status_code == 404


def test_the_list_shows_spots_taken_without_extra_queries(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    for _ in range(3):
        event = make_event()
        make_participation(event)
        make_participation(event, status=Participation.Status.WAITING)
    client.force_login(make_student())

    with django_assert_num_queries(5):
        response = client.get("/")

    assert response.content.count(b"2 / 8 spots") == 3
