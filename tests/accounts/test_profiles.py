import io
import re
from collections.abc import Callable

import pytest
from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import User

pytestmark = pytest.mark.django_db

PROFILE = {
    "full_name": "Student New",
    "nationality": "PT",
    "age": 30,
    "gender": "other",
}


def jpeg(name: str = "me.jpg") -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), "teal").save(buffer, "JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def test_logged_in_users_see_a_students_profile(
    client: Client, make_student: Callable[..., User]
) -> None:
    student = make_student(full_name="Student Two", age=24, nationality="FR")
    client.force_login(make_student())

    response = client.get(reverse("student_detail", args=(student.pk,)))

    assert response.status_code == 200
    assert b"Student Two" in response.content
    assert b"24" in response.content
    assert b"France" in response.content


@pytest.mark.parametrize(
    "overrides",
    [{"is_active": False}, {"is_active": False, "deleted_at": timezone.now()}],
    ids=["not verified", "deleted"],
)
def test_inactive_and_deleted_students_have_no_profile(
    client: Client, make_student: Callable[..., User], overrides: dict[str, object]
) -> None:
    student = make_student(**overrides)
    client.force_login(make_student())

    response = client.get(reverse("student_detail", args=(student.pk,)))

    assert response.status_code == 404


def test_staff_have_no_profile(
    client: Client,
    make_student: Callable[..., User],
    make_staff: Callable[..., User],
) -> None:
    staff = make_staff()
    client.force_login(make_student())

    response = client.get(reverse("student_detail", args=(staff.pk,)))

    assert response.status_code == 404


def test_student_edits_their_profile_and_keeps_the_photo(
    client: Client, make_student: Callable[..., User]
) -> None:
    student = make_student()
    client.force_login(student)

    response = client.post(reverse("profile_edit"), PROFILE)

    student.refresh_from_db()
    assert response.status_code == 302
    assert response["Location"] == reverse("student_detail", args=(student.pk,))
    assert student.full_name == "Student New"
    assert student.age == 30
    assert student.photo.name == "photos/users/student.jpg"


def test_student_replaces_their_photo(
    client: Client, make_student: Callable[..., User]
) -> None:
    student = make_student()
    client.force_login(student)

    client.post(reverse("profile_edit"), {**PROFILE, "photo": jpeg()})

    student.refresh_from_db()
    assert student.photo.name.startswith("photos/users/")
    assert student.photo.name != "photos/users/student.jpg"


def test_profile_needs_every_field(
    client: Client, make_student: Callable[..., User]
) -> None:
    student = make_student()
    client.force_login(student)

    response = client.post(reverse("profile_edit"), {**PROFILE, "age": ""})

    student.refresh_from_db()
    assert response.status_code == 200
    assert b"This field is required." in response.content
    assert student.age == 22


def test_staff_have_no_profile_page_and_no_profile_link(
    client: Client, make_staff: Callable[..., User]
) -> None:
    client.force_login(make_staff())

    assert client.get(reverse("profile_edit")).status_code == 404
    assert reverse("profile_edit").encode() not in client.get("/").content


def test_students_see_the_profile_link(
    client: Client, make_student: Callable[..., User]
) -> None:
    client.force_login(make_student())

    assert reverse("profile_edit").encode() in client.get("/").content


def test_student_changes_their_password(
    client: Client, make_student: Callable[..., User]
) -> None:
    student = make_student()
    client.force_login(student)

    response = client.post(
        reverse("password_change"),
        {
            "old_password": "s3cret-pass",
            "new_password1": "a-new-long-pass",
            "new_password2": "a-new-long-pass",
        },
    )

    student.refresh_from_db()
    assert response.status_code == 302
    assert response["Location"] == reverse("password_change_done")
    assert student.check_password("a-new-long-pass")


def test_login_page_links_to_password_reset(client: Client) -> None:
    response = client.get(reverse("login"))

    assert reverse("password_reset").encode() in response.content


def test_password_reset_from_the_email_link(
    client: Client,
    mailoutbox: list[mail.EmailMessage],
    make_student: Callable[..., User],
) -> None:
    student = make_student(email="student1@example.com")

    response = client.post(reverse("password_reset"), {"email": "Student1@Example.com"})

    assert response["Location"] == reverse("password_reset_done")
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["student1@example.com"]
    body = str(mailoutbox[0].body)
    link = re.search(rf"{settings.SITE_URL}(/accounts/reset/\S+/)", body)
    assert link is not None
    # Django swaps the token in the URL for "set-password" and keeps it in the session.
    form_url = client.get(link.group(1))["Location"]
    response = client.post(
        form_url,
        {"new_password1": "a-new-long-pass", "new_password2": "a-new-long-pass"},
    )
    student.refresh_from_db()
    assert response["Location"] == reverse("password_reset_complete")
    assert student.check_password("a-new-long-pass")


@pytest.mark.parametrize("email", ["student1@example.com", "nobody@example.com"])
def test_password_reset_says_the_same_and_skips_inactive_or_unknown(
    client: Client,
    mailoutbox: list[mail.EmailMessage],
    make_student: Callable[..., User],
    email: str,
) -> None:
    make_student(email="student1@example.com", is_active=False)

    response = client.post(reverse("password_reset"), {"email": email})

    assert response["Location"] == reverse("password_reset_done")
    assert mailoutbox == []


def test_a_photo_uploaded_in_the_admin_is_shrunk(
    admin_client: Client, make_student: Callable[..., User]
) -> None:
    student = make_student(email="student1@example.com")
    buffer = io.BytesIO()
    Image.new("RGB", (2000, 1000), "teal").save(buffer, "JPEG")

    admin_client.post(
        f"/admin/accounts/user/{student.pk}/change/",
        {
            "email": "student1@example.com",
            **PROFILE,
            "is_active": "on",
            "photo": SimpleUploadedFile("big.jpg", buffer.getvalue()),
        },
    )

    student.refresh_from_db()
    with Image.open(student.photo) as image:
        assert image.size == (1024, 512)
