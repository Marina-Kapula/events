from collections.abc import Callable
from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.utils import timezone
from pytest_django import DjangoCaptureOnCommitCallbacks

from accounts.models import User
from events.models import Event, Participation
from events.services import (
    participation_join,
    participation_leave,
    waiting_list_move_up,
)

pytestmark = pytest.mark.django_db

GOING = Participation.Status.GOING
WAITING = Participation.Status.WAITING


def test_the_last_spot_then_the_waiting_list(
    make_student: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    event = make_event(max_people=3)  # the organizer and two more
    now = timezone.now()

    first = participation_join(event=event, user=make_student(), now=now)
    last = participation_join(event=event, user=make_student(), now=now)
    late = participation_join(event=event, user=make_student(), now=now)

    assert [first.status, last.status, late.status] == [GOING, GOING, WAITING]


def test_the_organizer_cannot_join(make_event: Callable[..., Event]) -> None:
    event = make_event()

    with pytest.raises(ValidationError, match="You organize this event"):
        participation_join(event=event, user=event.organizer, now=timezone.now())


def test_staff_cannot_join(
    make_staff: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    with pytest.raises(ValidationError):
        participation_join(event=make_event(), user=make_staff(), now=timezone.now())


def test_nobody_joins_twice(
    make_event: Callable[..., Event], make_participation: Callable[..., Participation]
) -> None:
    participation = make_participation(make_event(), status=WAITING)

    with pytest.raises(ValidationError, match="already on this event"):
        participation_join(
            event=participation.event, user=participation.user, now=timezone.now()
        )


def test_a_started_event_cannot_be_joined(
    make_student: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    now = timezone.now()
    event = make_event(starts_at=now - timedelta(minutes=1))

    with pytest.raises(ValidationError, match="not open"):
        participation_join(event=event, user=make_student(), now=now)


@pytest.mark.parametrize(
    "status", [Event.Status.PENDING, Event.Status.REJECTED, Event.Status.CANCELLED]
)
def test_only_an_approved_event_can_be_joined(
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    status: Event.Status,
) -> None:
    event = make_event(status=status)

    with pytest.raises(ValidationError, match="not open"):
        participation_join(event=event, user=make_student(), now=timezone.now())


def test_leaving_frees_the_spot_for_the_first_one_waiting(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(max_people=2)
    leaving = make_participation(event, status=GOING)
    first = make_participation(event, status=WAITING)
    second = make_participation(event, status=WAITING)

    with django_capture_on_commit_callbacks(execute=True):
        participation_leave(event=event, user=leaving.user, now=timezone.now())

    assert not Participation.objects.filter(pk=leaving.pk).exists()
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.status, second.status) == (GOING, WAITING)
    assert [message.to for message in mailoutbox] == [
        [event.organizer.email],
        [first.user.email],
    ]
    assert leaving.user.full_name in mailoutbox[0].body
    assert first.user.full_name in mailoutbox[1].body


def test_leaving_the_waiting_list_emails_nobody(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    participation = make_participation(make_event(), status=WAITING)

    with django_capture_on_commit_callbacks(execute=True):
        participation_leave(
            event=participation.event, user=participation.user, now=timezone.now()
        )

    assert not Participation.objects.exists()
    assert mailoutbox == []


def test_nobody_leaves_a_started_event(
    make_event: Callable[..., Event], make_participation: Callable[..., Participation]
) -> None:
    participation = make_participation(make_event())
    later = participation.event.starts_at + timedelta(minutes=1)

    with pytest.raises(ValidationError):
        participation_leave(
            event=participation.event, user=participation.user, now=later
        )

    assert Participation.objects.exists()


def test_move_up_fills_every_free_spot_oldest_first(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(max_people=2)
    make_participation(event, status=GOING)
    waiting = [make_participation(event, status=WAITING) for _ in range(3)]
    # Two more spots, as when the admin approves a bigger event (issue 014).
    event.max_people = 4
    event.save()

    with django_capture_on_commit_callbacks(execute=True):
        waiting_list_move_up(event=event)

    for participation in waiting:
        participation.refresh_from_db()
    assert [p.status for p in waiting] == [GOING, GOING, WAITING]
    assert [message.to for message in mailoutbox] == [
        [waiting[0].user.email],
        [waiting[1].user.email],
    ]
