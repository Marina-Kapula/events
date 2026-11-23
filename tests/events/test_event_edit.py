import io
from collections.abc import Callable
from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from pytest_django import DjangoCaptureOnCommitCallbacks

from accounts.models import User
from events.models import Event, EventChange, Participation

pytestmark = pytest.mark.django_db


def form_data(event: Event, **changes: object) -> dict[str, object]:
    """The edit form as the browser sends it: every field, no new photo."""
    return {
        "title": event.title,
        "description": event.description,
        "city": event.city,
        "place": event.place,
        "starts_at": timezone.localtime(event.starts_at).strftime("%Y-%m-%dT%H:%M"),
        "type": event.type,
        "max_people": event.max_people,
        "language": event.language,
        **changes,
    }


def test_editing_a_pending_event_saves_it_and_emails_staff(
    client: Client,
    make_event: Callable[..., Event],
    make_staff: Callable[..., User],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    staff = make_staff()
    event = make_event(status=Event.Status.PENDING)
    client.force_login(event.organizer)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("event_edit", args=[event.pk]),
            form_data(event, title="Pizza night"),
        )

    assert response.status_code == 302
    event.refresh_from_db()
    assert event.title == "Pizza night"
    assert event.status == Event.Status.PENDING
    assert [message.to for message in mailoutbox] == [[staff.email]]
    assert f"/admin/events/event/{event.pk}/change/" in mailoutbox[0].body


def test_editing_a_rejected_event_sends_it_back_to_review(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.REJECTED, review_note="No place given.")
    client.force_login(event.organizer)

    client.post(
        reverse("event_edit", args=[event.pk]),
        form_data(event, place="Bar Centrale"),
    )

    event.refresh_from_db()
    assert event.status == Event.Status.PENDING
    assert event.place == "Bar Centrale"


def test_editing_an_approved_event_keeps_the_public_version(
    client: Client,
    make_event: Callable[..., Event],
    make_staff: Callable[..., User],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    make_staff()
    event = make_event(status=Event.Status.APPROVED, title="Pizza night")
    client.force_login(event.organizer)

    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            reverse("event_edit", args=[event.pk]),
            form_data(event, title="Pasta night"),
        )

    event.refresh_from_db()
    assert event.title == "Pizza night"
    assert event.status == Event.Status.APPROVED
    assert EventChange.objects.get(event=event).title == "Pasta night"
    assert len(mailoutbox) == 1


def test_editing_again_replaces_the_changes_and_prefills_the_form(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    client.force_login(event.organizer)
    url = reverse("event_edit", args=[event.pk])

    client.post(url, form_data(event, title="Pasta night"))
    page = client.get(url)
    client.post(url, form_data(event, title="Pasta and wine"))

    assert b'value="Pasta night"' in page.content
    assert EventChange.objects.get(event=event).title == "Pasta and wine"


def test_a_photo_that_is_not_uploaded_again_keeps_its_file(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    client.force_login(event.organizer)

    client.post(reverse("event_edit", args=[event.pk]), form_data(event))

    assert EventChange.objects.get(event=event).photo.name == event.photo.name


def test_a_new_photo_goes_into_the_changes(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    public_photo = event.photo.name
    client.force_login(event.organizer)
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), "teal").save(buffer, "JPEG")
    photo = SimpleUploadedFile("new.jpg", buffer.getvalue(), "image/jpeg")

    client.post(reverse("event_edit", args=[event.pk]), form_data(event, photo=photo))

    change = EventChange.objects.get(event=event)
    assert change.photo.name != public_photo
    assert change.photo.storage.exists(change.photo.name)
    event.refresh_from_db()
    assert event.photo.name == public_photo


def test_max_people_cannot_go_below_the_people_going(
    client: Client,
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    event = make_event(status=Event.Status.APPROVED, max_people=5)
    make_participation(event=event)
    make_participation(event=event)
    client.force_login(event.organizer)

    response = client.post(
        reverse("event_edit", args=[event.pk]), form_data(event, max_people=2)
    )

    assert response.status_code == 200
    assert b"at least 3 spots" in response.content
    assert not EventChange.objects.exists()


def test_a_refused_edit_does_not_touch_the_event(
    client: Client,
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    # Bound to `event` itself, the form would write "Pasta night" onto it in
    # is_valid(), even though max_people refuses the edit (worked example 09).
    event = make_event(status=Event.Status.APPROVED, title="Pizza night", max_people=5)
    make_participation(event=event)
    make_participation(event=event)
    client.force_login(event.organizer)

    response = client.post(
        reverse("event_edit", args=[event.pk]),
        form_data(event, title="Pasta night", max_people=2),
    )

    assert response.status_code == 200
    # The event the page shows (its heading, its status text) is still the public one.
    assert response.context["event"].title == "Pizza night"


def test_only_the_organizer_may_edit(
    client: Client,
    make_event: Callable[..., Event],
    make_student: Callable[..., User],
    make_staff: Callable[..., User],
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    url = reverse("event_edit", args=[event.pk])

    client.force_login(make_student())
    assert client.get(url).status_code == 404
    client.force_login(make_staff())
    assert client.get(url).status_code == 404


@pytest.mark.parametrize(
    ("status", "days"),
    [(Event.Status.APPROVED, -1), (Event.Status.CANCELLED, 7)],
    ids=["started", "cancelled"],
)
def test_started_or_cancelled_events_cannot_be_edited(
    client: Client, make_event: Callable[..., Event], status: str, days: int
) -> None:
    event = make_event(status=status, starts_at=timezone.now() + timedelta(days=days))
    client.force_login(event.organizer)

    assert client.get(reverse("event_edit", args=[event.pk])).status_code == 404


def test_the_list_and_the_page_say_changes_pending(
    client: Client, make_event: Callable[..., Event], make_student: Callable[..., User]
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    client.force_login(event.organizer)
    client.post(reverse("event_edit", args=[event.pk]), form_data(event, title="New"))
    client.force_login(make_student())

    assert b"Changes pending" in client.get(reverse("home")).content
    assert (
        b"Changes pending"
        in client.get(reverse("event_detail", args=[event.pk])).content
    )
