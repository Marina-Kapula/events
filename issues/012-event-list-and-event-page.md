# The event list with filters, and the event page

Status: done · Opened: 2026-11-21 · Milestone: M2 · Depends on: 009, 010

## Why

This is the page students open the app for: what's on, soonest first, with a few filters to find
a pizza night in Avezzano next Friday (SPEC.md §2 #29, `docs/wireframe-*.svg`). Each card leads
to the event's own page: the photo, the details, and who organizes it.

Not every event is for everyone's eyes. A pending or rejected event is the organizer's business
until AMFI approves it, and a cancelled one only matters to the people who were on it (SPEC.md
§6.3). Everyone else gets a plain 404, as if the event didn't exist.

The list replaces the placeholder home page of the skeleton and keeps its URL name, `home`.

## What you'll build

- `/` shows the approved events that haven't started, soonest first, as cards. No pagination.
- A filter form above them, sent with GET: keyword, city, date, type and size.
- `/events/<id>/`, the event page, for whoever may see it (SPEC.md §6.3), with the reason for the
  organizer of a rejected event.
- The organizer on the page: their photo and name, linking to their profile (issue 009); "AMFI"
  for an event by staff (SPEC.md §6.9); "Deleted student" for a soft-deleted organizer (§6.7).
- The card as a template partial, `event_card`, that "My events" (issue 016) reuses.
- A test that the list page runs the same number of queries for any number of events.

Not in this issue: joining, the people going and the spots taken (013), the "Changes pending"
badge (014). The page shows "Going (1 of 8)" for now: the organizer.

It depends on 009 because the organizer links to `student_detail`.

## Before you start

Read:
- SPEC.md §2 #21, #29, #34; §6.3; §6.7 and §6.9 (how an organizer is shown); §7 (the card).
- AGENTS.md: Layers (reads are QuerySet methods), Views and templates (partials; queries).
- `docs/typing/custom-querysets.md`.
- `docs/learn/models-migrations-and-querysets.md` (QuerySets, the N+1 problem) and
  `docs/learn/hypermedia-and-forms.md` (GET or POST: why the filter form is a GET).
- [Django: Making queries](https://docs.djangoproject.com/en/6.1/topics/db/queries/), up to
  "Complex lookups with Q objects".
- [Django: Template partials](https://docs.djangoproject.com/en/6.1/ref/templates/language/#template-partials).

Words you'll meet:
- **QuerySet**: a description of a database query. Filtering returns a new QuerySet; nothing
  runs until you loop over it. So five filters still make **one** SQL query.
- **`Q` object**: one condition you can combine with `|` (or) and `&` (and), for queries that
  `filter(a=…, b=…)` (always "and") can't say.
- **GET form**: a form whose values go in the URL (`/?city=roma&type=food`). Right for search:
  it changes nothing, can be bookmarked and shared, and needs no CSRF token.
- **N+1 queries**: one query for the list, then one more *per row* because the template reads
  something that wasn't loaded. Invisible with 3 events, slow with 300.
- **Template partial**: a named piece of a template (`{% partialdef event_card %}`) that other
  templates can include by name (`"events/event_list.html#event_card"`).

## Steps

### 1. The reads: QuerySet methods

Every question the list asks the database gets a name, as a method on `EventQuerySet`
(AGENTS.md, Layers). Each returns `Self`, so they chain:
`Event.objects.listed(now=now).in_city("roma").of_type("food")`.

In `events/models.py`, first a `Size` list for the size filter, above `EventQuerySet`, then the
methods in it. The imports at the top become:

```python
from datetime import date, datetime
from typing import Self, override

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from accounts.models import User
```

```python
class Size(models.TextChoices):
    """The size filter of the event list (SPEC §2 #29)."""

    SMALL = "small", "Up to 5 people"
    MEDIUM = "medium", "6 to 10 people"
    LARGE = "large", "More than 10 people"


class EventQuerySet(models.QuerySet["Event"]):
    def listed(self, *, now: datetime) -> Self:
        """The event list: approved, not started yet, soonest first."""
        return self.filter(status=Event.Status.APPROVED, starts_at__gt=now).order_by(
            "starts_at"
        )

    def visible_to(self, user: User) -> Self:
        """The events whose page `user` may open (SPEC §6.3)."""
        return self.filter(Q(status=Event.Status.APPROVED) | Q(organizer=user))

    def search(self, text: str) -> Self:
        return self.filter(Q(title__icontains=text) | Q(description__icontains=text))

    def in_city(self, text: str) -> Self:
        return self.filter(city__icontains=text)

    def on_date(self, *, day: date) -> Self:
        # The day in the site's time zone (Europe/Rome), not in UTC.
        return self.filter(starts_at__date=day)

    def of_type(self, event_type: str) -> Self:
        return self.filter(type=event_type)

    def of_size(self, size: Size) -> Self:
        match size:
            case Size.SMALL:
                return self.filter(max_people__lte=5)
            case Size.MEDIUM:
                return self.filter(max_people__range=(6, 10))
            case Size.LARGE:
                return self.filter(max_people__gt=10)
```

- **`listed` takes `now` as an argument** (AGENTS.md, Layers). The view passes
  `timezone.now()`; a test passes a fixed time, so it never depends on the day you run it.
  "Not started" covers "not past" too: an event is past once it has started (SPEC.md §2 #34).
- **`visible_to`** says who may open an event's page: approved events for everyone, any event
  for its organizer. Issue 013 adds "a cancelled event, for the people who were on it".
  Pending, rejected and cancelled events are covered by the organizer's `Q`.
- **`icontains`** is "contains, ignoring case": `avez` finds Avezzano.
- **`starts_at__date`** compares the *local* date: with `USE_TZ`, Django converts to the current
  time zone first. An event at 00:30 on Saturday in Rome is still Friday in UTC.
- **`Size` is a `TextChoices` without a field.** It names the three sizes once, for the form's
  `<select>` and for `of_size`. pyrefly checks that the `match` covers every size.
- **`type` is also a Python built-in**, so the argument is called `event_type`.

`Size` is not a model field, so there is no migration.

- [x] The methods above, each with a test (step 6).

### 2. The filter form

`events/forms.py` (import `Size` next to `Event`):

```python
class EventFilterForm(forms.Form):
    """The filters above the event list, sent with GET (SPEC §2 #29)."""

    q = forms.CharField(label="Keyword", required=False)
    city = forms.CharField(required=False)
    date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    type = forms.ChoiceField(
        choices=[("", "Any type"), *Event.Type.choices], required=False
    )
    size = forms.ChoiceField(choices=[("", "Any size"), *Size.choices], required=False)
```

A plain `forms.Form`, not a `ModelForm`: it saves nothing. Every field is optional; an empty
one means "don't filter on it". Django still does the boring part: it turns `"2027-03-05"` into
a `date`, and refuses a size that isn't one of the three.

- [x] `EventFilterForm` as above.

### 3. The views

Replace the top of `events/views.py` (the imports) and add the two views above `event_new`:

```python
from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from events.forms import EventFilterForm, EventForm
from events.models import Event, Size
from events.services import event_create


def event_list(request: HttpRequest) -> HttpResponse:
    form = EventFilterForm(request.GET)
    events = Event.objects.listed(now=timezone.now())
    if form.is_valid():
        data = form.cleaned_data
        if data["q"]:
            events = events.search(data["q"])
        if data["city"]:
            events = events.in_city(data["city"])
        if data["date"]:
            events = events.on_date(day=data["date"])
        if data["type"]:
            events = events.of_type(data["type"])
        if data["size"]:
            events = events.of_size(Size(data["size"]))
    return render(request, "events/event_list.html", {"form": form, "events": events})


def event_detail(request: HttpRequest, pk: int) -> HttpResponse:
    user = request.user
    if not isinstance(user, User):
        raise Http404
    event = get_object_or_404(
        Event.objects.visible_to(user).select_related("organizer"), pk=pk
    )
    return render(request, "events/event_detail.html", {"event": event})
```

- **`EventFilterForm(request.GET)`** binds the form to the URL's values. With no values at all
  it is valid and filters nothing. With a wrong value (`?size=huge`) it isn't valid: the list
  shows every event, and the form shows the error.
- **Each `if` adds one filter** to the same QuerySet. Nothing runs until the template loops over
  `events`.
- **`Size(data["size"])`** turns the string from the form back into a `Size`.
- **`get_object_or_404` on `visible_to(user)`**: an event you may not see is a 404, exactly like
  one that doesn't exist. A 403 ("forbidden") would tell a stranger that event 12 exists
  (AGENTS.md, Views).
- **`select_related("organizer")`** loads the organizer in the same query, because the page shows
  their name and photo.
- **`isinstance(user, User)`**: as in 010, it tells pyrefly that `user` is our `User`
  (`LoginRequiredMiddleware` already turned anonymous visitors away). Staff may see this page.

`events/urls.py` gets the two new paths:

```python
urlpatterns: list[URLPattern] = [
    path("", views.event_list, name="home"),
    path("events/new/", views.event_new, name="event_new"),
    path("events/<int:pk>/", views.event_detail, name="event_detail"),
]
```

Then remove the placeholder: the `path("", views.home, name="home")` line in `config/urls.py`,
the `home` view in `config/views.py` (and the imports only it used), and `templates/home.html`.
The login redirect (`LOGIN_REDIRECT_URL = "/"`) and the "Events" link in the navigation now
lead to the list.

- [x] `/` is the event list, `/events/<id>/` the event page; the placeholder is gone.

### 4. The templates

The structure; style it with your UI library (issue 003).

`events/templates/events/event_list.html`:

```django
{% extends "base.html" %}

{% block title %}Events · AMFI Meetups{% endblock %}

{% block content %}
<main id="main">
  <h1>Events</h1>

  <form method="get" role="search">
    {{ form }}
    <button type="submit">Search</button>
    <a href="{% url 'home' %}">Clear</a>
  </form>

  {% for event in events %}
    {% partialdef event_card inline %}
    <article>
      <img src="{{ event.photo.url }}" alt="">
      <p>{{ event.get_type_display }} · {{ event.language }}</p>
      <p><time datetime="{{ event.starts_at|date:'c' }}">{{ event.starts_at|date:"D j M, H:i" }}</time></p>
      <h2><a href="{% url 'event_detail' event.pk %}">{{ event.title }}</a></h2>
      <p>{{ event.city }} · {{ event.place }}</p>
      <p>Up to {{ event.max_people }} people</p>
      {% if event.status != "approved" %}<span>{{ event.get_status_display }}</span>{% endif %}
    </article>
    {% endpartialdef %}
  {% empty %}
    <p>No events match. Try fewer filters, or create one!</p>
  {% endfor %}
</main>
{% endblock %}
```

- **`{% partialdef event_card inline %}`** defines the card *and* renders it right there, once per
  event. Issue 016 shows the same card on "My events" with
  `{% include "events/event_list.html#event_card" %}`, so the card's markup lives in one place.
  The status badge never shows on this list (it only has approved events); it is for 016.
- **`{% empty %}`** is the `for` loop's "there was nothing to loop over".
- **`<time datetime="…">`** gives the machine-readable date next to the human one.
- **`event.photo.url`** is `/media/photos/events/…`, served to logged-in users by issue 006's
  `media` view. `alt=""` because the title right below says what the event is.

`events/templates/events/event_detail.html`:

```django
{% extends "base.html" %}

{% block title %}{{ event.title }} · AMFI Meetups{% endblock %}

{% block content %}
<main id="main">
  {% if event.status == "pending" %}
    <p>AMFI is reviewing this event. Only you can see it for now.</p>
  {% elif event.status == "rejected" %}
    <p>AMFI didn't approve this event. The reason: {{ event.review_note|linebreaksbr }}</p>
  {% elif event.status == "cancelled" %}
    <p>This event was cancelled.</p>
  {% endif %}

  <img src="{{ event.photo.url }}" alt="">
  <h1>{{ event.title }}</h1>
  <p>{{ event.get_type_display }} · We will speak {{ event.language }}</p>
  <p><time datetime="{{ event.starts_at|date:'c' }}">{{ event.starts_at|date:"l j F Y, H:i" }}</time></p>
  <p>{{ event.city }} · {{ event.place }}</p>
  <p>{{ event.description|linebreaksbr }}</p>

  <h2>Going (1 of {{ event.max_people }})</h2>
  <ul>
    <li>
      {% if event.organizer.is_staff %}
        AMFI
      {% elif event.organizer.deleted_at %}
        Deleted student
      {% else %}
        <a href="{% url 'student_detail' event.organizer.pk %}">
          <img src="{{ event.organizer.photo.url }}" alt="" width="48" height="48">
          {{ event.organizer.full_name }}
        </a>
      {% endif %}
      (organizer)
    </li>
  </ul>
</main>
{% endblock %}
```

Only the organizer ever sees a pending or rejected event (`visible_to`), so the status lines
need no "is this the organizer?" check. `linebreaksbr` keeps the organizer's line breaks; it
escapes the text first, so it is safe on user input (unlike `|safe`).

- [x] The list shows cards and filters; the page shows the details and the organizer.

### 5. One smoke test changes

`tests/test_smoke.py` looked for the placeholder's "Open the admin" link on the home page. The
list doesn't have it, so remove that line from
`test_login_lands_on_home_and_logout_returns_to_login`:

```python
assert reverse("admin:index").encode() in home.content
```

The rest of that test (the user's email in the header, `aria-current="page"`, the logout form)
still holds. Staff reach the admin at `/admin/`.

### 6. Tests

`tests/events/test_list.py`. The QuerySet tests use a fixed `NOW`, so they pass on any day:

```python
from collections.abc import Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.test import Client
from pytest_django import DjangoAssertNumQueries

from accounts.models import User
from events.models import Event, Size

pytestmark = pytest.mark.django_db

NOW = datetime(2027, 3, 1, 12, 0, tzinfo=ZoneInfo("Europe/Rome"))


def test_listed_is_approved_and_not_started_soonest_first(
    make_event: Callable[..., Event],
) -> None:
    make_event(title="Later", starts_at=NOW + timedelta(days=2))
    make_event(title="Sooner", starts_at=NOW + timedelta(days=1))
    make_event(title="Started", starts_at=NOW - timedelta(minutes=1))
    for status in (Event.Status.PENDING, Event.Status.REJECTED, Event.Status.CANCELLED):
        make_event(starts_at=NOW + timedelta(days=1), status=status)

    listed = Event.objects.listed(now=NOW)

    assert [event.title for event in listed] == ["Sooner", "Later"]


def test_search_looks_in_title_and_description(
    make_event: Callable[..., Event],
) -> None:
    make_event(title="Pizza night")
    make_event(title="Hike", description="Bring PIZZA for lunch.")
    make_event(title="Museum")

    found = Event.objects.search("pizza")

    assert {event.title for event in found} == {"Pizza night", "Hike"}


def test_in_city_matches_part_of_the_name(make_event: Callable[..., Event]) -> None:
    make_event(title="Here", city="Avezzano")
    make_event(title="There", city="Roma")

    assert [event.title for event in Event.objects.in_city("avez")] == ["Here"]


def test_on_date_uses_the_local_day(make_event: Callable[..., Event]) -> None:
    rome = NOW.tzinfo
    make_event(title="Evening", starts_at=datetime(2027, 3, 5, 21, 0, tzinfo=rome))
    # 00:30 in Rome is still 23:30 of the day before in UTC.
    make_event(title="Late", starts_at=datetime(2027, 3, 6, 0, 30, tzinfo=rome))

    found = Event.objects.on_date(day=date(2027, 3, 5))

    assert [event.title for event in found] == ["Evening"]


def test_of_type(make_event: Callable[..., Event]) -> None:
    make_event(title="Pizza", type=Event.Type.FOOD)
    make_event(title="Hike", type=Event.Type.TRIP)

    assert [event.title for event in Event.objects.of_type("trip")] == ["Hike"]


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (Size.SMALL, {"2", "5"}),
        (Size.MEDIUM, {"6", "10"}),
        (Size.LARGE, {"11", "100"}),
    ],
)
def test_of_size(
    make_event: Callable[..., Event], size: Size, expected: set[str]
) -> None:
    for max_people in (2, 5, 6, 10, 11, 100):
        make_event(title=str(max_people), max_people=max_people)

    assert {event.title for event in Event.objects.of_size(size)} == expected


def test_the_list_page_filters_with_get(
    client: Client, make_student: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    make_event(title="Pizza night", city="Avezzano")
    make_event(title="Pizza in Rome", city="Roma")
    client.force_login(make_student())

    response = client.get("/", {"q": "pizza", "city": "roma"})

    assert response.status_code == 200
    assert b"Pizza in Rome" in response.content
    assert b"Pizza night" not in response.content


def test_a_wrong_filter_value_shows_an_error(
    client: Client, make_student: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    make_event(title="Pizza night")
    client.force_login(make_student())

    response = client.get("/", {"size": "huge"})

    assert b"Select a valid choice" in response.content
    assert b"Pizza night" in response.content


def test_the_list_page_runs_a_fixed_number_of_queries(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    for _ in range(3):
        make_event()
    client.force_login(make_student())

    # The session, the logged-in user, and the events: however many events there are.
    with django_assert_num_queries(3):
        response = client.get("/")

    assert response.content.count(b"<article") == 3
```

The last test is the one AGENTS.md asks of every list page. If someone later shows the
organizer's name on the card without `select_related`, it fails with 6 queries instead of 3, and
the failure message lists them. Note how each test writes out only the fields it is about;
`make_event` fills in the rest.

`tests/events/test_detail.py`:

```python
from collections.abc import Callable

import pytest
from django.test import Client
from django.utils import timezone

from accounts.models import User
from events.models import Event

pytestmark = pytest.mark.django_db


def test_an_approved_event_is_visible_to_everyone(
    client: Client, make_staff: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    event = make_event(title="Pizza night")
    client.force_login(make_staff())

    response = client.get(f"/events/{event.pk}/")

    assert response.status_code == 200
    assert b"Pizza night" in response.content
    assert event.organizer.full_name.encode() in response.content


@pytest.mark.parametrize(
    "status", [Event.Status.PENDING, Event.Status.REJECTED, Event.Status.CANCELLED]
)
def test_only_the_organizer_sees_an_event_that_is_not_approved(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    status: Event.Status,
) -> None:
    event = make_event(status=status)

    client.force_login(make_student())
    assert client.get(f"/events/{event.pk}/").status_code == 404

    client.force_login(event.organizer)
    assert client.get(f"/events/{event.pk}/").status_code == 200


def test_the_organizer_sees_why_it_was_rejected(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.REJECTED, review_note="Add the address.")
    client.force_login(event.organizer)

    response = client.get(f"/events/{event.pk}/")

    assert b"Add the address." in response.content


def test_an_unknown_event_is_a_404(
    client: Client, make_student: Callable[..., User]
) -> None:
    client.force_login(make_student())

    assert client.get("/events/999/").status_code == 404


def test_an_event_by_staff_shows_amfi_as_organizer(
    client: Client,
    make_student: Callable[..., User],
    make_staff: Callable[..., User],
    make_event: Callable[..., Event],
) -> None:
    staff = make_staff(full_name="Staff Person")
    event = make_event(organizer=staff)
    client.force_login(make_student())

    response = client.get(f"/events/{event.pk}/")

    assert b"AMFI" in response.content
    assert b"Staff Person" not in response.content


def test_a_deleted_organizer_is_shown_as_deleted_student(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
) -> None:
    organizer = make_student(full_name="Gone Student", deleted_at=timezone.now())
    event = make_event(organizer=organizer)
    client.force_login(make_student())

    response = client.get(f"/events/{event.pk}/")

    assert b"Deleted student" in response.content
    assert b"Gone Student" not in response.content
```

- [x] The tests above pass.
- [x] `scripts/check.sh` passes.

## Done when

- [x] `/` lists approved events that haven't started, soonest first; pending, rejected, cancelled
      and started ones are not there (test).
- [x] Keyword, city, date, type and size each filter the list (a test each); a wrong value shows
      an error instead of a crash (test).
- [x] The list page runs 3 queries, however many events there are (test).
- [x] The event page: approved events for every logged-in user; pending, rejected and cancelled
      ones for their organizer only, with the reason when rejected; 404 otherwise (tests).
- [x] The organizer shows as "AMFI" for staff and "Deleted student" after a soft delete (tests).
- [x] The card is the `event_card` partial in `events/event_list.html`.
- [x] The placeholder `home` view and `templates/home.html` are gone.
- [x] `scripts/check.sh` passes.
- [x] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 012-event-list-and-event-page
```

Suggested commits:
1. `Add the event list's QuerySet methods`
2. `Show the event list with filters at /`
3. `Add the event page`
4. `Close 012 in the issue`

Open a pull request titled "The event list with filters, and the event page". Show the list on a
phone-sized window with a filter applied, and an event page. Ask the reviewer to try opening a
pending event of someone else by its URL. `docs/workflow/git.md` has every step.

## Watch out

- **Never `.all()` and then filter in Python** (`[e for e in events if e.city == …]`). That
  loads every event to keep three. Each filter belongs in the QuerySet, where the database does
  it.
- **Use `timezone.now()`, not `date.today()` or `datetime.now()`.** Those know nothing about time
  zones; a comparison with an aware datetime is an error, and around midnight the day is wrong.
- **`?q=` and `?city=` are user input.** Django escapes them when the form shows them again, and
  the ORM passes them to the database as parameters, so neither HTML nor SQL can be injected.
  Never build SQL with f-strings, and never use `|safe` on them.
- **`if data["date"]:`, not `if "date" in data:`.** An empty filter is in `cleaned_data` too, as
  `""` or `None`.
- **The order of the URLs:** `events/new/` must not be caught by `events/<int:pk>/`. It isn't,
  because `new` isn't an `int`; with `<str:…>` it would be.
- **A partial inside a loop renders with the loop's variables.** The page that includes it must
  name the object `event` too (`{% for event in … %}`).

## Worked example

- [06, N+1 queries](../docs/examples/06-n-plus-one-queries.md): after step 6, break the
  query-count test on purpose, read the queries it prints, and fix them with `select_related`.

## Further reading

- [Django: Making queries](https://docs.djangoproject.com/en/6.1/topics/db/queries/)
  (QuerySets are lazy; `Q` objects).
- [Django: QuerySet API reference](https://docs.djangoproject.com/en/6.1/ref/models/querysets/),
  especially the lookups `icontains`, `date`, `range`, and `select_related`.
- [Django: Managers, "Calling custom QuerySet methods from the manager"](https://docs.djangoproject.com/en/6.1/topics/db/managers/#calling-custom-queryset-methods-from-the-manager).
- [Django: Template partials](https://docs.djangoproject.com/en/6.1/ref/templates/language/#template-partials)
  and the [`partialdef` tag](https://docs.djangoproject.com/en/6.1/ref/templates/builtins/#partialdef).
- [Django: Time zones](https://docs.djangoproject.com/en/6.1/topics/i18n/timezones/).
- [pytest-django: `django_assert_num_queries`](https://pytest-django.readthedocs.io/en/latest/helpers.html#django-assert-num-queries).
- [MDN: GET or POST for forms](https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Forms/Sending_and_retrieving_form_data#the_get_method).
- [Django tutorial, part 3](https://docs.djangoproject.com/en/6.1/intro/tutorial03/): a list page
  and a detail page with `get_object_or_404`, the shape of this issue, on a small example.
- [Django: Database access optimization](https://docs.djangoproject.com/en/6.1/topics/db/optimization/):
  when a QuerySet runs, what it caches, and loading related objects at once.
- [Django: Search](https://docs.djangoproject.com/en/6.1/topics/db/search/): `icontains` as the
  simplest search, and where it stops being enough.
- [Django: Returning errors](https://docs.djangoproject.com/en/6.1/topics/http/views/#returning-errors):
  `Http404`, our answer for an event you may not see.
