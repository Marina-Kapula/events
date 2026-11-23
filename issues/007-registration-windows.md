# Open a registration window with a QR code

Status: done · Opened: 2026-11-21 · Milestone: M1 · Depends on: 002, 005

## Why

Students join AMFI Meetups at the welcome meeting. At the end of the talk on the Erasmus rules,
the admin puts a QR code on the projector, everyone scans it with their phone, and they register
on the spot (SPEC.md §2 #5). Nobody types in forty names, and nobody gets an invitation email.

The QR code must stop working soon after the meeting. Otherwise a photo of it, forwarded to a
group chat, lets anyone in. So the link belongs to a **registration window**: a row in the
database with an expiry time, which the admin can also close early (§2 #7, #11). Each student
remembers the window they came through, so the admin can see who registered at which meeting.

This issue builds the window, its admin page with the QR code, and the public page the QR code
opens. Issue 008 puts the registration form on that page.

## What you'll build

- A `RegistrationWindow` model, and a `registration_window` field on `User`.
- In the admin, "Add registration window" asks one thing: how long it stays open (15 min, 30 min,
  1 h or 2 h; 30 min is preselected). After saving, the admin lands on the window's page: a big QR
  code for the projector, the link, when it expires, whether it is open, and who registered.
- An admin action "Close now" in the list of windows.
- A public page at `/register/<code>/`: "Registration is open" while the window is open,
  "Registration closed, ask the AMFI staff" once it isn't, and a 404 for an unknown code.
- A `make_window` test fixture, and tests.

Not in this issue: the registration form and the verification email (issue 008).

## Before you start

Read:
- SPEC.md §2 #5, #7, #8, #11, #14, #15, #35; §5 (`RegistrationWindow`, and
  `User.registration_window`); §6.1 points 1–3; §8 (Registration windows).
- AGENTS.md: Layers (methods that depend on the time take `now`), Views and templates (no
  `mark_safe` on anything user-derived), and Django.
- `docs/learn/how-a-django-request-works.md` (a URL with a parameter, a 404) and
  `docs/learn/testing-with-pytest-django.md` ("Time without waiting"), if they are new to you.
- [Django: The admin's `ModelAdmin` methods](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#modeladmin-methods)
  (`save_model`, `get_fields`, `get_inlines`, `has_change_permission`) and
  [Admin actions](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/actions/).
- [segno: Creating QR codes](https://segno.readthedocs.io/en/latest/make.html).

Words you'll meet:
- **Registration window**: the time during which the registration link works. One row per
  meeting.
- **QR code**: a square barcode. A phone camera reads it and offers to open the link inside.
- **SVG**: an image format written as text. The server can put it straight into the HTML, so
  there is no image file to store or serve.
- **Autoescaping and `mark_safe`**: Django escapes every value it puts into a template, so
  `<script>` typed by a user shows up as text instead of running. `mark_safe` says "this string is
  HTML that *I* made: print it as it is".
- **Admin action**: a function that runs on the rows you tick in an admin list. "Delete selected"
  is one.
- **Inline**: a small table of related rows shown on another model's admin page.

## Steps

### 1. Add segno

The QR code is drawn on the server by [segno](https://segno.readthedocs.io/), a small pure-Python
library with no dependencies of its own (SPEC.md §2 #8). SPEC.md §3 already records the decision,
so you only install it:

```sh
uv add segno
```

- [x] `pyproject.toml` and `uv.lock` list segno.

### 2. Write the model

Add this to `accounts/models.py`, below `User`. The new imports go at the top of the file:

```python
import secrets
from datetime import datetime

from django.conf import settings


def new_window_code() -> str:
    return secrets.token_urlsafe(16)


class RegistrationWindow(models.Model):
    code = models.CharField(
        max_length=32, unique=True, default=new_window_code, editable=False
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    opened_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-opened_at",)

    @override
    def __str__(self) -> str:
        opened = timezone.localtime(self.opened_at)
        return f"Window of {opened:%d %b %Y, %H:%M}"

    def is_open(self, *, now: datetime) -> bool:
        return self.closed_at is None and now < self.expires_at
```

And one new field on `User`, after `deleted_at`:

```python
    registration_window = models.ForeignKey(
        "RegistrationWindow",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="students",
    )
```

Why each piece is there:

- **`default=new_window_code`, without parentheses.** Django calls the function for every new
  window. With `default=secrets.token_urlsafe(16)` Python would run it *once*, when the file is
  imported, and every window would get the same code. It is a named function, not a `lambda`,
  because the migration has to import it by name.
- **`secrets.token_urlsafe(16)`**: 16 random bytes, written as 22 URL-safe characters. Nobody can
  guess it. Use `secrets` for anything that must be unguessable, never `random`.
- **`editable=False`**: the code never appears in a form, not even in the admin.
- **`related_name="students"`**: `window.students.all()` lists the students who came through a
  window. `"+"` on `opened_by` means "no way back from the user"; we never need it.
- **`"RegistrationWindow"` in quotes**: the class is defined *below* `User`, so `User` names it
  with a string, and Django resolves it later.
- **`null=True` on the user's field**: admins, and the students in older tests, came through no
  window.
- **`PROTECT`**: a window that students came through can't be deleted. That keeps the history of
  who registered at which meeting. (The same for `opened_by`: an admin who opened a window can't
  be deleted.)
- **`is_open(*, now)`** takes the time as an argument (AGENTS.md, Layers): the page passes
  `timezone.now()`, and a test passes a fixed time, so it never depends on when it runs.

- [x] The model and the field are in `accounts/models.py`.

### 3. Make the migration

```sh
uv run python manage.py makemigrations accounts
uv run python manage.py migrate
```

Django writes one migration, `accounts/migrations/0002_registrationwindow_user_registration_window.py`,
with two operations: *Create model RegistrationWindow* and *Add field registration_window to
user*. Open it and read it: it refers to `accounts.models.new_window_code`, which is why that
function must keep its name.

- [x] The migration exists and `migrate` runs.

### 4. The admin pages

The admin needs three different pages: an *add* page that asks only for a duration, a window's
page that only *shows* things (the QR code, the link, the students), and the list with the "Close
now" action. Add this to `accounts/admin.py`:

```python
from datetime import timedelta
from typing import override

import segno
from django import forms
from django.conf import settings
from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import SafeString, mark_safe

from accounts.models import RegistrationWindow, User


class OpenWindowForm(forms.ModelForm[RegistrationWindow]):
    duration = forms.TypedChoiceField(
        choices=(
            (15, "15 minutes"),
            (30, "30 minutes"),
            (60, "1 hour"),
            (120, "2 hours"),
        ),
        coerce=int,
        initial=30,
        help_text="The QR code stops working after this time.",
    )

    class Meta:
        model = RegistrationWindow
        fields: tuple[str, ...] = ()  # the duration isn't a model field


class StudentInline(admin.TabularInline[User, RegistrationWindow]):
    model = User
    fields = ("full_name", "email", "nationality", "is_active")
    extra = 0
    verbose_name_plural = "Students who registered"


@admin.register(RegistrationWindow)
class RegistrationWindowAdmin(admin.ModelAdmin[RegistrationWindow]):
    form = OpenWindowForm
    list_display = ("__str__", "opened_by", "expires_at", "is_open_now")
    actions = ("close_now",)

    @override
    def get_fields(
        self, request: HttpRequest, obj: RegistrationWindow | None = None
    ) -> tuple[str, ...]:
        if obj is None:  # the add page asks only for the duration
            return ("duration",)
        return (
            "qr_code",
            "register_url",
            "expires_at",
            "is_open_now",
            "closed_at",
            "opened_by",
            "opened_at",
        )

    @override
    def get_inlines(
        self, request: HttpRequest, obj: RegistrationWindow | None
    ) -> tuple[type[StudentInline], ...]:
        return () if obj is None else (StudentInline,)

    # A window can't be edited: its page only shows it.
    @override
    def has_change_permission(
        self, request: HttpRequest, obj: RegistrationWindow | None = None
    ) -> bool:
        return False

    @override
    def save_model(
        self,
        request: HttpRequest,
        obj: RegistrationWindow,
        form: forms.ModelForm[RegistrationWindow],
        change: bool,
    ) -> None:
        assert isinstance(request.user, User)  # the admin requires a login
        obj.opened_by = request.user
        minutes: int = form.cleaned_data["duration"]
        obj.expires_at = obj.opened_at + timedelta(minutes=minutes)
        super().save_model(request, obj, form, change)

    @override
    def response_post_save_add(
        self, request: HttpRequest, obj: RegistrationWindow
    ) -> HttpResponseRedirect:
        # Straight to the QR code, instead of the list.
        url = reverse("admin:accounts_registrationwindow_change", args=(obj.pk,))
        return HttpResponseRedirect(url)

    @admin.display(description="Registration link")
    def register_url(self, window: RegistrationWindow) -> str:
        return settings.SITE_URL + reverse("register", args=(window.code,))

    @admin.display(description="QR code")
    def qr_code(self, window: RegistrationWindow) -> SafeString:
        qr = segno.make_qr(self.register_url(window))
        # Safe: segno draws the SVG from our own URL; nothing in it comes from a user.
        return mark_safe(qr.svg_inline(scale=10, light="white"))

    @admin.display(description="Open", boolean=True)
    def is_open_now(self, window: RegistrationWindow) -> bool:
        return window.is_open(now=timezone.now())

    @admin.action(description="Close now")
    def close_now(
        self, request: HttpRequest, queryset: QuerySet[RegistrationWindow]
    ) -> None:
        now = timezone.now()
        closed = queryset.filter(closed_at=None, expires_at__gt=now).update(
            closed_at=now
        )
        self.message_user(request, f"Closed {closed} window(s).")
```

Piece by piece:

- **`OpenWindowForm`** is a `ModelForm` with no model fields (`fields = ()`) and one extra field,
  `duration`. `TypedChoiceField(coerce=int)` turns the posted text `"30"` into the number `30`.
  The admin needs a `ModelForm`, even when it only asks for one value.
- **`get_fields`** decides what each page shows. `obj is None` means "the add page". On the
  window's page, the names are fields of the model (`expires_at`) or methods of this class
  (`qr_code`).
- **`has_change_permission` returns `False`**: the window's page becomes *view only*. Django shows
  every field read-only, with no Save button, and calls the page "View registration window".
  There is nothing to edit: the only change, closing early, is the action.
- **`save_model`** runs when the add form is saved. It sets who opened the window and when it
  expires. `request.user` is typed as "a user, or `AnonymousUser`"; the admin only lets staff in,
  and the `assert` tells pyrefly so (and would fail loudly if it were ever wrong).
- **`response_post_save_add`** decides where "Save" goes after adding. Normally that is the list;
  we go straight to the QR code, because that's what the presenter wants on the projector. This
  method isn't in the reference docs, but it is a public method of `ModelAdmin`: read it in
  [Django's source](https://github.com/django/django/blob/stable/6.1.x/django/contrib/admin/options.py).
- **`register_url`** starts with `settings.SITE_URL` (issue 005), never with the request's host
  (SPEC.md §2 #35). Locally it is `http://127.0.0.1:8000`; on your server it must be
  `https://<your domain>`, or the QR code sends phones to the wrong place.
- **`qr_code`**:
  - `segno.make_qr` always makes a normal QR code. `segno.make` may choose a *Micro* QR code
    for short text, which many phone cameras can't read.
  - `svg_inline(scale=10)` draws each little square 10 pixels wide, so our links give a code of
    about 410 px, big enough for a projector.
  - `light="white"` paints the background. By default it is transparent, and in the admin's
    dark mode a black code on a dark page can't be scanned.
  - **Why `mark_safe` is fine here.** AGENTS.md forbids `mark_safe` on anything *user-derived*.
    This SVG is made by segno from our own URL, and the URL becomes black squares, not text in
    the page. No visitor can put anything into it. Without `mark_safe` the admin would escape it
    and show the SVG source as text.
- **`is_open_now`** with `boolean=True` shows a green tick or a red cross, in the list and on the
  page.
- **`close_now`** sets `closed_at` on the ticked windows that are still open. A plain `update()`
  is enough: no rule, no email, nothing else changes (it isn't one of the services in SPEC.md
  §6.10).
- **`StudentInline`** lists the students who came through the window, as a table. On a view-only
  page, the inline is read-only too. **`get_inlines`** hides it on the add page: there is no
  window yet, and an inline there would expect form data for new users.

Finally, show the window in the Users page too (SPEC.md §8). In `UserAdmin`, add
`"registration_window"` to `list_display`, `list_filter` and `fields`, and make it read-only:

```python
    list_filter = ("is_active", "is_staff", "registration_window")
    readonly_fields = ("registration_window", "date_joined", "deleted_at")
```

- [x] "Add registration window" asks only for the duration and then shows the QR code.
- [x] The list has a "Close now" action, and an Open column.
- [x] The Users page shows and filters by window.

### 5. The public page

The QR code opens `/register/<code>/`. Create `accounts/urls.py` (if issue 009 got there first,
add the line to its list):

```python
from django.urls import URLPattern, path

from accounts import views

urlpatterns: list[URLPattern] = [
    path("register/<str:code>/", views.register, name="register"),
]
```

Include it in `config/urls.py`, at the root (the URLs in SPEC.md §7 have no `accounts/` prefix),
unless 009 already did:

```python
from django.urls import URLPattern, URLResolver, include, path

    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
```

Then the view, in `accounts/views.py` (issue 002 deleted the empty one Django made; create it, or
add to 009's):

```python
from django.contrib.auth.decorators import login_not_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from accounts.models import RegistrationWindow


@login_not_required
def register(request: HttpRequest, code: str) -> HttpResponse:
    window = get_object_or_404(RegistrationWindow, code=code)
    if not window.is_open(now=timezone.now()):
        return render(request, "accounts/register_closed.html")
    return render(request, "accounts/register.html", {"window": window})
```

- **`@login_not_required`**: Django's `LoginRequiredMiddleware` sends every visitor to the login
  page, unless the view is marked public (SPEC.md §2 #14). The phones in the room aren't logged
  in.
- **`get_object_or_404`**: a code that doesn't exist is a 404 (SPEC.md §6.1 point 3).

Two templates, in `accounts/templates/accounts/`. `register.html`:

```html
{% extends "base.html" %}

{% block title %}Register · AMFI Meetups{% endblock %}

{% block header %}{% endblock %}

{% block content %}
<main id="main">
  <h1>Welcome to AMFI Meetups</h1>
  <p>Registration is open until {{ window.expires_at|time:"H:i" }}. The form comes in issue 008.</p>
</main>
{% endblock %}
```

`register_closed.html` is the same, with the title "Registration closed" and the sentence
"Registration closed, ask the AMFI staff." The empty `header` block hides the navigation and the
"Log out" button, as on the login page: the visitor isn't logged in. Style both pages with your
UI library (issue 003).

- [x] In a private browser window, the link from the admin page shows "Registration is open".
- [x] After "Close now", the same link shows "Registration closed, ask the AMFI staff".

### 6. Scan it with your phone

The real test is a phone. Your laptop and phone must be on the same Wi-Fi (some university
networks block this; a phone hotspot works).

1. Find your laptop's address on the network: `ipconfig getifaddr en0` on a Mac, `ipconfig` on
   Windows, `hostname -I` on Linux. Say it is `192.168.1.20`.
2. In `.env`: `DJANGO_SITE_URL=http://192.168.1.20:8000`, and add `192.168.1.20` to
   `DJANGO_ALLOWED_HOSTS`.
3. `uv run python manage.py runserver 0.0.0.0:8000` (`0.0.0.0` accepts connections from other
   devices, not only from the laptop).
4. Add a window in the admin and scan the code.

Put `.env` back afterwards. After your next deploy (issue 004), do the same on your server: there
`DJANGO_SITE_URL` is already your domain.

- [x] Your phone opens the registration page from the QR code.

### 7. Tests

Add the fixture to `tests/conftest.py`, below the others (new imports at the top):

```python
from datetime import timedelta

from django.utils import timezone

from accounts.models import RegistrationWindow, User


@pytest.fixture
def make_window(make_staff: Callable[..., User]) -> Callable[..., RegistrationWindow]:
    def make(**overrides: object) -> RegistrationWindow:
        fields: dict[str, object] = {
            "opened_by": make_staff(),
            "expires_at": timezone.now() + timedelta(minutes=30),
            **overrides,
        }
        window = RegistrationWindow(**fields)
        window.full_clean()
        window.save()
        return window

    return make
```

By default the window is open for the next 30 minutes; a test passes `closed_at=...` or other
times when it needs something else.

Then `tests/accounts/test_registration_windows.py`:

```python
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pytest_django import Settings

from accounts.models import RegistrationWindow, User

pytestmark = pytest.mark.django_db

NOON = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
CHANGELIST = "/admin/accounts/registrationwindow/"


def test_a_window_is_open_until_it_expires(
    make_window: Callable[..., RegistrationWindow],
) -> None:
    window = make_window(opened_at=NOON, expires_at=NOON + timedelta(minutes=30))

    assert window.is_open(now=NOON + timedelta(minutes=29))
    assert not window.is_open(now=NOON + timedelta(minutes=30))


def test_a_closed_window_is_not_open(
    make_window: Callable[..., RegistrationWindow],
) -> None:
    window = make_window(
        opened_at=NOON,
        expires_at=NOON + timedelta(minutes=30),
        closed_at=NOON + timedelta(minutes=5),
    )

    assert not window.is_open(now=NOON + timedelta(minutes=10))


def test_each_window_gets_its_own_random_code(
    make_window: Callable[..., RegistrationWindow],
) -> None:
    first, second = make_window(), make_window()

    assert len(first.code) == 22
    assert first.code != second.code


def test_admin_opens_a_window_for_the_chosen_duration(
    admin_client: Client, admin_user: User
) -> None:
    response = admin_client.post(f"{CHANGELIST}add/", {"duration": "60"})

    window = RegistrationWindow.objects.get()
    assert response.status_code == 302
    assert response["Location"] == f"{CHANGELIST}{window.pk}/change/"
    assert window.opened_by == admin_user
    assert window.expires_at - window.opened_at == timedelta(minutes=60)


def test_window_page_shows_the_qr_code_and_the_link(
    admin_client: Client,
    settings: Settings,
    make_window: Callable[..., RegistrationWindow],
) -> None:
    settings.SITE_URL = "https://meetups.example.com"
    window = make_window()

    response = admin_client.get(f"{CHANGELIST}{window.pk}/change/")

    assert response.status_code == 200
    assert b"<svg" in response.content
    url = f"https://meetups.example.com/register/{window.code}/"
    assert url.encode() in response.content


def test_window_page_lists_the_students_who_registered(
    admin_client: Client,
    make_window: Callable[..., RegistrationWindow],
    make_student: Callable[..., User],
) -> None:
    window = make_window()
    make_student(full_name="Student One", registration_window=window)
    make_student(full_name="Student Two")

    response = admin_client.get(f"{CHANGELIST}{window.pk}/change/")

    assert b"Student One" in response.content
    assert b"Student Two" not in response.content


def test_close_now_closes_the_selected_windows(
    admin_client: Client, make_window: Callable[..., RegistrationWindow]
) -> None:
    window = make_window()

    response = admin_client.post(
        CHANGELIST, {"action": "close_now", "_selected_action": [window.pk]}
    )

    window.refresh_from_db()
    assert response.status_code == 302
    assert window.closed_at is not None
    assert not window.is_open(now=timezone.now())


def test_register_page_is_public_while_the_window_is_open(
    client: Client, make_window: Callable[..., RegistrationWindow]
) -> None:
    window = make_window()

    response = client.get(reverse("register", args=(window.code,)))

    assert response.status_code == 200
    assert b"Registration is open" in response.content


@pytest.mark.parametrize(
    "overrides",
    [
        {"closed_at": timezone.now()},
        {"opened_at": NOON, "expires_at": NOON + timedelta(minutes=15)},
    ],
    ids=["closed", "expired"],
)
def test_register_page_says_closed_when_the_window_is_not_open(
    client: Client,
    make_window: Callable[..., RegistrationWindow],
    overrides: dict[str, object],
) -> None:
    window = make_window(**overrides)

    response = client.get(reverse("register", args=(window.code,)))

    assert response.status_code == 200
    assert b"Registration closed, ask the AMFI staff" in response.content


def test_unknown_code_is_a_404(client: Client) -> None:
    assert client.get("/register/not-a-code/").status_code == 404
```

Things to notice:
- `NOON` is a fixed time: the `is_open` tests give the same answer on any day.
- `settings` is pytest-django's fixture: a setting changed through it goes back after the test.
- An admin action is a POST to the list page with `action` and the ticked ids in
  `_selected_action`: exactly what your browser sends.
- `test_admin_opens_every_changelist` in `tests/test_smoke.py` now opens the windows list too.

- [x] The tests pass.
- [x] `scripts/check.sh` passes.

## Done when

- [x] `RegistrationWindow` exists with a random, unique code; users have a `registration_window`;
  one migration adds both.
- [x] The admin opens a window for 15, 30, 60 or 120 minutes, and its page shows the QR code, the
  link from `SITE_URL`, the expiry, open or closed, and the students who registered.
- [x] "Close now" closes a window early (test).
- [x] `/register/<code>/` is public and says open or closed; an unknown code is a 404 (tests).
- [x] You scanned a QR code with a phone and it opened the page.
- [x] `scripts/check.sh` passes.
- [x] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 007-registration-windows
```

Suggested commits (each one passes `scripts/check.sh`):
1. `Add segno`
2. `Add the RegistrationWindow model`
3. `Show registration windows and their QR code in the admin`
4. `Add the public registration page`
5. `Add registration window tests` (or put each test in the commit of what it tests)
6. `Close 007 in the issue`

Open a pull request titled "Open a registration window with a QR code". Add a screenshot of a
window's admin page with the QR code, and say that you scanned it with a phone. Ask the reviewer
to look at the `mark_safe` line and its comment. `docs/workflow/git.md` has every step.

## Watch out

- **`default=new_window_code`, not `default=new_window_code()`**: with the parentheses every
  window gets the same code, and `makemigrations` freezes it into the migration.
- **Compare times with `timezone.now()`, never `datetime.now()`.** `USE_TZ` is on: the database
  stores UTC, the admin shows Europe/Rome, and comparing with a naive `datetime.now()` raises an
  error.
- **A wrong `DJANGO_SITE_URL` on the server makes a QR code that points to `127.0.0.1`.** It looks
  fine on the projector, and fails on every phone. Scan it once before the meeting.
- **Deleting a window that students came through fails** with a "protected" page. That is
  `PROTECT` doing its job. Close windows; don't delete them.
- **A forwarded photo of the QR code works until the window closes.** That's why durations are
  short, and why "Close now" exists: close the window when the room is done.
- **`mark_safe` only for HTML you generate.** If you ever want to show a student's name next to
  the code, put it in the template (escaped), not inside the marked-safe string.

## Worked example

- [04, two migrations numbered 0003](../docs/examples/04-two-migrations-numbered-0003.md): once
  this issue is merged, in a scratch copy, before two of you add migrations to the same app at
  once.

## Further reading

- [Django: The admin site](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/):
  [`save_model`](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#django.contrib.admin.ModelAdmin.save_model),
  [`get_fields`](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#django.contrib.admin.ModelAdmin.get_fields),
  [`has_change_permission`](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#django.contrib.admin.ModelAdmin.has_change_permission),
  [`@admin.display`](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#django.contrib.admin.display),
  [inlines](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#inlinemodeladmin-objects).
- [Django: Admin actions](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/actions/).
- [Django: Automatic HTML escaping](https://docs.djangoproject.com/en/6.1/ref/templates/language/#automatic-html-escaping)
  and [`mark_safe`](https://docs.djangoproject.com/en/6.1/ref/utils/#django.utils.safestring.mark_safe).
- [Django: `Field.default`](https://docs.djangoproject.com/en/6.1/ref/models/fields/#django.db.models.Field.default)
  and [`PROTECT`](https://docs.djangoproject.com/en/6.1/ref/models/fields/#django.db.models.PROTECT).
- segno: [Creating QR codes](https://segno.readthedocs.io/en/latest/make.html),
  [`svg_inline`](https://segno.readthedocs.io/en/latest/api.html#segno.QRCode.svg_inline),
  [SVG options](https://segno.readthedocs.io/en/latest/svg-options.html).
- [Python: `secrets`](https://docs.python.org/3/library/secrets.html): why not `random`.
- [QR code](https://en.wikipedia.org/wiki/QR_code) on Wikipedia: how the squares hold the data.
- [Django tutorial, part 7](https://docs.djangoproject.com/en/6.1/intro/tutorial07/): `fields`,
  `list_display`, inlines and `@admin.display` in the admin, step by step on a small example.
- [Django: Time zones](https://docs.djangoproject.com/en/6.1/topics/i18n/timezones/): aware and
  naive datetimes, UTC in the database, and why `timezone.now()`.
- [MDN: Cross-site scripting (XSS)](https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/XSS):
  the attack autoescaping prevents, and what `mark_safe` switches off.
