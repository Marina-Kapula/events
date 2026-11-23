"""The bell, the chat and the badges on the cards (our choice, not SPEC)."""

from collections.abc import Callable
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from events.models import Comment, Event, Notification, Participation
from events.services import (
    comment_add,
    event_approve,
    event_cancel,
    participation_join,
    participation_leave,
)

pytestmark = pytest.mark.django_db


def texts(user: User) -> list[str]:
    return list(Notification.objects.filter(user=user).values_list("text", flat=True))


def test_joining_rings_the_organizers_bell(
    make_event: Callable[..., Event], make_student: Callable[..., User]
) -> None:
    event = make_event(title="Pizza night")
    student = make_student(full_name="Kwame Mensah")

    participation_join(event=event, user=student, now=timezone.now())

    assert texts(event.organizer) == ["Kwame Mensah is going"]


def test_leaving_gives_the_spot_and_tells_the_next_in_line(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    event = make_event(title="Pizza night", max_people=2)
    going = make_participation(event)
    waiting = make_participation(event, status=Participation.Status.WAITING)

    participation_leave(event=event, user=going.user, now=timezone.now())

    assert texts(waiting.user) == ["A spot freed up: you're going!"]
    assert f"{going.user.full_name} left" in texts(event.organizer)


def test_approving_tells_the_organizer_only(
    make_event: Callable[..., Event], make_student: Callable[..., User]
) -> None:
    event = make_event(status=Event.Status.PENDING)
    student = make_student()

    event_approve(event=event, now=timezone.now())

    assert texts(event.organizer) == ["Approved: it's live! 🎉"]
    assert texts(student) == []


def test_cancelling_tells_everyone_on_it(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    event = make_event(title="Walk")
    going = make_participation(event)
    waiting = make_participation(event, status=Participation.Status.WAITING)

    event_cancel(event=event, by=event.organizer, now=timezone.now())

    assert texts(going.user) == ["Cancelled."]
    assert texts(waiting.user) == ["Cancelled."]


def test_a_comment_tells_everyone_but_the_author(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    event = make_event(title="Walk")
    one = make_participation(event)
    two = make_participation(event)

    comment_add(event=event, author=one.user, text="  Who brings water?  ")

    assert Comment.objects.get().text == "Who brings water?"
    expected = [f"{one.user.full_name}: Who brings water?"]
    assert texts(event.organizer) == expected
    assert texts(two.user) == expected
    assert texts(one.user) == []


def test_a_long_comment_is_cut_in_the_bell(
    make_event: Callable[..., Event], make_student: Callable[..., User]
) -> None:
    event = make_event(title="Walk")

    comment_add(event=event, author=make_student(full_name="Ann"), text="a" * 100)

    assert texts(event.organizer) == [f"Ann: {'a' * 59}…"]


@pytest.mark.parametrize("text", ["", "   ", "a" * 501])
def test_a_comment_needs_1_to_500_characters(
    make_event: Callable[..., Event], make_student: Callable[..., User], text: str
) -> None:
    with pytest.raises(ValidationError):
        comment_add(event=make_event(), author=make_student(), text=text)


@pytest.mark.parametrize("status", [Event.Status.CANCELLED, Event.Status.REJECTED])
def test_no_comments_on_a_closed_event(
    make_event: Callable[..., Event], status: Event.Status
) -> None:
    event = make_event(status=status)

    with pytest.raises(ValidationError):
        comment_add(event=event, author=event.organizer, text="Hi")


def test_the_chat_on_the_event_page(
    client: Client, make_event: Callable[..., Event], make_student: Callable[..., User]
) -> None:
    event = make_event()
    student = make_student()
    client.force_login(student)

    response = client.post(
        reverse("comment_add", args=[event.pk]), {"text": "Late by 10 minutes"}
    )

    assert response["Location"] == f"/events/{event.pk}/#comments"
    page = client.get(f"/events/{event.pk}/").content.decode()
    assert "Late by 10 minutes" in page
    assert 'name="text"' in page


def test_no_chat_on_an_event_you_cannot_see(
    client: Client, make_event: Callable[..., Event], make_student: Callable[..., User]
) -> None:
    event = make_event(status=Event.Status.REJECTED)
    client.force_login(make_student())

    response = client.post(reverse("comment_add", args=[event.pk]), {"text": "Hi"})

    assert response.status_code == 404
    assert not Comment.objects.exists()


def test_the_bell_shows_the_count_and_the_page_marks_them_read(
    client: Client, make_event: Callable[..., Event], make_student: Callable[..., User]
) -> None:
    event = make_event(title="Walk")
    participation_join(event=event, user=make_student(), now=timezone.now())
    client.force_login(event.organizer)

    assert b"Notifications: 1 new" in client.get("/").content
    page = client.get(reverse("notifications")).content.decode()
    assert "Walk" in page
    assert "is going" in page
    assert "Your event" in page
    assert b"Notifications: 1 new" not in client.get("/").content


def test_the_card_shows_who_is_going_and_what_is_urgent(
    client: Client,
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    make_student: Callable[..., User],
) -> None:
    event = make_event(max_people=3, starts_at=timezone.now() + timedelta(hours=5))
    make_participation(event, user=make_student(full_name="Kwame Mensah"))
    client.force_login(make_student())

    page = client.get("/").content.decode()

    assert f"by {event.organizer.full_name}" in page
    assert "1 going" in page
    assert "🔥 Only 1 spot left" in page
    assert "⏰ Starts in 4\xa0hours" in page or "⏰ Starts in 5\xa0hours" in page


def test_a_notification_about_an_event_you_cannot_see_is_hidden(
    client: Client,
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    event = make_event(title="Walk")
    participation = make_participation(event)
    comment_add(event=event, author=event.organizer, text="Hi all")
    participation_leave(event=event, user=participation.user, now=timezone.now())
    event_cancel(event=event, by=event.organizer, now=timezone.now())
    client.force_login(participation.user)

    page = client.get(reverse("notifications")).content.decode()

    assert "Hi all" not in page


def test_a_pending_card_says_sign_ups_open_later(
    client: Client, make_event: Callable[..., Event], make_student: Callable[..., User]
) -> None:
    make_event(status=Event.Status.PENDING)
    client.force_login(make_student())

    page = client.get("/").content.decode()

    assert "Sign-ups open once approved" in page
    assert "Be the first to join!" not in page
