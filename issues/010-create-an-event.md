# Create an event and send it to review

Status: todo · Opened: 2026-11-21 · Milestone: M2 · Depends on: 002, 005, 006

## Why

This is the heart of the app: students create events (a pizza night, a trip to Rome) for the
others to join. AMFI checks every event before anyone else sees it, so there are no fakes
(SPEC.md §1). There are no drafts: saving a new event sends it straight to review, and the AMFI
staff get an email with a link to it in the admin (SPEC.md §2 #20, §6.6).

This issue creates the `events` app and the `Event` model that every other M2 issue builds on:
the review buttons (011), the list and the event page (012), joining (013), editing (014) and
cancelling (015).

## What you'll build

- A new app, `events`, with the `Event` model and an abstract base model, `EventFields`, that
  holds the fields an organizer fills in.
- A "Create" page at `/events/new/` for students: title, type, description, photo, city, place,
  date and time, max people, language. Staff get a 404 there (SPEC.md §6.9).
- Saving it creates an event with the status `pending`, emails every active staff user a link to
  the event's admin page, and goes back to the home page with "Sent to AMFI for review".
- An "Events" page in the Django admin. An event added *there* is `approved` at once, with the
  admin as its organizer (SPEC.md §2 #15).
- A `make_event` test fixture that every later events issue uses.

Not in this issue: the Approve / Reject buttons (011), the event list and the event page (012),
joining (013), editing (014). Until 012, an event you create is only visible in the admin.

## Before you start

Read:
- SPEC.md §2 #15, #17, #20–#24, #34; §5 (`events.EventFields`, `events.Event`); §6.2 (the first
  two rows); §6.6; §6.9; §8 (Events).
- AGENTS.md: Layers, Views and templates, Typing.
- `docs/typing/custom-querysets.md` and `docs/testing/emails.md`.
- `docs/learn/hypermedia-and-forms.md` (the form page pattern) and
  `docs/learn/transactions-and-race-conditions.md` (why a service, and `on_commit`).
- [Django: Creating forms from models](https://docs.djangoproject.com/en/6.1/topics/forms/modelforms/),
  especially "The `save()` method".
- [Django: Abstract base classes](https://docs.djangoproject.com/en/6.1/topics/db/models/#abstract-base-classes).

Words you'll meet:
- **Abstract base model**: a model class with `abstract = True`. It has no table of its own; the
  models that inherit from it get its fields in *their* tables.
- **`TextChoices`**: a fixed list of values for a field (`"food"`, shown as "Food"). Django turns
  it into a `<select>` in forms and checks the value in `full_clean()`.
- **`ModelForm`**: a form built from a model's fields. `form.save(commit=False)` gives you the
  model object *without* saving it, so you can fill in what the form doesn't ask for.
- **Service**: a plain function in `services.py` that changes data and applies a rule or sends an
  email (AGENTS.md, Layers). Here: `event_create`.
- **`transaction.on_commit`**: "run this once the database has really saved everything". Emails
  go there, so nobody is told about a change that was rolled back.

## Steps

### 1. Create the `events` app

```sh
uv run python manage.py startapp events
```

Delete `events/tests.py` (tests live in `tests/`). Add `"events"` to `INSTALLED_APPS` after
`"accounts"`, and include the app's URLs in `config/urls.py`, after the admin:

```python
path("", include("events.urls")),
```

(`include` comes from `django.urls`.) If your project still uses Tailwind (issue 003), add the
app's templates to `assets/css/source.css`, or Tailwind won't see the classes you use there:

```css
@source "../../events/templates";
```

- [ ] The app exists, is installed, and its URLs are included.

### 2. The models

Why two classes? Issue 014 lets an organizer edit an approved event while the old version stays
public. The proposed edit is stored in a second model, `EventChange`, with *the same fields*
(SPEC.md §2 #17). Putting those fields in an abstract base now means 014 only writes
`class EventChange(EventFields)`, and nobody has to move fields between models (and rewrite
migrations) later. The fields that only the real event has (organizer, status, review note) go
in `Event`.

`events/models.py`:

```python
from typing import override

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class EventFields(models.Model):
    """The fields an organizer fills in. Issue 014's EventChange reuses them."""

    class Type(models.TextChoices):
        MEETUP = "meetup", "Meetup"
        FOOD = "food", "Food"
        TRIP = "trip", "Trip"
        SPORT = "sport", "Sport"
        PARTY = "party", "Party"
        CULTURE = "culture", "Culture"
        OTHER = "other", "Other"

    title = models.CharField(max_length=80)
    description = models.TextField()
    photo = models.ImageField(upload_to="photos/events/")
    city = models.CharField(max_length=60)
    place = models.CharField(max_length=120)
    starts_at = models.DateTimeField()
    type = models.CharField(max_length=10, choices=Type.choices)
    max_people = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(2), MaxValueValidator(100)],
        help_text="Including you, the organizer.",
    )
    language = models.CharField(max_length=40, default="English")

    class Meta:
        abstract = True


class EventQuerySet(models.QuerySet["Event"]):
    """Reads of events. Issue 012 adds the event list's methods here."""


class Event(EventFields):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    organizer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # pyrefly sees as_manager() as a plain Manager; the manager proxies the QuerySet's
    # methods (docs/typing/custom-querysets.md).
    objects: EventQuerySet = EventQuerySet.as_manager()  # pyrefly: ignore[bad-assignment]

    @override
    def __str__(self) -> str:
        return self.title
```

Why each piece is there:

- **`Type` lives inside `EventFields`**, next to the field that uses it. `Event` inherits it, so
  `Event.Type.FOOD` works everywhere. A new type is one line (SPEC.md §2 #22).
- **`max_people` counts the organizer** (SPEC.md §2 #24): 2 is the smallest event that makes
  sense. The validators run in `full_clean()`, so the form shows the error.
- **`organizer` is `PROTECT`**: the database refuses to delete a user who still organizes events.
  Students are soft-deleted instead (issue 017). It points at `settings.AUTH_USER_MODEL`, never
  at `User` directly (issue 002, Watch out).
- **`status` defaults to `pending`**, and nothing but the services changes it (SPEC.md §6.2).
  `review_note` keeps the last rejection reason (issue 011).
- **`EventQuerySet` is empty for now.** It is here so the `objects` line, with its one explained
  ignore, is right from the start; 012 adds `listed()`, `search()` and the rest.

Make the migration:

```sh
uv run python manage.py makemigrations events
uv run python manage.py migrate
```

- [ ] `events/models.py` as above; `events/migrations/0001_initial.py` creates `Event` only
      (an abstract model has no table).

### 3. The form

`events/forms.py`:

```python
from datetime import datetime

from django import forms
from django.utils import timezone

from config.photos import PhotoField
from events.models import Event


class EventForm(forms.ModelForm[Event]):
    photo = PhotoField()
    # The browser's own date and time picker. It sends, and needs, this format.
    starts_at = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
        )
    )

    class Meta:
        model = Event
        fields = (
            "title",
            "type",
            "description",
            "photo",
            "city",
            "place",
            "starts_at",
            "max_people",
            "language",
        )

    def clean_starts_at(self) -> datetime:
        starts_at = self.cleaned_data["starts_at"]
        if starts_at <= timezone.now():
            raise forms.ValidationError("Pick a date and time in the future.")
        return starts_at
```

- **`fields` lists only what the organizer fills in.** `organizer`, `status` and `review_note`
  are not in the form, so nobody can POST `status=approved` to skip the review.
- **`photo = PhotoField()`** replaces the plain image field with issue 006's, which refuses big
  files and shrinks the photo.
- **`starts_at` is declared on the form** to get `<input type="datetime-local">`, a date and time
  picker on every phone and browser. The browser sends `2026-12-01T19:30`, with no time zone;
  Django reads it in `TIME_ZONE` (Europe/Rome, SPEC.md §2 #34).
- **"In the future" is a form rule, not a model rule.** A model validator would run on every
  `full_clean()`, also when a service saves an event that has already started; the form only
  runs when someone sends it. The admin checks it again when approving (011).

- [ ] `EventForm` as above.

### 4. The service: save and tell the staff

Creating an event sends an email, so it isn't a plain `form.save()`: it goes through a service
(AGENTS.md, Layers). The view gives it the unsaved event from the form.

`events/services.py`:

```python
from django.db import transaction

from accounts.models import User
from config.emails import send_email
from events.models import Event


def event_create(*, event: Event, organizer: User) -> None:
    """Save a new event from the student page and send it to review (SPEC §6.2)."""
    event.organizer = organizer
    event.status = Event.Status.PENDING
    event.full_clean()
    event.save()
    staff = [user.email for user in User.objects.filter(is_staff=True, is_active=True)]
    transaction.on_commit(
        lambda: send_email(
            to=staff, template="events/emails/event_created", context={"event": event}
        )
    )
```

The two email templates (issue 005: the subject is one line, and both start with
`{% autoescape off %}`). `events/templates/events/emails/event_created_subject.txt`:

```django
{% autoescape off %}New event to review: {{ event.title }}{% endautoescape %}
```

`events/templates/events/emails/event_created.txt`:

```django
{% autoescape off %}{{ event.organizer.full_name }} sent a new event for review:

{{ event.title }}
{{ event.starts_at|date:"l j F Y, H:i" }} in {{ event.city }}, {{ event.place }}

Approve or reject it in the admin:
{{ site_url }}{% url "admin:events_event_change" event.pk %}
{% endautoescape %}
```

`admin:events_event_change` is the name Django's admin gives the change page of an event: it
builds `/admin/events/event/<id>/change/`, and `site_url` (added by `send_email`) puts the
server's address in front (SPEC.md §2 #35).

- [ ] `event_create` and both templates.

### 5. The page

`events/views.py`:

```python
from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from accounts.models import User
from events.forms import EventForm
from events.services import event_create


def event_new(request: HttpRequest) -> HttpResponse:
    user = request.user
    if not isinstance(user, User) or user.is_staff:
        raise Http404
    if request.method == "POST":
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event_create(event=form.save(commit=False), organizer=user)
            messages.success(
                request, "Sent to AMFI for review. We'll email you when it's approved."
            )
            return redirect("home")
    else:
        form = EventForm()
    return render(request, "events/event_form.html", {"form": form})
```

This is the pattern of every form page in the app: GET shows an empty form; a valid POST does
the work, adds a message and **redirects** (Post/Redirect/Get, so a reload doesn't send it
twice); an invalid POST shows the same page again with the errors, status 200.

The first two lines: `request.user` is typed as "a user or `AnonymousUser`".
`LoginRequiredMiddleware` already sent anonymous visitors to the login page, so the `isinstance`
check is really about staff, and it tells pyrefly that `user` is our `User` from here on.

`events/urls.py`:

```python
from django.urls import URLPattern, path

from events import views

urlpatterns: list[URLPattern] = [
    path("events/new/", views.event_new, name="event_new"),
]
```

`events/templates/events/event_form.html` (the structure; style it with your UI library, issue
003):

```django
{% extends "base.html" %}

{% block title %}New event · AMFI Meetups{% endblock %}

{% block content %}
<main id="main">
  <h1>New event</h1>
  <p>AMFI checks every event before it is listed. We'll email you when it's approved.</p>
  <form method="post" enctype="multipart/form-data">
    {% csrf_token %}
    {{ form }}
    <button type="submit">Send to review</button>
  </form>
</main>
{% endblock %}
```

Finally, a "Create" link in `templates/base.html`, next to "Events" (and in the bottom
navigation for phones, if issue 003 added one). Staff don't see it (SPEC.md §6.9):

```django
{% if not user.is_staff %}
  <li><a href="{% url 'event_new' %}"{% if request.resolver_match.url_name == 'event_new' %} aria-current="page"{% endif %}>Create</a></li>
{% endif %}
```

- [ ] Logged in as a student, "Create" opens the form; sending it lands on the home page with
      the message, and the event is in the admin as "Pending".
- [ ] A file written by the file email backend in `var/mail/` holds the staff email with the
      admin link.

### 6. Events in the admin

`events/admin.py`:

```python
from typing import ClassVar, override

from django import forms
from django.contrib import admin
from django.db import models
from django.http import HttpRequest

from accounts.models import User
from config.photos import PhotoField
from events.models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin[Event]):
    list_display = ("title", "organizer", "starts_at", "status")
    list_filter = ("status", "type")
    search_fields = ("title", "city")
    list_select_related = ("organizer",)
    # They change only through the review buttons, which call services (SPEC §6.2).
    readonly_fields = ("status", "organizer")
    # Photos uploaded in the admin are checked and shrunk too (SPEC.md §6.8).
    formfield_overrides: ClassVar = {models.ImageField: {"form_class": PhotoField}}

    @override
    def save_model(
        self,
        request: HttpRequest,
        obj: Event,
        form: forms.ModelForm[Event],
        change: bool,
    ) -> None:
        if not change:
            # An event added by staff is approved at once, with them as organizer.
            assert isinstance(request.user, User)  # the admin requires a login
            obj.organizer = request.user
            obj.status = Event.Status.APPROVED
        super().save_model(request, obj, form, change)
```

- **`readonly_fields`**: the admin shows `status` and `organizer` but can't edit them. A status
  typed into a form would skip the emails and the rules; issue 011 adds buttons that call the
  services instead.
- **`save_model`** is the admin's hook for "save this object". `change` is `False` on the Add
  page, so only a *new* event gets the admin as organizer and `approved`. Editing in the admin
  sends no emails (SPEC.md §2 #33).
- **`list_select_related`** loads the organizers in the same query as the list, instead of one
  query per row.

- [ ] `/admin/events/event/` lists events with the filters and search; "Add event" creates an
      approved event organized by you.

### 7. Tests

First the fixture every later events test uses. In `tests/conftest.py`, below the user
fixtures (add `from datetime import timedelta`, `from django.utils import timezone` and
`from events.models import Event` at the top):

```python
@pytest.fixture
def make_event(make_student: Callable[..., User]) -> Callable[..., Event]:
    numbers = itertools.count(1)

    def make(**overrides: object) -> Event:
        n = next(numbers)
        fields: dict[str, object] = {
            "title": f"Event {n}",
            "description": "We meet at the fountain.",
            # A file name is enough for the model; a test that uploads makes an image.
            "photo": "photos/events/event.jpg",
            "city": "Avezzano",
            "place": "Piazza Risorgimento",
            "starts_at": timezone.now() + timedelta(days=7),
            "type": Event.Type.FOOD,
            "max_people": 8,
            # Most tests need an event everyone can see; pass status= for the others.
            "status": Event.Status.APPROVED,
            **overrides,
        }
        if "organizer" not in fields:
            fields["organizer"] = make_student()
        event = Event(**fields)
        event.full_clean()
        event.save()
        return event

    return make
```

`make_event()` gives an approved event a week from now, organized by a new student;
`make_event(status=Event.Status.PENDING, organizer=someone)` gives anything else.

Then `tests/events/__init__.py` (empty) and `tests/events/test_create.py`:

```python
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
```

`photo()` makes a real JPEG in memory, because `PhotoField` opens the upload with Pillow. Issue
006's autouse fixture `_media_root_in_tmp_path` saves it in a temporary folder, not in your
`var/media/`. `former_staff` proves that only *active* staff are emailed. (`make_staff` always
makes an active user, hence the two extra lines.)

- [ ] The tests above pass. `test_admin_opens_every_changelist` now opens the Events page too.
- [ ] `scripts/check.sh` passes.

## Done when

- [ ] A student creates an event at `/events/new/`; it is `pending`, they are its organizer, and
      they land on the home page with "Sent to AMFI for review" (test).
- [ ] Every active staff user gets an email with the event's admin link (test).
- [ ] A start in the past, or max people outside 2–100, is a form error (tests).
- [ ] Staff get a 404 on `/events/new/` (test) and don't see the "Create" link.
- [ ] The admin lists, filters and searches events; `status` and `organizer` are readonly; an
      event added there is approved and organized by the admin (test).
- [ ] `make_event` is in `tests/conftest.py`.
- [ ] `scripts/check.sh` passes.
- [ ] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 010-create-an-event
```

Suggested commits (each one passes `scripts/check.sh`):
1. `Add the events app with the Event model`
2. `Add the event form and the event_create service`
3. `Add the Create page`
4. `Show events in the admin`
5. `Add the make_event fixture and event creation tests`
6. `Close 010 in the issue`

Open a pull request titled "Create an event and send it to review". Show a screenshot of the form
on a phone-sized window, and the email file from `var/mail/`. Ask the reviewer to check that
`status` can't be set from the form or the admin. `docs/workflow/git.md` has every step.

## Watch out

- **`enctype="multipart/form-data"` and `request.FILES`.** Without the first, the browser doesn't
  send the photo at all; without the second, the form never sees it. Either way you get "This
  field is required." for a photo you did choose.
- **Don't call `form.save()` here.** It would save the event without an organizer (an
  `IntegrityError`) and skip the email. `form.save(commit=False)` hands the unsaved event to the
  service, which fills in the rest.
- **The email is sent in `on_commit`**, so in tests `mailoutbox` stays empty unless you wrap the
  request in `django_capture_on_commit_callbacks(execute=True)` (`docs/testing/emails.md`).
- **`{% autoescape off %}` in email templates**, the subject too: without it "D'Arcy & friends"
  arrives as `D&#x27;Arcy &amp; friends`. And keep the subject on one line: a newline in a
  subject is an error (issue 005).
- **Migrations:** `EventFields` has `abstract = True`, so there is no `events_eventfields`
  table. If `makemigrations` creates one, the `abstract` line is missing.
- **Time zones:** compare datetimes with `timezone.now()`, never `datetime.now()`. The second has
  no time zone, and Django refuses to compare the two.

## Worked example

- [05, one registration, request by request](../docs/examples/05-a-request-step-by-step.md), "Try
  this" 1: after step 5, the same trip for `/events/new/`.
- [04, two migrations numbered 0003](../docs/examples/04-two-migrations-numbered-0003.md): if
  someone else adds a migration while you work on this one.

## Further reading

- [Django: Creating forms from models](https://docs.djangoproject.com/en/6.1/topics/forms/modelforms/).
- [Django: Model inheritance](https://docs.djangoproject.com/en/6.1/topics/db/models/#model-inheritance)
  (abstract base classes versus multi-table inheritance, and why we want the first).
- [Django: File uploads](https://docs.djangoproject.com/en/6.1/topics/http/file-uploads/).
- [Django: `ModelAdmin.save_model`](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#django.contrib.admin.ModelAdmin.save_model)
  and [`readonly_fields`](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#django.contrib.admin.ModelAdmin.readonly_fields).
- [Django: Enumeration types (`TextChoices`)](https://docs.djangoproject.com/en/6.1/ref/models/fields/#enumeration-types).
- [MDN: `<input type="datetime-local">`](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/input/datetime-local).
- [Django: Working with forms](https://docs.djangoproject.com/en/6.1/topics/forms/): the GET/POST
  view pattern this page follows, and how errors are shown.
- [Django: Validating objects](https://docs.djangoproject.com/en/6.1/ref/models/instances/#validating-objects):
  what `full_clean()` checks in `event_create`, and why `save()` doesn't check it for you.
- [Django tutorial, part 4](https://docs.djangoproject.com/en/6.1/intro/tutorial04/): a first
  form, `{% csrf_token %}`, and why to redirect after a POST.
