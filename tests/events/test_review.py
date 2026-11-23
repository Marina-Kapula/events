from collections.abc import Callable
from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.http import HttpResponseBase
from django.test import Client
from django.utils import timezone
from pytest_django import DjangoCaptureOnCommitCallbacks

from events.models import Event
from events.services import event_approve, event_reject

pytestmark = pytest.mark.django_db


def test_approving_emails_the_organizer(
    make_event: Callable[..., Event],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(status=Event.Status.PENDING)

    with django_capture_on_commit_callbacks(execute=True):
        event_approve(event=event, now=timezone.now())

    event.refresh_from_db()
    assert event.status == Event.Status.APPROVED
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [event.organizer.email]
    assert f"/events/{event.pk}/" in mailoutbox[0].body


def test_a_started_event_cannot_be_approved(make_event: Callable[..., Event]) -> None:
    now = timezone.now()
    event = make_event(status=Event.Status.PENDING, starts_at=now - timedelta(hours=1))

    with pytest.raises(ValidationError, match="already started"):
        event_approve(event=event, now=now)

    event.refresh_from_db()
    assert event.status == Event.Status.PENDING


@pytest.mark.parametrize(
    "status", [Event.Status.APPROVED, Event.Status.REJECTED, Event.Status.CANCELLED]
)
def test_only_a_pending_event_can_be_reviewed(
    make_event: Callable[..., Event], status: Event.Status
) -> None:
    event = make_event(status=status)

    with pytest.raises(ValidationError):
        event_approve(event=event, now=timezone.now())
    with pytest.raises(ValidationError):
        event_reject(event=event, reason="Too vague.")


def test_rejecting_emails_the_reason(
    make_event: Callable[..., Event],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(status=Event.Status.PENDING)

    with django_capture_on_commit_callbacks(execute=True):
        event_reject(event=event, reason="The place is missing.")

    event.refresh_from_db()
    assert event.status == Event.Status.REJECTED
    assert event.review_note == "The place is missing."
    assert mailoutbox[0].to == [event.organizer.email]
    assert "The place is missing." in mailoutbox[0].body


def test_rejecting_needs_a_reason(make_event: Callable[..., Event]) -> None:
    event = make_event(status=Event.Status.PENDING)

    with pytest.raises(ValidationError, match="reason"):
        event_reject(event=event, reason="  ")


def test_the_approve_button(
    admin_client: Client,
    press_admin_button: Callable[..., HttpResponseBase],
    make_event: Callable[..., Event],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(status=Event.Status.PENDING)
    url = f"/admin/events/event/{event.pk}/change/"
    assert b'name="_approve"' in admin_client.get(url).content

    with django_capture_on_commit_callbacks(execute=True):
        response = press_admin_button(event, "_approve")

    assert response.status_code == 302
    assert response["Location"] == url
    event.refresh_from_db()
    assert event.status == Event.Status.APPROVED
    assert len(mailoutbox) == 1
    assert b'name="_approve"' not in admin_client.get(url).content


def test_the_reject_button_takes_the_review_note(
    press_admin_button: Callable[..., HttpResponseBase],
    make_event: Callable[..., Event],
) -> None:
    event = make_event(status=Event.Status.PENDING)

    press_admin_button(event, "_reject", review_note="Add the address.")

    event.refresh_from_db()
    assert event.status == Event.Status.REJECTED
    assert event.review_note == "Add the address."


def test_the_reject_button_without_a_reason_shows_an_error(
    admin_client: Client,
    press_admin_button: Callable[..., HttpResponseBase],
    make_event: Callable[..., Event],
) -> None:
    event = make_event(status=Event.Status.PENDING)

    response = press_admin_button(event, "_reject")

    page = admin_client.get(response["Location"])
    assert "Write the reason" in page.content.decode()
    event.refresh_from_db()
    assert event.status == Event.Status.PENDING
