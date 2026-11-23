from collections.abc import Callable

import pytest
from django.test import Client
from django.utils import timezone

from accounts.models import User
from events.models import Event

pytestmark = pytest.mark.django_db


def test_an_approved_event_is_visible_to_everyone(
    client: Client, make_staff: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    event = make_event(title="Pizza night")
    client.force_login(make_staff())

    response = client.get(f"/events/{event.pk}/")

    assert response.status_code == 200
    assert b"Pizza night" in response.content
    assert event.organizer.full_name.encode() in response.content


def test_everyone_sees_a_pending_event(
    client: Client, make_student: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.PENDING)
    client.force_login(make_student())

    response = client.get(f"/events/{event.pk}/")

    assert response.status_code == 200
    assert b"Not approved yet" in response.content


@pytest.mark.parametrize("status", [Event.Status.REJECTED, Event.Status.CANCELLED])
def test_only_the_organizer_sees_a_rejected_or_cancelled_event(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    status: Event.Status,
) -> None:
    event = make_event(status=status)

    client.force_login(make_student())
    assert client.get(f"/events/{event.pk}/").status_code == 404

    client.force_login(event.organizer)
    assert client.get(f"/events/{event.pk}/").status_code == 200


def test_the_organizer_sees_why_it_was_rejected(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.REJECTED, review_note="Add the address.")
    client.force_login(event.organizer)

    response = client.get(f"/events/{event.pk}/")

    assert b"Add the address." in response.content


def test_an_unknown_event_is_a_404(
    client: Client, make_student: Callable[..., User]
) -> None:
    client.force_login(make_student())

    assert client.get("/events/999/").status_code == 404


def test_an_event_by_staff_shows_amfi_as_organizer(
    client: Client,
    make_student: Callable[..., User],
    make_staff: Callable[..., User],
    make_event: Callable[..., Event],
) -> None:
    staff = make_staff(full_name="Staff Person")
    event = make_event(organizer=staff)
    client.force_login(make_student())

    response = client.get(f"/events/{event.pk}/")

    assert b"AMFI" in response.content
    assert b"Staff Person" not in response.content


def test_a_deleted_organizer_is_shown_as_deleted_student(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
) -> None:
    organizer = make_student(full_name="Gone Student", deleted_at=timezone.now())
    event = make_event(organizer=organizer)
    client.force_login(make_student())

    response = client.get(f"/events/{event.pk}/")

    assert b"Deleted student" in response.content
    assert b"Gone Student" not in response.content
