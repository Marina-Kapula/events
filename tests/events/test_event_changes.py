from collections.abc import Callable
from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.http import HttpResponseBase
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pytest_django import DjangoCaptureOnCommitCallbacks

from events.models import Event, EventChange, Participation
from events.services import event_change_approve, event_change_reject

pytestmark = pytest.mark.django_db


def make_change(event: Event, **changes: object) -> EventChange:
    change = EventChange(event=event)
    event.copy_fields_to(change)
    for name, value in changes.items():
        setattr(change, name, value)
    change.full_clean()
    change.save()
    return change


def test_approving_copies_the_changes_and_emails_everyone(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(status=Event.Status.APPROVED, title="Pizza night")
    going = make_participation(event=event)
    make_change(event, title="Pasta night", photo="photos/events/pasta.jpg")

    with django_capture_on_commit_callbacks(execute=True):
        event_change_approve(event=event, now=timezone.now())

    event.refresh_from_db()
    assert event.title == "Pasta night"
    assert event.photo.name == "photos/events/pasta.jpg"
    assert not EventChange.objects.exists()
    assert sorted(message.to[0] for message in mailoutbox) == sorted(
        [event.organizer.email, going.user.email]
    )


def test_approving_more_spots_moves_the_waiting_list_up(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    event = make_event(status=Event.Status.APPROVED, max_people=2)
    make_participation(event=event, status=Participation.Status.GOING)
    waiting = make_participation(event=event, status=Participation.Status.WAITING)
    make_change(event, max_people=3)

    event_change_approve(event=event, now=timezone.now())

    waiting.refresh_from_db()
    assert waiting.status == Participation.Status.GOING


def test_approving_refuses_fewer_spots_than_people_going(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    event = make_event(status=Event.Status.APPROVED, max_people=4)
    make_change(event, max_people=2)
    make_participation(event=event)
    make_participation(event=event)  # joined while AMFI was reviewing

    with pytest.raises(ValidationError, match="at least 3"):
        event_change_approve(event=event, now=timezone.now())

    event.refresh_from_db()
    assert event.max_people == 4


def test_approving_refuses_a_start_in_the_past(
    make_event: Callable[..., Event],
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    change = make_change(event)

    with pytest.raises(ValidationError, match="passed"):
        event_change_approve(event=event, now=change.starts_at + timedelta(minutes=1))


def test_rejecting_keeps_the_event_and_emails_the_reason(
    make_event: Callable[..., Event],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(status=Event.Status.APPROVED, title="Pizza night")
    make_change(event, title="Pasta night")

    with django_capture_on_commit_callbacks(execute=True):
        event_change_reject(event=event, reason="Say where's the pasta from.")

    event.refresh_from_db()
    assert event.title == "Pizza night"
    assert event.review_note == "Say where's the pasta from."
    assert not EventChange.objects.exists()
    assert [message.to for message in mailoutbox] == [[event.organizer.email]]
    assert "Say where's the pasta from." in mailoutbox[0].body  # not &#x27;


def test_rejecting_needs_a_reason(make_event: Callable[..., Event]) -> None:
    event = make_event(status=Event.Status.APPROVED)
    make_change(event)

    with pytest.raises(ValidationError, match="reason"):
        event_change_reject(event=event, reason=" ")

    assert EventChange.objects.exists()


def test_the_admin_shows_the_buttons_only_with_changes(
    admin_client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    url = reverse("admin:events_event_change", args=[event.pk])

    assert b'name="_approve_changes"' not in admin_client.get(url).content
    make_change(event)
    assert b'name="_approve_changes"' in admin_client.get(url).content


def test_the_admin_approves_changes(
    press_admin_button: Callable[..., HttpResponseBase],
    make_event: Callable[..., Event],
) -> None:
    event = make_event(status=Event.Status.APPROVED, title="Pizza night")
    make_change(event, title="Pasta night")

    response = press_admin_button(event, "_approve_changes")

    assert response.status_code == 302
    event.refresh_from_db()
    assert event.title == "Pasta night"
    assert not EventChange.objects.exists()


def test_the_admin_needs_a_reason_to_reject_changes(
    admin_client: Client,
    press_admin_button: Callable[..., HttpResponseBase],
    make_event: Callable[..., Event],
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    make_change(event)

    response = press_admin_button(event, "_reject_changes")

    assert response.status_code == 302
    assert EventChange.objects.exists()
    page = admin_client.get(response["Location"])
    assert b"Write the reason in the review note" in page.content


def test_the_admin_rejects_changes_with_the_review_note(
    press_admin_button: Callable[..., HttpResponseBase],
    make_event: Callable[..., Event],
) -> None:
    event = make_event(status=Event.Status.APPROVED, title="Pizza night")
    make_change(event, title="Pasta night")

    press_admin_button(event, "_reject_changes", review_note="Keep the pizza.")

    event.refresh_from_db()
    assert event.title == "Pizza night"
    assert event.review_note == "Keep the pizza."
    assert not EventChange.objects.exists()
