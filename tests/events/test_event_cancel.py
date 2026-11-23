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

from accounts.models import User
from events.models import Event, EventChange, Participation
from events.services import event_cancel

pytestmark = pytest.mark.django_db


def test_cancelling_emails_everyone_going_or_waiting(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(status=Event.Status.APPROVED, max_people=2)
    going = make_participation(event=event, status=Participation.Status.GOING)
    waiting = make_participation(event=event, status=Participation.Status.WAITING)

    with django_capture_on_commit_callbacks(execute=True):
        event_cancel(event=event, by=event.organizer, now=timezone.now())

    event.refresh_from_db()
    assert event.status == Event.Status.CANCELLED
    assert sorted(message.to[0] for message in mailoutbox) == sorted(
        [going.user.email, waiting.user.email]
    )
    assert event.title in mailoutbox[0].subject
    # Kept, so the event stays in everyone's "My events".
    assert Participation.objects.filter(event=event).count() == 2


def test_cancelling_deletes_the_pending_changes(
    make_event: Callable[..., Event],
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    change = EventChange(event=event)
    event.copy_fields_to(change)
    change.save()

    event_cancel(event=event, by=event.organizer, now=timezone.now())

    assert not EventChange.objects.exists()


def test_the_organizer_cannot_cancel_after_the_start(
    make_event: Callable[..., Event],
) -> None:
    event = make_event(status=Event.Status.APPROVED)

    with pytest.raises(ValidationError, match="started"):
        event_cancel(
            event=event,
            by=event.organizer,
            now=event.starts_at + timedelta(minutes=1),
        )


def test_staff_can_cancel_any_time(
    make_event: Callable[..., Event], make_staff: Callable[..., User]
) -> None:
    event = make_event(status=Event.Status.APPROVED)

    event_cancel(event=event, by=make_staff(), now=event.starts_at + timedelta(hours=1))

    assert event.status == Event.Status.CANCELLED


def test_a_cancelled_event_cannot_be_cancelled_again(
    make_event: Callable[..., Event], make_staff: Callable[..., User]
) -> None:
    event = make_event(status=Event.Status.CANCELLED)

    with pytest.raises(ValidationError, match="already cancelled"):
        event_cancel(event=event, by=make_staff(), now=timezone.now())


def test_the_organizer_cancels_from_the_event_page(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.PENDING)
    client.force_login(event.organizer)
    url = reverse("event_detail", args=[event.pk])

    page = client.get(url)
    response = client.post(reverse("event_cancel", args=[event.pk]), follow=True)

    assert b'command="show-modal"' in page.content
    assert response.redirect_chain == [(url, 302)]
    assert b"Event cancelled" in response.content
    assert b'command="show-modal"' not in response.content
    event.refresh_from_db()
    assert event.status == Event.Status.CANCELLED


def test_cancelling_a_started_event_shows_an_error(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(
        status=Event.Status.APPROVED, starts_at=timezone.now() - timedelta(hours=1)
    )
    client.force_login(event.organizer)

    response = client.post(reverse("event_cancel", args=[event.pk]), follow=True)

    assert b"already started" in response.content
    event.refresh_from_db()
    assert event.status == Event.Status.APPROVED


def test_only_the_organizer_may_cancel(
    client: Client,
    make_event: Callable[..., Event],
    make_student: Callable[..., User],
    make_staff: Callable[..., User],
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    url = reverse("event_cancel", args=[event.pk])

    client.force_login(make_student())
    assert client.post(url).status_code == 404
    client.force_login(make_staff())
    assert client.post(url).status_code == 404
    assert client.get(url).status_code == 405


def test_a_cancelled_event_is_seen_by_the_people_on_it_only(
    client: Client,
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    make_student: Callable[..., User],
) -> None:
    event = make_event(status=Event.Status.CANCELLED)
    participation = make_participation(event=event)
    url = reverse("event_detail", args=[event.pk])

    client.force_login(participation.user)
    page = client.get(url)
    assert b"cancelled" in page.content
    assert reverse("event_leave", args=[event.pk]).encode() not in page.content
    client.force_login(make_student())
    assert client.get(url).status_code == 404


def test_the_admin_cancels_an_event(
    admin_client: Client,
    press_admin_button: Callable[..., HttpResponseBase],
    make_event: Callable[..., Event],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    url = reverse("admin:events_event_change", args=[event.pk])
    assert b'name="_cancel"' in admin_client.get(url).content

    with django_capture_on_commit_callbacks(execute=True):
        response = press_admin_button(event, "_cancel")

    assert response.status_code == 302
    event.refresh_from_db()
    assert event.status == Event.Status.CANCELLED
    assert b'name="_cancel"' not in admin_client.get(url).content
