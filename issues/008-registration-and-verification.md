# Register with the QR code and verify the email

Status: todo · Opened: 2026-11-21 · Milestone: M1 · Depends on: 002, 005, 006, 007, 009

## Why

Issue 007 put a QR code on the projector, and the page it opens says "the form comes in 008".
This is that form. Students register themselves on their phone, with their whole profile in one
go: name, email, password, photo, nationality, age and gender (SPEC.md §2 #10). Nobody has half a
profile, so later pages never have to ask "is your profile complete?".

An email address typed on a phone can be wrong, or can be someone else's. So a new account is
**inactive** until its owner clicks a link we email to them (§2 #9). Django already knows how to
make such links: it does it for password resets. We reuse that.

After this issue, AMFI Meetups has real users. 009 is a dependency because the "already
registered" error links to the password reset page that 009 adds.

## What you'll build

- The registration form on `/register/<code>/`: full name, email, password (twice), photo (the
  front camera opens on phones), nationality, age and gender. All required.
- Sending it checks the window again, creates an inactive user and emails a verification link.
  The next page says "Check your email".
- `/verify/<uidb64>/<token>/` activates the account, logs the student in and welcomes them. A link
  that was used, is too old or is broken says so and offers to send a new one.
- `/accounts/resend-verification/` asks for an email and always gives the same answer, so it
  doesn't tell strangers who is registered. The login page links to it.
- An email that is already registered is a form error with links to log in, reset the password or
  resend the verification email, "or ask the AMFI staff".

Not in this issue: editing the profile, password change and reset (009).

## Before you start

Read:
- SPEC.md §2 #5, #9, #10, #12, #13, #14, #36; §6.1 (all of it); §6.6 (the first row); §11
  "Emails in tests".
- AGENTS.md: Layers (services), Views and templates, Django (`transaction.on_commit`).
- `docs/testing/emails.md`.
- `docs/learn/hypermedia-and-forms.md` (the form view pattern, Post/Redirect/Get) and
  `docs/learn/transactions-and-race-conditions.md` (why a service, and `on_commit`).
- [Django: `BaseUserCreationForm`](https://docs.djangoproject.com/en/6.1/topics/auth/default/#django.contrib.auth.forms.BaseUserCreationForm)
  and [Custom users and the built-in auth forms](https://docs.djangoproject.com/en/6.1/topics/auth/customizing/#custom-users-and-the-built-in-auth-forms).
- [Django: Performing actions after commit](https://docs.djangoproject.com/en/6.1/topics/db/transactions/#performing-actions-after-commit).

Words you'll meet:
- **Inactive user**: `is_active=False`. Django's login refuses them.
- **Token**: a string that proves a link came from us. Django's `default_token_generator` (the
  one password reset uses) signs it with `SECRET_KEY`, so nobody can make one up, and it stops
  working after a while.
- **`uidb64`**: the user's id, encoded in base64 so it fits in a URL.
- **`transaction.on_commit`**: "run this once the database has really saved the data". If saving
  fails, the email is never sent.
- **Service**: a function in `accounts/services.py` where a rule lives, so views stay small and
  tests can check the rule directly (AGENTS.md, Layers).
- **User enumeration**: finding out who has an account by trying emails on a form. A form that
  always answers the same prevents it.

## Steps

### 1. The forms

Add to `accounts/forms.py` (new imports at the top):

```python
from typing import Any, override

from django import forms
from django.contrib.auth.forms import AuthenticationForm, BaseUserCreationForm
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.html import format_html

from accounts.models import User
from config.photos import PhotoField


class RegistrationForm(BaseUserCreationForm[User]):
    # On a phone, the photo field opens the front camera.
    photo = PhotoField(widget=forms.FileInput(attrs={"capture": "user"}))

    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ("full_name", "email", "photo", "nationality", "age", "gender")

    @override
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # The model allows them blank for staff; a student fills in every field.
        for name in ("nationality", "age", "gender"):
            self.fields[name].required = True

    def clean_email(self) -> str:
        email: str = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError(
                format_html(
                    "This email is already registered. "
                    '<a href="{}">Log in</a>, <a href="{}">reset your password</a> '
                    'or <a href="{}">resend the verification email</a>, '
                    "or ask the AMFI staff.",
                    reverse("login"),
                    reverse("password_reset"),
                    reverse("resend_verification"),
                ),
                code="registered",
            )
        return email


class ResendVerificationForm(forms.Form):
    email = forms.EmailField()

    def clean_email(self) -> str:
        email: str = self.cleaned_data["email"]
        return email.lower()
```

Why it looks like this:

- **`BaseUserCreationForm`** is Django's documented base for sign-up forms. It brings the two
  password fields, the "didn't match" check, every validator in `AUTH_PASSWORD_VALIDATORS` (too
  short, too common, only numbers, too similar to the email), and a `save()` that hashes the
  password. Not `UserCreationForm`: that one adds a check on a `username` field we don't have.
- **`class Meta(BaseUserCreationForm.Meta)`** inherits the parent's `Meta`, as in the Django docs'
  example. pyrefly requires it too: a plain `class Meta:` is a `bad-override`.
- **The `required = True` loop**: the model allows these fields blank, because admins have no
  profile. The database constraint from issue 002 would still refuse a student without them, but
  the form should say "This field is required." next to the field first. (009's `ProfileForm`
  has the same loop.)
- **`PhotoField`** (issue 006) refuses files over 10 MB, shrinks the photo and drops its EXIF
  data. The `capture="user"` attribute asks a phone for its front camera. You don't add
  `accept="image/*"`: Django's image fields add it themselves. `FileInput` instead of the default
  widget, because a new account has no photo to "clear".
- **`clean_email`** lowercases the email (§2 #36): phones capitalise the first letter. Then it
  refuses an email that is already registered, with the links from §6.1 point 7.
- **`format_html`** builds a piece of HTML safely: it escapes each `{}` argument and marks the
  result as safe, so the links show as links. The arguments here are our own URLs. Never put
  anything a user typed into the first string (the format).

- [ ] The forms are in `accounts/forms.py`.

### 2. The services

Create `accounts/services.py`:

```python
from datetime import datetime

from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from accounts.models import RegistrationWindow, User
from config.emails import send_email


def user_register(*, user: User, window: RegistrationWindow, now: datetime) -> None:
    if not window.is_open(now=now):
        raise ValidationError("Registration closed, ask the AMFI staff.")
    user.registration_window = window
    user.full_clean()
    user.save()
    transaction.on_commit(lambda: _send_verification_email(user))


def user_verify(*, uidb64: str, token: str) -> User:
    try:
        user = User.objects.get(
            pk=urlsafe_base64_decode(uidb64).decode(),
            is_active=False,
            deleted_at=None,
        )
    except ValueError, User.DoesNotExist:
        user = None
    if user is None or not default_token_generator.check_token(user, token):
        raise ValidationError("This link was already used, or it is too old.")
    user.is_active = True
    user.full_clean()
    user.save()
    return user


def verification_resend(*, email: str) -> None:
    user = User.objects.filter(email=email, is_active=False, deleted_at=None).first()
    if user is not None:
        transaction.on_commit(lambda: _send_verification_email(user))


def _send_verification_email(user: User) -> None:
    send_email(
        to=[user.email],
        template="accounts/emails/verification",
        context={
            "user": user,
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
    )
```

How it works:

- **`user_register` takes an unsaved user**: the view gets it from `form.save(commit=False)`,
  which fills in the fields and hashes the password without saving. The service checks the
  window *again*: the page was open when the student scanned the code, but the form may arrive
  twenty minutes later (§2 #11). The rule lives here, so a test can check it without a browser.
- **`is_active` is already `False`**: that's the model's default (issue 002).
- **How the token works.** We read it in Django 6.1's source
  ([`django/contrib/auth/tokens.py`](https://github.com/django/django/blob/stable/6.1.x/django/contrib/auth/tokens.py)).
  `make_token(user)` is a time stamp plus a hash of the user's id, password hash, `last_login`,
  email and that time stamp, signed with `SECRET_KEY`. `check_token` recomputes it: if any of
  those values changed, or more than
  [`PASSWORD_RESET_TIMEOUT`](https://docs.djangoproject.com/en/6.1/ref/settings/#std-setting-PASSWORD_RESET_TIMEOUT)
  (3 days by default) has passed, the token is refused. Nothing is stored in the database.
- **Why a link works only once.** `user_verify` only looks for *inactive* users, so after the
  first click the same link finds nobody. And the view logs the student in, which sets
  `last_login`: that alone changes the hash and kills the token.
- **A soft-deleted student is never activated** (§6.1 point 5): `deleted_at=None` in the query
  makes their link answer like an expired one.
- **A broken link**: `urlsafe_base64_decode` raises `ValueError` on garbage, and so does
  `get(pk="abc")`. Both mean "this link doesn't work", like a wrong token.
- **`except ValueError, User.DoesNotExist:`** without parentheses is new in Python 3.14
  ([PEP 758](https://peps.python.org/pep-0758/)); `ruff format` writes it this way. It catches
  both exceptions, like `except (ValueError, User.DoesNotExist):`.
- **`verification_resend`** sends a link only to an inactive student who isn't deleted (§6.1
  point 6), and says nothing about what it did.
- **`_send_verification_email`** is shared by the two services. It starts with `_`: it is a helper
  of this module, not a service the views call.
- **`transaction.on_commit`**: the email goes out only once the user is really saved (AGENTS.md,
  Django). There is a single write here, so no `transaction.atomic` is needed.

The email itself: two templates in `accounts/templates/accounts/emails/`.
`verification_subject.txt`, one line:

```text
{% autoescape off %}Confirm your email for AMFI Meetups{% endautoescape %}
```

`verification.txt`:

```text
{% autoescape off %}Hello {{ user.full_name }},

Welcome to AMFI Meetups! Open this link to confirm your email and activate your
account:

{{ site_url }}{% url 'verify' uidb64=uid token=token %}

The link works once, for 3 days. If you didn't register, ignore this email.
{% endautoescape %}
```

`send_email` (issue 005) adds `site_url` to the context (SPEC.md §2 #35).

- **`{% autoescape off %}` in both files**: Django escapes HTML in every template, `.txt` files
  too, so in a plain-text email "O'Brien" would arrive as `O&#x27;Brien`. Plain text can't run
  scripts, so it is safe to turn escaping off here.
- **The subject is one line.** An email subject can't contain a line break: Django 6.1 refuses
  it with a `ValueError`.

- [ ] `accounts/services.py` and the two email templates exist.

### 3. The views and their URLs

Replace 007's `register` view, and add three more in `accounts/views.py`:

```python
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.forms import RegistrationForm, ResendVerificationForm
from accounts.models import RegistrationWindow
from accounts.services import user_register, user_verify, verification_resend


@login_not_required
def register(request: HttpRequest, code: str) -> HttpResponse:
    window = get_object_or_404(RegistrationWindow, code=code)
    if not window.is_open(now=timezone.now()):
        return render(request, "accounts/register_closed.html")
    if request.method == "POST":
        form = RegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                user_register(
                    user=form.save(commit=False), window=window, now=timezone.now()
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                return redirect("register_sent")
    else:
        form = RegistrationForm()
    return render(request, "accounts/register.html", {"form": form})


@login_not_required
def register_sent(request: HttpRequest) -> HttpResponse:
    return render(request, "accounts/register_sent.html")


@login_not_required
def verify(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    try:
        user = user_verify(uidb64=uidb64, token=token)
    except ValidationError:
        return render(request, "accounts/verify_failed.html")
    login(request, user)
    messages.success(request, "Your email is verified. Welcome to AMFI Meetups!")
    return redirect("home")


@login_not_required
def resend_verification(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = ResendVerificationForm(request.POST)
        if form.is_valid():
            verification_resend(email=form.cleaned_data["email"])
            messages.info(
                request,
                "If that email is waiting for verification, a new link is on its way.",
            )
            return redirect("login")
    else:
        form = ResendVerificationForm()
    return render(request, "accounts/resend_verification.html", {"form": form})
```

Keep 009's `student_detail` and `profile_edit`, and the imports they need.

- **The window is checked on every request**, GET and POST: a form sent after "Close now" gets
  the "Registration closed" page and creates nobody.
- **`request.FILES`**: uploaded files don't arrive in `request.POST`. Forget it and the photo is
  always "required".
- **`form.add_error(None, error)`** shows a service's `ValidationError` above the form. It only
  happens if the window closes in the second between the check above and the service.
- **Post/Redirect/Get**: after a successful POST, always redirect. Reloading "Check your email"
  then doesn't send the form again.
- **`login(request, user)`** logs the student in right away: they just proved the email is theirs.
- **The resend page redirects to the login page with the same message** whatever the email was.

The URLs, in `accounts/urls.py`:

```python
urlpatterns: list[URLPattern] = [
    # Before register/<code>/, or "sent" would be taken for a code.
    path("register/sent/", views.register_sent, name="register_sent"),
    path("register/<str:code>/", views.register, name="register"),
    path("verify/<str:uidb64>/<str:token>/", views.verify, name="verify"),
    path(
        "accounts/resend-verification/",
        views.resend_verification,
        name="resend_verification",
    ),
    # ... 009's students/ and profile/ paths
]
```

Django tries the patterns in order and takes the first match. `<str:code>` matches any word,
`sent` included, so `register/sent/` must come first.

- [ ] The four views are public (`@login_not_required`) and wired to their URLs.

### 4. The templates

In `accounts/templates/accounts/`. Replace 007's `register.html`:

```html
{% extends "base.html" %}

{% block title %}Register · AMFI Meetups{% endblock %}

{% block header %}{% endblock %}

{% block content %}
<main id="main">
  <h1>Welcome to AMFI Meetups</h1>
  <form method="post" enctype="multipart/form-data">
    {% csrf_token %}
    {{ form }}
    <button type="submit">Register</button>
  </form>
</main>
{% endblock %}
```

**`enctype="multipart/form-data"`** is what lets a form send a file. Without it the browser sends
only the file's *name*. `{{ form }}` prints every field with its label, its errors and its help
text (the password rules). Style it with your UI library (issue 003), or print the fields one by
one if you need more control.

Three small pages more, each with an empty `header` block like the login page:

- `register_sent.html`: "Check your email. We sent you a link: open it to activate your account."
  and a link to `{% url 'resend_verification' %}` for "Nothing after a few minutes?".
- `verify_failed.html`: "This link doesn't work. It was already used, or it is too old." with
  links to `{% url 'login' %}` and `{% url 'resend_verification' %}` (§6.1 point 5).
- `resend_verification.html`: the title "Resend the verification email", the form (only
  `{% csrf_token %}`, `{{ form }}` and a button, no `enctype`), and a link back to log in.

On the login page (`templates/registration/login.html`), under the button:

```html
<p><a href="{% url 'resend_verification' %}">Resend the verification email</a></p>
```

- [ ] Every page works in a private browser window, without logging in.

### 5. Try it end to end

`.env` uses the file-based email backend: every email is written to `var/mail/` and nothing is
sent. Then:

1. In the admin, open a registration window. Open its link in a private browser window.
2. Register with a made-up student (`student1@example.com`) and a small photo.
3. Open the newest file in `var/mail/`, copy the `/verify/...` link into the private window.
4. You land on the event list, logged in, with the welcome message.
5. Open the same link again (log out first): "This link doesn't work".

Then do it on your phone, as in issue 007 step 6: check that the photo field opens the camera.

- [ ] The whole flow works on a laptop and on a phone.

### 6. Tests

007's `test_register_page_is_public_while_the_window_is_open` looks for "Registration is open",
which is gone. Make it look for the form instead:

```python
    assert b'name="password1"' in response.content
```

Then `tests/accounts/test_registration.py`. The services first, then the pages through the test
client:

```python
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


def test_register_form_asks_for_the_camera_on_phones(
    client: Client, make_window: Callable[..., RegistrationWindow]
) -> None:
    window = make_window()

    response = client.get(reverse("register", args=(window.code,)))

    assert b'capture="user"' in response.content
    assert b'accept="image/*"' in response.content


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
```

Things to notice:
- **`django_capture_on_commit_callbacks(execute=True)`** runs the `on_commit` callbacks, which
  never run in a test otherwise (`docs/testing/emails.md`). Without it `mailoutbox` stays empty
  and you'll think the email is broken.
- **Photos saved by these tests land in a temporary folder**, not in your `var/media/`: issue
  006's autouse fixture `_media_root_in_tmp_path` in `tests/conftest.py` does it for every test.
- **`jpeg()`** makes a real, tiny image in memory, because `PhotoField` opens it with Pillow.
- Each rule of §6.1 has its test, including the forbidden cases: a closed window, a used link, a
  deleted student, a broken link, an email that is already registered.

- [ ] The tests pass.
- [ ] `scripts/check.sh` passes.

### 7. A note for the next developer

How the verification link works is hard to guess from the code. Write it down in a few lines in
`docs/accounts/email-verification.md` (the token is Django's password reset token, what makes it
single use, what makes it expire, why the resend page always says the same), and add it to
`docs/index.md` (AGENTS.md, Notetaking).

- [ ] The note exists and the index links to it.

## Done when

- [ ] A student registers on `/register/<code>/` with every profile field and a photo, and gets an
  email with a link; the account stays inactive until the link is clicked (tests).
- [ ] The window is checked again when the form is sent (test).
- [ ] The link activates the account and logs in, once; a used, broken or old link, or a deleted
  student's link, shows "This link doesn't work" with a way to get a new one (tests).
- [ ] An email that is already registered shows the error with its three links (test).
- [ ] The resend page answers the same for every email, and only emails inactive, not deleted
  students (tests). The login page links to it.
- [ ] On a phone, the photo field opens the camera.
- [ ] `scripts/check.sh` passes.
- [ ] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 008-registration-and-verification
```

Suggested commits (each one passes `scripts/check.sh`):
1. `Add the registration form`
2. `Add the registration and verification services`
3. `Register through the window's page and verify the email`
4. `Add the resend verification page`
5. `Add a note on email verification`
6. `Close 008 in the issue`

Open a pull request titled "Register with the QR code and verify the email". Show screenshots of
the form on a phone, of the "Check your email" page, and of the email from `var/mail/`. Ask the
reviewer to check that every page that must be public has `@login_not_required`, and nothing else.
`docs/workflow/git.md` has every step.

## Watch out

- **An unverified student who tries to log in sees Django's usual "Please enter a correct email
  and password".** Django's login backend refuses inactive users without saying why, so it doesn't
  reveal that the account exists. That's why the login page has the "Resend the verification
  email" link.
- **No `enctype="multipart/form-data"`, no photo.** The form then says the photo is required,
  even though you picked one.
- **`mailoutbox` is empty in a test?** You forgot `django_capture_on_commit_callbacks(execute=True)`.
- **The same token generator signs password reset links (009).** A verification link pasted into
  the password reset URL would let its owner set a password: harmless, it's the same inbox. The
  other way round doesn't work: reset emails go only to active users, and `user_verify` only
  looks for inactive ones.
- **Changing `SECRET_KEY` on the server kills every link already sent** (verification and password
  reset). Students then ask for a new one.
- **`capture="user"` opens the camera directly on most phones, without the photo gallery.**
  Desktop browsers ignore it. That's what SPEC.md §2 #10 asks for: a fresh photo of the person in
  the room.
- **Never print the token** in a message, a log or the page: whoever has it can activate the
  account.

## Worked example

- [05, one registration, request by request](../docs/examples/05-a-request-step-by-step.md): after
  step 4, watch the POST, the 302 and the GET in the Network tab and with `curl -i`, then get the
  403 without `{% csrf_token %}`.

## Further reading

- [Django: `BaseUserCreationForm`](https://docs.djangoproject.com/en/6.1/topics/auth/default/#django.contrib.auth.forms.BaseUserCreationForm)
  and [Custom users and the built-in auth forms](https://docs.djangoproject.com/en/6.1/topics/auth/customizing/#custom-users-and-the-built-in-auth-forms).
- [Django: `login()`](https://docs.djangoproject.com/en/6.1/topics/auth/default/#django.contrib.auth.login).
- [Django: `format_html`](https://docs.djangoproject.com/en/6.1/ref/utils/#django.utils.html.format_html)
  and [`urlsafe_base64_encode`](https://docs.djangoproject.com/en/6.1/ref/utils/#django.utils.http.urlsafe_base64_encode).
- [Django: Binding uploaded files to a form](https://docs.djangoproject.com/en/6.1/ref/forms/api/#binding-uploaded-files-to-a-form).
- [Django's token generator, the source](https://github.com/django/django/blob/stable/6.1.x/django/contrib/auth/tokens.py):
  about 100 lines, worth reading.
- [OWASP: Authentication and error messages](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages):
  why the resend page and the login page don't say whether an account exists.
- [MDN: the `capture` attribute](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/capture).
- [Post/Redirect/Get](https://en.wikipedia.org/wiki/Post/Redirect/Get) on Wikipedia.
- [Django: Working with forms](https://docs.djangoproject.com/en/6.1/topics/forms/): bound and
  unbound forms, `is_valid()`, and showing errors, the pattern of the registration view.
- [MDN: Django tutorial part 9, Working with forms](https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Server-side/Django/Forms):
  the same flow with a diagram. (Its later sections use class-based views; we don't.)
- [Django: Password validation](https://docs.djangoproject.com/en/6.1/topics/auth/passwords/#password-validation):
  the rules in `AUTH_PASSWORD_VALIDATORS` that the two password fields check.
- [MDN: Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies): how
  the browser stays logged in after the verify view calls `login()`.
