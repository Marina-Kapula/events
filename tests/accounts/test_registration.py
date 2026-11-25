import io
import re
from collections.abc import Callable
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode
from PIL import Image
from pytest_django import DjangoCaptureOnCommitCallbacks

from accounts.models import RegistrationWindow, User
from accounts.services import user_register, user_verify, verification_resend

pytestmark = pytest.mark.django_db

PASSWORD = "a-long-pass-123"


def jpeg() -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), "teal").save(buffer, "JPEG")
    return SimpleUploadedFile("me.jpg", buffer.getvalue(), content_type="image/jpeg")


def form_data(**overrides: object) -> dict[str, object]:
    return {
        "full_name": "Student New",
        "email": "new@example.com",
        "password1": PASSWORD,
        "password2": PASSWORD,
        "photo": jpeg(),
        "nationality": "PT",
        "age": "21",
        "gender": "other",
        **overrides,
    }


def link_in(email: mail.EmailMessage) -> str:
    match = re.search(rf"{settings.SITE_URL}(/verify/\S+/)", str(email.body))
    assert match is not None
    return match.group(1)


def verify_args(user: User) -> tuple[str, str]:
    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    return uidb64, default_token_generator.make_token(user)


def new_user() -> User:
    user = User(
        email="new@example.com",
        full_name="Student New",
        photo="photos/users/new.jpg",
        nationality="PT",
        age=21,
        gender=User.Gender.OTHER,
    )
    user.set_password(PASSWORD)
    return user


