from collections.abc import Callable
from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pytest_django import DjangoAssertNumQueries

from accounts.models import User
from events.models import Event, Participation

pytestmark = pytest.mark.django_db


def test_created_has_every_own_event_and_the_reason_when_rejected(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
) -> None:
    me = make_student()
    soon = timezone.now() + timedelta(days=1)
    make_event(
        organizer=me,
        title="Pasta night",
        starts_at=soon + timedelta(days=1),
        status=Event.Status.APPROVED,
    )
    make_event(
        organizer=me,
        title="Pizza night",
        starts_at=soon,
        status=Event.Status.REJECTED,
        review_note="Add the place.",
    )
    make_event(title="Someone else's")
    client.force_login(me)

    response = client.get(reverse("my_events"))

    created = [event.title for event in response.context["created"]]
    assert created == ["Pizza night", "Pasta night"]
    assert b"Add the place." in response.content


def test_joined_has_upcoming_events_first_then_past_and_cancelled(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    me = make_student()
    now = timezone.now()
    approved = Event.Status.APPROVED
    events = [
        make_event(title="Past", starts_at=now - timedelta(days=3), status=approved),
        make_event(
            title="Next week", starts_at=now + timedelta(days=7), status=approved
        ),
        make_event(
            title="Cancelled",
            starts_at=now + timedelta(days=1),
            status=Event.Status.CANCELLED,
        ),
        make_event(
            title="Tomorrow", starts_at=now + timedelta(days=1), status=approved
        ),
    ]
    for event in events:
        make_participation(event=event, user=me)
    Participation.objects.filter(event__title="Next week").update(
        status=Participation.Status.WAITING
    )
    make_event(title="Not joined")
    client.force_login(me)

    response = client.get(reverse("my_events"))

    joined = [event.title for event in response.context["joined"]]
    assert joined == ["Tomorrow", "Next week", "Past", "Cancelled"]
    assert b"You are on the waiting list." in response.content
    # The organizer and me where I'm going; only the organizer where I'm waiting.
    assert response.content.count(b"2 / 8 spots") == 3
    assert response.content.count(b"1 / 8 spots") == 1


def test_joined_by_counts_everyone_going_in_either_order(
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    me = make_student()
    event = make_event(status=Event.Status.APPROVED)
    for student in (me, make_student(), make_student()):
        make_participation(event=event, user=student)

    # Three going, whichever method runs first. A joined_by written as
    # filter(participations__user=me) counts 1 in the first order (worked example 10).
    assert Event.objects.joined_by(me).with_going_count().filter(going_count=3).exists()
    assert Event.objects.with_going_count().joined_by(me).filter(going_count=3).exists()


def test_my_events_runs_the_same_queries_for_any_number_of_events(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    me = make_student()
    for _ in range(3):
        make_event(organizer=me)
        make_participation(event=make_event(), user=me)
    client.force_login(me)

    # The session, the user, then one query per list.
    with django_assert_num_queries(4):
        client.get(reverse("my_events"))


def test_students_see_the_link_and_staff_get_a_404(
    client: Client, make_student: Callable[..., User], make_staff: Callable[..., User]
) -> None:
    link = f'href="{reverse("my_events")}"'.encode()

    client.force_login(make_student())
    assert link in client.get(reverse("home")).content
    client.force_login(make_staff())
    assert link not in client.get(reverse("home")).content
    assert client.get(reverse("my_events")).status_code == 404
