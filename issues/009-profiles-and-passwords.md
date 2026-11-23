# Profiles, profile editing and passwords

Status: done · Opened: 2026-11-21 · Milestone: M1 · Depends on: 002, 005, 006

## Why

Meeting strangers is easier when you know a little about them. An event's page will list the
people going, each with a link to their profile (issue 013), so every logged-in user can see every
active student's profile: photo, name, age, nationality and gender (SPEC.md §2 #31). Students
change their own profile when something changes, and they need to change a password, or get a new
one when they forget it.

Passwords are the part you should *not* write yourself. Django ships the whole flow, tested by
thousands of sites: change, "forgot your password?", the email with a one-time link, choosing a
new one. We only give it URLs and templates.

## What you'll build

- `/students/<id>/`: a student's profile, for every logged-in user. Staff, unverified and deleted
  students have no profile: 404.
- `/profile/`: a student edits their own profile (everything from registration except email and
  password). A photo that isn't re-uploaded stays. Staff get a 404 (§6.9).
- A "Profile" link in the navigation, hidden for staff.
- Photos uploaded in the admin's Users page go through the same `PhotoField` (SPEC.md §6.8).
- Password change at `/accounts/password_change/`, linked from the profile page.
- Password reset: "Forgot your password?" on the login page → an email with a link → choose a new
  password → log in.

Not in this issue: registration (008), soft delete (017).

## Before you start

Read:
- SPEC.md §2 #12, #13, #14, #31, #35; §5 (`User`); §6.6 (the last row); §6.8; §6.9; §7 (the rows for
  `/students/<id>/`, `/profile/` and Django's auth views).
- AGENTS.md: Layers (a plain one-model edit is a `ModelForm` and `form.save()`), Views and
  templates (404 for the forbidden case, Post/Redirect/Get).
- `docs/learn/hypermedia-and-forms.md` and `docs/learn/how-a-django-request-works.md`, if the
  GET/POST view pattern, redirects or sessions are new to you.