def test_user_register_creates_an_inactive_user_and_emails_a_link(
    make_window: Callable[..., RegistrationWindow],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    window = make_window()

    with django_capture_on_commit_callbacks(execute=True):
        user_register(user=new_user(), window=window, now=timezone.now())

    user = User.objects.get(email="new@example.com")
    assert not user.is_active
    assert user.registration_window == window
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["new@example.com"]
    assert link_in(mailoutbox[0]).startswith("/verify/")


def test_user_register_refuses_a_closed_window(
    make_window: Callable[..., RegistrationWindow],
) -> None:
    window = make_window(closed_at=timezone.now())

    with pytest.raises(ValidationError, match="Registration closed"):
        user_register(user=new_user(), window=window, now=timezone.now())

    assert not User.objects.filter(email="new@example.com").exists()


def test_user_verify_activates_once(make_student: Callable[..., User]) -> None:
    student = make_student(is_active=False)
    uidb64, token = verify_args(student)

    user = user_verify(uidb64=uidb64, token=token)

    assert user.is_active
    with pytest.raises(ValidationError):
        user_verify(uidb64=uidb64, token=token)


def test_user_verify_never_activates_a_deleted_student(
    make_student: Callable[..., User],
) -> None:
    student = make_student(is_active=False, deleted_at=timezone.now())
    uidb64, token = verify_args(student)

    with pytest.raises(ValidationError):
        user_verify(uidb64=uidb64, token=token)

    student.refresh_from_db()
    assert not student.is_active


@pytest.mark.parametrize("uidb64", ["!!!", "YWJj", "OTk5OTk5OTk5OTk5OTk5OTk5OTk5"])
def test_user_verify_refuses_a_broken_uid(uidb64: str) -> None:
    # "YWJj" is "abc"; the last one is a number too big for the database.
    with pytest.raises(ValidationError):
        user_verify(uidb64=uidb64, token="abc-123")


def test_verification_resend_only_to_inactive_not_deleted_students(
    make_student: Callable[..., User],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    make_student(email="waiting@example.com", is_active=False)
    make_student(email="active@example.com")
    make_student(email="gone@example.com", is_active=False, deleted_at=timezone.now())

    with django_capture_on_commit_callbacks(execute=True):
        for email in ("waiting", "active", "gone", "unknown"):
            verification_resend(email=f"{email}@example.com")

    assert [message.to for message in mailoutbox] == [["waiting@example.com"]]


def test_register_form_creates_the_account_and_says_check_your_email(
    client: Client,
    make_window: Callable[..., RegistrationWindow],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    window = make_window()
    url = reverse("register", args=(window.code,))

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(url, form_data(email="New@Example.com"))

    assert response.status_code == 302
    assert response["Location"] == reverse("register_sent")
    user = User.objects.get(email="new@example.com")
    assert not user.is_active
    assert user.photo.name.startswith("photos/users/")
    assert len(mailoutbox) == 1


def test_register_form_offers_the_camera_or_the_gallery(
    client: Client, make_window: Callable[..., RegistrationWindow]
) -> None:
    window = make_window()

    response = client.get(reverse("register", args=(window.code,)))

    # capture="user" would open only the camera on an iPhone, never the gallery.
    assert b"capture=" not in response.content
    assert b'accept="image/*"' in response.content
    assert b"data-photo-input" in response.content
    assert b'id="photo-editor"' in response.content


def test_register_keeps_the_photo_after_a_form_error(
    client: Client,
    make_window: Callable[..., RegistrationWindow],
    mailoutbox: list[mail.EmailMessage],
) -> None:
    url = reverse("register", args=(make_window().code,))

    response = client.post(url, form_data(password2="a-typo-123"))

    assert response.status_code == 200
    assert b"data:image/jpeg;base64," in response.content
    data = form_data()
    del data["photo"]
    response = client.post(url, data)
    assert response["Location"] == reverse("register_sent")
    assert User.objects.get(email="new@example.com").photo
    assert "register_photo" not in client.session


def test_register_without_a_photo_asks_for_one(
    client: Client, make_window: Callable[..., RegistrationWindow]
) -> None:
    data = form_data()
    del data["photo"]

    response = client.post(reverse("register", args=(make_window().code,)), data)

    assert response.status_code == 200
    assert response.context["form"].errors["photo"]
    assert not User.objects.filter(email="new@example.com").exists()


def test_a_wrong_qr_link_gets_a_friendly_page(client: Client) -> None:
    response = client.get("/register/not-a-code/")

    assert response.status_code == 404
    assert b"ask the AMFI staff for a new one" in response.content


def test_register_form_refuses_when_the_window_closed_meanwhile(
    client: Client, make_window: Callable[..., RegistrationWindow]
) -> None:
    window = make_window()
    url = reverse("register", args=(window.code,))
    assert client.get(url).status_code == 200
    window.expires_at = timezone.now() - timedelta(seconds=1)
    window.save()

    response = client.post(url, form_data())

    assert b"Registration closed, ask the AMFI staff" in response.content
    assert not User.objects.filter(email="new@example.com").exists()


def test_register_form_refuses_a_registered_email_with_links(
    client: Client,
    make_window: Callable[..., RegistrationWindow],
    make_student: Callable[..., User],
) -> None:
    make_student(email="student1@example.com")
    window = make_window()

    response = client.post(
        reverse("register", args=(window.code,)),
        form_data(email="Student1@example.com"),
    )

    assert response.status_code == 200
    assert b"This email is already registered." in response.content
    for name in ("login", "password_reset", "resend_verification"):
        assert f'href="{reverse(name)}"'.encode() in response.content


def test_register_form_checks_the_password(
    client: Client, make_window: Callable[..., RegistrationWindow]
) -> None:
    window = make_window()

    response = client.post(
        reverse("register", args=(window.code,)),
        form_data(password1="12345678", password2="12345678"),
    )

    assert response.status_code == 200
    assert b"This password is too common." in response.content


def test_verification_link_logs_in_once(
    client: Client,
    make_window: Callable[..., RegistrationWindow],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    window = make_window()
    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("register", args=(window.code,)), form_data())
    link = link_in(mailoutbox[0])

    response = client.get(link)

    assert response.status_code == 302
    assert response["Location"] == reverse("home")
    assert client.get(reverse("home")).status_code == 200
    client.logout()
    response = client.get(link)
    assert response.status_code == 200
    assert b"This link doesn" in response.content


def test_resend_page_always_answers_the_same(
    client: Client,
    make_student: Callable[..., User],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    make_student(email="waiting@example.com", is_active=False)
    url = reverse("resend_verification")

    with django_capture_on_commit_callbacks(execute=True):
        waiting = client.post(url, {"email": "Waiting@Example.com"}, follow=True)
        unknown = client.post(url, {"email": "nobody@example.com"}, follow=True)

    # The same page and message, so the form doesn't reveal who registered.
    assert waiting.redirect_chain == [("/accounts/login/", 302)]
    assert unknown.redirect_chain == waiting.redirect_chain
    for response in (waiting, unknown):
        assert b"a new link is on its way" in response.content
    assert [message.to for message in mailoutbox] == [["waiting@example.com"]]


def test_login_page_links_to_resend_verification(client: Client) -> None:
    response = client.get(reverse("login"))

    assert reverse("resend_verification").encode() in response.content
