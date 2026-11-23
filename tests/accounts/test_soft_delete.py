from collections.abc import Callable
from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pytest_django import DjangoCaptureOnCommitCallbacks

from accounts.models import User
from accounts.services import user_soft_delete
from events.models import Event, Participation

pytestmark = pytest.mark.django_db


def test_the_account_is_closed(make_student: Callable[..., User]) -> None:
    student = make_student()
    now = timezone.now()

    user_soft_delete(user=student, now=now)

    student.refresh_from_db()
    assert not student.is_active
    assert student.deleted_at == now


def test_upcoming_events_are_cancelled_and_past_ones_stay(
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    student = make_student()
    now = timezone.now()
    upcoming = make_event(
        organizer=student,
        starts_at=now + timedelta(days=2),
        status=Event.Status.APPROVED,
    )
    pending = make_event(
        organizer=student,
        starts_at=now + timedelta(days=3),
        status=Event.Status.PENDING,
    )
    past = make_event(
        organizer=student,
        starts_at=now - timedelta(days=2),
        status=Event.Status.APPROVED,
    )
    going = make_participation(event=upcoming)

    with django_capture_on_commit_callbacks(execute=True):
        user_soft_delete(user=student, now=now)

    for event in (upcoming, pending, past):
        event.refresh_from_db()
    assert upcoming.status == Event.Status.CANCELLED
    assert pending.status == Event.Status.CANCELLED
    assert past.status == Event.Status.APPROVED
    assert [message.to for message in mailoutbox] == [[going.user.email]]


def test_participations_go_and_the_waiting_list_moves_up(
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    student = make_student()
    event = make_event(status=Event.Status.APPROVED, max_people=2)
    make_participation(event=event, user=student, status=Participation.Status.GOING)
    waiting = make_participation(event=event, status=Participation.Status.WAITING)

    with django_capture_on_commit_callbacks(execute=True):
        user_soft_delete(user=student, now=timezone.now())

    assert not Participation.objects.filter(user=student).exists()
    waiting.refresh_from_db()
    assert waiting.status == Participation.Status.GOING
    assert [message.to for message in mailoutbox] == [[waiting.user.email]]


def test_the_profile_is_gone_and_past_events_say_deleted_student(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
) -> None:
    student = make_student(full_name="Student One")
    past = make_event(
        organizer=student,
        starts_at=timezone.now() - timedelta(days=1),
        status=Event.Status.APPROVED,
    )
    user_soft_delete(user=student, now=timezone.now())
    client.force_login(make_student())

    assert client.get(reverse("student_detail", args=[student.pk])).status_code == 404
    page = client.get(reverse("event_detail", args=[past.pk]))
    assert b"Deleted student" in page.content
    assert b"Student One" not in page.content


def test_a_deleted_student_cannot_log_in(
    client: Client, make_student: Callable[..., User]
) -> None:
    student = make_student()
    user_soft_delete(user=student, now=timezone.now())

    response = client.post(
        reverse("login"), {"username": student.email, "password": "s3cret-pass"}
    )

    assert response.status_code == 200  # the form again, with an error
    assert "_auth_user_id" not in client.session


def test_the_admin_action_asks_first_then_soft_deletes_students_only(
    admin_client: Client,
    make_student: Callable[..., User],
    make_staff: Callable[..., User],
) -> None:
    student = make_student(full_name="Student One")
    staff = make_staff()
    url = reverse("admin:accounts_user_changelist")
    data = {"action": "soft_delete", "_selected_action": [student.pk, staff.pk]}

    page = admin_client.post(url, data)
    student.refresh_from_db()
    assert page.status_code == 200
    assert b"Student One" in page.content
    assert student.is_active

    response = admin_client.post(url, {**data, "confirm": "yes"}, follow=True)
    student.refresh_from_db()
    staff.refresh_from_db()
    assert not student.is_active
    assert staff.is_active
    assert b"Soft deleted 1 student(s)" in response.content