- [Django: Using the views](https://docs.djangoproject.com/en/6.1/topics/auth/default/#using-the-views)
  and [All authentication views](https://docs.djangoproject.com/en/6.1/topics/auth/default/#all-authentication-views).
- [Django: The `save()` method of a ModelForm](https://docs.djangoproject.com/en/6.1/topics/forms/modelforms/#the-save-method).

Words you'll meet:
- **Auth views**: Django's ready-made views for login, logout, password change and password reset.
  You give them templates; they do the rest.
- **`instance=`**: a `ModelForm` built with an existing row edits that row instead of creating a
  new one.
- **`get_object_or_404`**: fetch one row, or answer 404 if it doesn't exist (or isn't allowed).
- **Password reset token**: the one-time, time-limited part of the reset link. Django signs it with
  `SECRET_KEY`; nothing is stored.
- **`multipart/form-data`**: the form encoding that can carry files.

## Steps

### 1. A student's profile page

`accounts/views.py`:

```python
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from accounts.models import User


def student_detail(request: HttpRequest, pk: int) -> HttpResponse:
    student = get_object_or_404(
        User, pk=pk, is_active=True, is_staff=False, deleted_at=None
    )
    return render(request, "accounts/student_detail.html", {"student": student})
```

The filters say who has a profile:
- **`is_active=True`**: a student who hasn't verified their email yet (008) is inactive, and so is
  a soft-deleted one (017).
- **`deleted_at=None`**: a deleted student stays hidden even if an admin ticks "active" by
  mistake (§6.7: "Their profile page is a 404").
- **`is_staff=False`**: admins have no student profile (§6.9).

No `@login_not_required`: `LoginRequiredMiddleware` keeps the page for logged-in users.

`accounts/urls.py` is created by issue 007. If you get here first, create it as 007 step 5 shows
and include it in `config/urls.py`. Add:

```python
    path("students/<int:pk>/", views.student_detail, name="student_detail"),
    path("profile/", views.profile_edit, name="profile_edit"),
```

The template, `accounts/templates/accounts/student_detail.html`:

```html
{% extends "base.html" %}

{% block title %}{{ student.full_name }} · AMFI Meetups{% endblock %}

{% block content %}
<main id="main">
  <img src="{{ student.photo.url }}" alt="" width="256" height="256">
  <h1>{{ student.full_name }}</h1>
  <dl>
    <dt>Age</dt><dd>{{ student.age }}</dd>
    <dt>Nationality</dt><dd>{{ student.nationality.name }}</dd>
    <dt>Gender</dt><dd>{{ student.get_gender_display }}</dd>
  </dl>
  {% if student == user %}
    <p><a href="{% url 'profile_edit' %}">Edit your profile</a></p>
  {% endif %}
</main>
{% endblock %}
```

- `student.photo.url` is `/media/photos/users/…`, served by issue 006's `media` view to
  logged-in users only.
- `alt=""`: the photo is decoration next to the name, so screen readers skip it.
- `get_gender_display` prints "Female" instead of the stored `female`. Django adds it for every
  field with `choices`.
- `{{ student.nationality.name }}` comes from django-countries ("Portugal" for `PT`).

Style it with your UI library (issue 003): a card with the photo is a good start.

- [x] A logged-in student sees another student's profile; a staff user's id gives a 404.

### 2. Edit your own profile

Editing your own profile has no rule and no side effect beyond its own fields, so AGENTS.md says:
a `ModelForm`, and the view calls `form.save()`. No service.

`accounts/forms.py` (new imports at the top):

```python
from typing import Any, override

from django import forms

from accounts.models import User
from config.photos import PhotoField


class ProfileForm(forms.ModelForm[User]):
    photo = PhotoField()

    class Meta:
        model = User
        fields = ("full_name", "photo", "nationality", "age", "gender")

    @override
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # The model allows them blank for staff; a student fills in every field.
        for name in ("nationality", "age", "gender"):
            self.fields[name].required = True
```

- **No `email`, no password.** The email is the login: a typo would lock the student out, so the
  AMFI staff change it in the admin. The password has its own page (step 5).
- **`photo = PhotoField()`** (issue 006): the same checks as at registration, shrinking and EXIF
  removal. It is required, so there is no "clear" checkbox. When the student doesn't pick a new
  file, Django keeps the current one: a file field's `clean()` returns the existing file when
  nothing new was uploaded.
- **The `required = True` loop**: the model allows these fields blank because admins have no
  profile; a student must keep them filled. (008's `RegistrationForm` has the same loop.)

The view, in `accounts/views.py`:

```python
from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from accounts.forms import ProfileForm


def profile_edit(request: HttpRequest) -> HttpResponse:
    user = request.user
    if not isinstance(user, User) or user.is_staff:
        raise Http404
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile is saved.")
            return redirect("student_detail", pk=user.pk)
    else:
        form = ProfileForm(instance=user)
    return render(request, "accounts/profile_edit.html", {"form": form})
```

- **`isinstance(user, User)`**: `request.user` is typed as "a user, or `AnonymousUser`".
  `LoginRequiredMiddleware` already sent anonymous visitors to the login page; the check makes
  pyrefly sure of it.
- **Staff get a 404**, not a 403 (AGENTS.md: everyone else gets a 404), and the link is hidden
  for them (step 4).
- **`instance=user`**: the form edits the logged-in student. There is no id in the URL, so a
  student can't even try to edit someone else.
- **After saving**, the student lands on their own profile page and sees it as others do.

`accounts/templates/accounts/profile_edit.html`:

```html
{% extends "base.html" %}

{% block title %}Your profile · AMFI Meetups{% endblock %}

{% block content %}
<main id="main">
  <h1>Your profile</h1>
  <form method="post" enctype="multipart/form-data">
    {% csrf_token %}
    {{ form }}
    <button type="submit">Save</button>
  </form>
  <p><a href="{% url 'password_change' %}">Change your password</a></p>
</main>
{% endblock %}
```

`enctype="multipart/form-data"` is what lets the form send the photo.

- [x] A student edits their profile, with and without a new photo.

### 3. Photos uploaded in the admin

The AMFI staff can change a student's photo on the Users page in the admin. That upload must be
checked, shrunk and stripped of EXIF too (SPEC.md §6.8), but the admin builds its own form with a
plain `ImageField`. One line in `UserAdmin` (`accounts/admin.py`) swaps the field class for every
image field of the model:

```python
from typing import ClassVar, override

from django.db import models

from config.photos import PhotoField


@admin.register(User)
class UserAdmin(admin.ModelAdmin[User]):
    # ... list_display, fields and the rest as before ...
    readonly_fields = ("registration_window", "date_joined", "deleted_at")
    # Photos uploaded here are checked and shrunk like the students' own (SPEC.md §6.8).
    formfield_overrides: ClassVar = {models.ImageField: {"form_class": PhotoField}}
```

- **`formfield_overrides`** maps a model field class to options for its form field. Django merges
  it with the admin's own defaults, so the admin's file widget stays and only the field class
  changes.
- **`ClassVar`**: the attribute belongs to the class, not to each object; ruff wants mutable class
  attributes marked so, and pyrefly accepts it.
- In the admin the photo is optional (the model's `blank=True`, for staff). A student's photo
  can't really be removed there: the database constraint from issue 002 refuses it.

- [x] A big photo uploaded in the admin is stored at most 1024 px wide (test in step 7).

### 4. The Profile link

In `templates/base.html`, next to "Events" (and in the bottom navigation for phones, if issue 003
added one):

```html
{% if not user.is_staff %}
<li><a href="{% url 'profile_edit' %}"{% if request.resolver_match.url_name == 'profile_edit' %} aria-current="page"{% endif %}>Profile</a></li>
{% endif %}
```

`aria-current="page"` tells screen readers (and your CSS) which page you're on, like the Events
link does.

- [x] Students see "Profile"; staff don't.

### 5. Password change and reset: Django's views

Django has six views for passwords, in `django.contrib.auth.views`:

| URL | View | Template |
|---|---|---|
| `accounts/password_change/` | `PasswordChangeView` | `registration/password_change_form.html` |
| `accounts/password_change/done/` | `PasswordChangeDoneView` | `registration/password_change_done.html` |
| `accounts/password_reset/` | `PasswordResetView` | `registration/password_reset_form.html` (+ the email's two templates) |
| `accounts/password_reset/done/` | `PasswordResetDoneView` | `registration/password_reset_done.html` |
| `accounts/reset/<uidb64>/<token>/` | `PasswordResetConfirmView` | `registration/password_reset_confirm.html` |
| `accounts/reset/done/` | `PasswordResetCompleteView` | `registration/password_reset_complete.html` |

**Which ones are public?** We read Django 6.1's source (`django/contrib/auth/views.py`) instead of
guessing. `LoginView` and the four *reset* views are already decorated with `login_not_required`,
so `LoginRequiredMiddleware` lets anonymous visitors in: you don't mark anything. The two *change*
views use `login_required`. (`LogoutView` is *not* public by default: that's why issue 002 wraps
it in `login_not_required`.)

Add the six paths to `config/urls.py`, after login and logout:

```python
from django.conf import settings

    path(
        "accounts/password_change/",
        auth_views.PasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "accounts/password_change/done/",
        auth_views.PasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    path(
        "accounts/password_reset/",
        auth_views.PasswordResetView.as_view(
            extra_email_context={"site_url": settings.SITE_URL}
        ),
        name="password_reset",
    ),
    path(
        "accounts/password_reset/done/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "accounts/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "accounts/reset/done/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
```

- **Why not `include("django.contrib.auth.urls")`?** It would add these six *and* a second login
  and logout, next to the ones issue 002 set up with our options. Six explicit paths are easier to
  read, and they let us pass an option to the reset view.
- **`extra_email_context={"site_url": settings.SITE_URL}`**: Django's reset email builds its link
  from the request's host. Our rule is that links in emails start with `SITE_URL` (SPEC.md §2
  #35), like every other email of the app, so we hand it to the email template.
- **The names are Django's own** (`password_reset_done`, …): the views redirect to each other by
  these names, so keep them exactly.

**Who gets a reset email?** Django's `PasswordResetForm` looks for *active* users with that email,
ignoring upper and lower case. An unverified student (008) gets nothing: they need "Resend the
verification email" instead. The page after the form says the same in every case, so nobody can
use it to find out who is registered.

- [x] The six URLs resolve.

### 6. The templates

They go in `templates/registration/`, next to `login.html`. Django looks in `templates/` before
the apps' folders. Without your files it would find the *admin's* templates with the same names,
and your students would land on a page that looks like the admin.

The email first. Despite its name, `password_reset_email.html` is the **plain-text** body:

```text
{% autoescape off %}Hello {{ user.full_name }},

Someone asked to reset the password of your AMFI Meetups account. To choose a new
password, open this link:

{{ site_url }}{% url 'password_reset_confirm' uidb64=uid token=token %}

If it wasn't you, ignore this email: your password stays the same.
{% endautoescape %}
```

- `{% autoescape off %}`: without it, "O'Brien" would arrive as `O&#x27;Brien` (Django escapes
  HTML in every template; plain text doesn't need it).
- Django gives the template `user`, `uid`, `token`, `email`, `protocol` and `domain`; `site_url`
  is ours.

`password_reset_subject.txt` is one line, with escaping off for the same reason:

```text
{% autoescape off %}Choose a new password for AMFI Meetups{% endautoescape %}
```

An email subject can't contain a line break; Django joins the lines of this template into one.

`password_reset_confirm.html` has two cases, because the link may be used or too old:

```html
{% extends "base.html" %}

{% block title %}Choose a new password · AMFI Meetups{% endblock %}

{% block header %}{% endblock %}

{% block content %}
<main id="main">
  {% if validlink %}
    <h1>Choose a new password</h1>
    <form method="post">
      {% csrf_token %}
      {{ form }}
      <button type="submit">Save the password</button>
    </form>
  {% else %}
    <h1>This link doesn't work</h1>
    <p>It was already used, or it is too old.
      <a href="{% url 'password_reset' %}">Ask for a new one</a>.</p>
  {% endif %}
</main>
{% endblock %}
```

The other five are short pages. All extend `base.html`; the four reset pages have an empty
`header` block (the visitor isn't logged in), the two change pages keep the navigation:

- `password_reset_form.html`: "Forgot your password?", one sentence, the form with
  `{% csrf_token %}`, `{{ form }}` and a "Send the link" button, and a link back to log in.
- `password_reset_done.html`: "Check your email. If an account uses that address, we've sent it a
  link to choose a new password." Same text for everyone.
- `password_reset_complete.html`: "Password saved", and a link to `{% url 'login' %}`.
- `password_change_form.html`: the form (old password, new password twice) and a button.
- `password_change_done.html`: "Password changed", and a link back to the events.

On the login page, under the button:

```html
<p><a href="{% url 'password_reset' %}">Forgot your password?</a></p>
```

Try the whole reset by hand: `.env` writes emails to `var/mail/` instead of sending them; open the
newest file and paste the link into your browser.

- [x] Every page uses your templates, not the admin's.
- [x] A password reset works end to end on your laptop.

### 7. Tests

`tests/accounts/test_profiles.py`:

```python
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
```

Things to notice:
- **No `django_capture_on_commit_callbacks` here.** Django's reset view sends its email right
  away, not in `on_commit`, so `mailoutbox` fills up by itself.
- **The reset test follows the link like a browser.** Opening the link redirects to
  `/accounts/reset/<uidb64>/set-password/`: Django moves the token into the session, so it can't
  leak to another site through the `Referer` header. The test posts the new password there.
- **`jpeg()`** makes a real tiny image, because `PhotoField` opens it with Pillow.
- **Uploads go to a temporary folder**, not to your `var/media/`: issue 006's autouse fixture
  `_media_root_in_tmp_path` does it for every test.
- **The admin test posts the whole change form**, like the browser does: every field of
  `UserAdmin.fields` that isn't read-only. A checkbox that is off is simply left out.

- [x] The tests pass.
- [x] `scripts/check.sh` passes.

## Done when

- [x] `/students/<id>/` shows an active student's profile to logged-in users; staff, unverified and
  deleted students are a 404 (tests).
- [x] `/profile/` edits the student's own profile and keeps the photo unless a new one is uploaded;
  staff get a 404 (tests).
- [x] "Profile" is in the navigation for students only (tests).
- [x] A photo uploaded in the admin is shrunk like the students' own (test).
- [x] Password change works from the profile page (test).
- [x] "Forgot your password?" on the login page leads to an email whose link starts with
  `SITE_URL` and sets a new password; inactive and unknown emails get nothing, and the same page
  (tests).
- [x] Every password page uses your templates.
- [x] `scripts/check.sh` passes.
- [x] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 009-profiles-and-passwords
```

Suggested commits (each one passes `scripts/check.sh`):
1. `Add the student profile page`
2. `Let students edit their profile`
3. `Check and shrink photos uploaded in the admin`
4. `Add the Profile link to the navigation`
5. `Add password change and reset pages`
6. `Close 009 in the issue`

Open a pull request titled "Profiles, profile editing and passwords". Show screenshots of a profile
page, of the edit form, and of the reset email from `var/mail/`. Ask the reviewer to try the
forbidden cases: a staff id in `/students/<id>/`, and `/profile/` as an admin.
`docs/workflow/git.md` has every step.

## Watch out

- **No `enctype="multipart/form-data"`, no new photo**: the browser sends only the file's name,
  and the old photo silently stays.
- **The reset email template ends in `.html` but is plain text.** It's Django's historical name.
  Keep `{% autoescape off %}` in it.
- **The reset email isn't sent through our `send_email`.** Django's form sends it itself, from
  `DEFAULT_FROM_EMAIL` (issue 005). In production that address must be verified in Brevo, or the
  email never arrives.
- **`settings.SITE_URL` in `config/urls.py` is read once, when the server starts.** That's true of
  every setting: after changing `DJANGO_SITE_URL`, restart (on Dokku, `config:set` restarts the
  app for you).
- **Don't add `email` to `ProfileForm`.** A typo there locks the student out of their account.
- **Staff get a 404, not a 403**, on `/profile/`: the page doesn't exist for them (AGENTS.md).

## Further reading

- [Django: Using the views](https://docs.djangoproject.com/en/6.1/topics/auth/default/#using-the-views),
  [`PasswordResetView`](https://docs.djangoproject.com/en/6.1/topics/auth/default/#django.contrib.auth.views.PasswordResetView)
  and [`PasswordResetConfirmView`](https://docs.djangoproject.com/en/6.1/topics/auth/default/#django.contrib.auth.views.PasswordResetConfirmView).
- [Django: The `login_not_required` decorator](https://docs.djangoproject.com/en/6.1/topics/auth/default/#django.contrib.auth.decorators.login_not_required).
- [Django: Custom users and the built-in auth forms](https://docs.djangoproject.com/en/6.1/topics/auth/customizing/#custom-users-and-the-built-in-auth-forms):
  why `PasswordResetForm` works with our user model.
- [Django: ModelForms](https://docs.djangoproject.com/en/6.1/topics/forms/modelforms/) and
  [`get_object_or_404`](https://docs.djangoproject.com/en/6.1/topics/http/shortcuts/#get-object-or-404).
- [OWASP: Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html):
  what a good reset flow does, and how Django's matches it.
- [MDN: the `<form>` element](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/form)
  (`enctype`).
- [MDN: Django tutorial part 8, User authentication and permissions](https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Server-side/Django/Authentication):
  the login and password reset templates, step by step. It includes all of
  `django.contrib.auth.urls` at once; we add the views one by one.
- [Django: Working with forms](https://docs.djangoproject.com/en/6.1/topics/forms/): bound and
  unbound forms, the pattern of `profile_edit`.
- [Django: Path converters](https://docs.djangoproject.com/en/6.1/topics/http/urls/#path-converters):
  how `/students/<int:pk>/` becomes the view's `pk`.
- [Django: Password management](https://docs.djangoproject.com/en/6.1/topics/auth/passwords/):
  how Django stores and checks passwords, and the validators the change and reset forms run.
