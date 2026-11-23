import io
from collections.abc import Callable
from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone
from PIL import Image
from pytest_django import DjangoCaptureOnCommitCallbacks

from accounts.models import User
from events.models import Event

pytestmark = pytest.mark.django_db


def photo() -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "orange").save(buffer, "JPEG")
    return SimpleUploadedFile("pizza.jpg", buffer.getvalue(), "image/jpeg")


def form_data(**overrides: object) -> dict[str, object]:
    starts_at = timezone.localtime() + timedelta(days=7)
    return {
        "title": "Pizza night",
        "type": Event.Type.FOOD,
        "description": "Pizza, then a walk in the old town.",
        "photo": photo(),
        "city": "Avezzano",
        "place": "Piazza Risorgimento",
        "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
        "max_people": 8,
        "language": "English",
        **overrides,
    }


def test_a_student_sends_an_event_to_review(
    client: Client,
    make_student: Callable[..., User],
    make_staff: Callable[..., User],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    student = make_student()
    staff = make_staff()
    former_staff = make_staff()
    former_staff.is_active = False
    former_staff.save()
    client.force_login(student)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post("/events/new/", form_data(), follow=True)

    event = Event.objects.get()
    assert event.status == Event.Status.PENDING
    assert event.organizer == student
    assert response.redirect_chain == [("/", 302)]
    assert b"Sent to AMFI for review" in response.content
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [staff.email]
    assert f"/admin/events/event/{event.pk}/change/" in mailoutbox[0].body


def test_an_event_must_start_in_the_future(
    client: Client, make_student: Callable[..., User]
) -> None:
    client.force_login(make_student())
    yesterday = timezone.localtime() - timedelta(days=1)

    response = client.post(
        "/events/new/", form_data(starts_at=yesterday.strftime("%Y-%m-%dT%H:%M"))
    )

    assert response.status_code == 200
    assert b"Pick a date and time in the future." in response.content
    assert not Event.objects.exists()


@pytest.mark.parametrize("max_people", [1, 101])
def test_max_people_is_between_2_and_100(
    client: Client, make_student: Callable[..., User], max_people: int
) -> None:
    client.force_login(make_student())

    response = client.post("/events/new/", form_data(max_people=max_people))

    assert response.status_code == 200
    assert not Event.objects.exists()


def test_staff_get_a_404(client: Client, make_staff: Callable[..., User]) -> None:
    client.force_login(make_staff())

    assert client.get("/events/new/").status_code == 404


def test_an_event_added_in_the_admin_is_approved(
    admin_client: Client, admin_user: User
) -> None:
    # The admin shows the date and the time as two inputs.
    starts_at = timezone.localtime() + timedelta(days=7)
    data = form_data(
        starts_at_0=starts_at.strftime("%Y-%m-%d"),
        starts_at_1=starts_at.strftime("%H:%M"),
        review_note="",
    )

    response = admin_client.post("/admin/events/event/add/", data)

    assert response.status_code == 302
    event = Event.objects.get()
    assert event.status == Event.Status.APPROVED
    assert event.organizer == admin_user
