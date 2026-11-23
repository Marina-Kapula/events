# My events

Status: done · Opened: 2026-11-21 · Milestone: M2 · Depends on: 013, 015

## Why

A student who created an event wants to know where it stands: still in review, rejected (and
why), approved. A student who joined events wants to find them again, and see whether they got
a spot or are still waiting. Today they would have to search the list, and the list doesn't even
show pending, rejected, cancelled or past events.

"My events" is one page with two lists, "Created by me" and "Joined by me" (SPEC.md §2 #30,
docs/app-plan.md #26–27). It reuses the event card of the list, so it is mostly a view, two
QuerySet methods and a short template.

## What you'll build

- `/my-events/` (name `my_events`), for students; staff get a 404 (§6.9).
- "Created by me": every event the student organizes, in any state, with its status badge, and
  AMFI's reason when it is rejected.
- "Joined by me": every event they are going to or waiting for. Upcoming ones first, then past
  and cancelled ones. Events where they are waiting say so.
- A "My events" link in the navigation, hidden for staff.
- A test that the page runs the same number of queries however many events there are.

## Before you start

Read:
- SPEC.md §2 #27, #30; §6.3, §6.9; §7 (the screens, and the card).
- AGENTS.md: Layers (QuerySet methods), Views and templates (partials, `select_related`, the
  query-count test).
- `docs/typing/custom-querysets.md`.
- `docs/learn/models-migrations-and-querysets.md`: lookups across relations, and the N+1 problem
  the query-count test guards against.
- [Django: Conditional expressions](https://docs.djangoproject.com/en/6.1/ref/models/conditional-expressions/)
  (`Case` and `When`).
- [Django: the `partialdef` tag](https://docs.djangoproject.com/en/6.1/ref/templates/builtins/#partialdef)
  and [`include`](https://docs.djangoproject.com/en/6.1/ref/templates/builtins/#include).

What you use from earlier issues: `EventQuerySet` and the card partial `event_card` in
`events/event_list.html` (012); `Participation` (its `related_name` is `participations`) and
`EventQuerySet.with_going_count()` (013); `select_related("change")` for the "Changes pending"
badge (014); cancelled events that keep their participations (015).

Words you'll meet:
- **`Exists` and `OuterRef`**: a subquery that answers yes or no for each row ("is there a
  participation of this user for *this* event?"). You met it in 013's `visible_to`.
- **Annotation**: a computed value Django adds to each object of a QuerySet (`going_count`,
  `waiting`). Templates may read them; Python code doesn't (AGENTS.md, Typing).
- **`Case` / `When`**: an "if" inside the SQL query, here used to sort upcoming events first.

## Steps

### 1. Three QuerySet methods

In `EventQuerySet` (`events/models.py`), next to 012's and 013's methods. Add `Case` and `When`
to the `from django.db.models import ...` line.

```python
    def organized_by(self, user: User) -> Self:
        return self.filter(organizer=user)

    def joined_by(self, user: User) -> Self:
        """Events `user` is going to or waiting for; `waiting` says which."""
        mine = Participation.objects.filter(event=OuterRef("pk"), user=user)
        return self.filter(Exists(mine)).annotate(
            waiting=Exists(mine.filter(status=Participation.Status.WAITING))
        )

    def upcoming_first(self, *, now: datetime) -> Self:
        """Upcoming events first, then the past and cancelled ones; by start."""
        upcoming = Q(starts_at__gt=now) & ~Q(status=Event.Status.CANCELLED)
        return self.order_by(Case(When(upcoming, then=0), default=1), "starts_at")
```

Why each piece is there:

- **They are QuerySet methods**, not code in the view: reads live on the model (AGENTS.md,
  Layers), and each one can be tested alone. They return `Self`, so they chain:
  `Event.objects.with_going_count().joined_by(user).upcoming_first(now=now)`.
- **`joined_by` filters with `Exists`**, like 013's `visible_to`, instead of
  `filter(participations__user=user)`. That join would share the table with the `Count` of
  `with_going_count()`, and the result would depend on the order of the calls:
  `filter(participations__user=me).with_going_count()` counts only *your* participation (1
  instead of 3). A subquery adds no join, so the order doesn't matter.
- **`waiting`** is `True` where the student is on the waiting list, `False` where they are going.
  Only the template reads it.
- **`upcoming_first`** sorts by a number computed in the query: 0 for an upcoming event (not
  started, not cancelled), 1 for the rest; then by start. So: upcoming soonest first, then the
  past and cancelled ones.
- **`now` is an argument** (AGENTS.md, Layers): tests pass a fixed time.

- [x] The three methods.

### 2. The view

`events/views.py`:

```python
def my_events(request: HttpRequest) -> HttpResponse:
    user = request.user
    if not isinstance(user, User) or user.is_staff:
        raise Http404
    now = timezone.now()
    events = Event.objects.with_going_count().select_related("change")
    return render(
        request,
        "events/my_events.html",
        {
            "created": events.organized_by(user).upcoming_first(now=now),
            "joined": events.joined_by(user).upcoming_first(now=now),
        },
    )
```

and in `events/urls.py`:

```python
path("my-events/", views.my_events, name="my_events"),
```

- **Staff get a 404** (§6.9): they organize nothing on the student pages and join nothing.
- **`events` holds what the card needs**, as on the list page: the number of people going (013)
  and the pending change (014), both loaded in the same query as the events. Without them each
  card would run one or two more queries.
- **Nothing runs until the template loops.** `events` is only a recipe; each list adds its own
  filter and order, and the database runs one query per list.

- [x] `my_events` and its URL.

### 3. The template

`events/templates/events/my_events.html`. The structure; style it with your UI library:

```django
{% extends "base.html" %}

{% block title %}My events · AMFI Meetups{% endblock %}

{% block content %}
<main id="main">
  <h1>My events</h1>

  <section aria-labelledby="created-title">
    <h2 id="created-title">Created by me</h2>
    {% for event in created %}
      {% include "events/event_list.html#event_card" %}
      {% if event.status == "rejected" %}
        <p>Why AMFI rejected it: {{ event.review_note }}</p>
      {% endif %}
    {% empty %}
      <p>You haven't created an event yet. <a href="{% url 'event_new' %}">Create one</a>.</p>
    {% endfor %}
  </section>

  <section aria-labelledby="joined-title">
    <h2 id="joined-title">Joined by me</h2>
    {% for event in joined %}
      {% include "events/event_list.html#event_card" %}
      {% if event.waiting %}<p>You are on the waiting list.</p>{% endif %}
    {% empty %}
      <p>You haven't joined an event yet. <a href="{% url 'home' %}">Find one</a>.</p>
    {% endfor %}
  </section>
</main>
{% endblock %}
```

- **`{% include "events/event_list.html#event_card" %}`** renders the card defined by
  `{% partialdef event_card %}` in the list template (012), with the current `event`. One card,
  two pages: change it once and both follow (SPEC.md §7, AGENTS.md: partials, not
  `_fragment.html` files).
- **The status badge is already in the card** (012, and "Changes pending" from 014): on the list
  it never shows, because the list has only approved events; here it does.
- **The reason only when `rejected`** (§2 #30). A *change* that AMFI rejected leaves the event
  `approved`, and its reason went to the organizer by email only (014).
- **`{% empty %}`** gives each list a friendly line, with a link to what to do next.
- **Two `<section>`s with headings**: screen-reader users can jump between them.

- [x] The page shows both lists with cards, badges, the reason and the waiting line.

### 4. The navigation link

In `templates/base.html` (both navigations, if 003 gave you a top bar and a bottom bar on
phones), after "Events", for students only (§7):

```django
{% if not user.is_staff %}
  <li><a href="{% url 'my_events' %}"{% if request.resolver_match.url_name == 'my_events' %} aria-current="page"{% endif %}>My events</a></li>
{% endif %}
```

`aria-current="page"` marks the link of the page you are on, as for "Events"; add your UI
library's "active" class next to it, as 003 did.

- [x] Students see "My events" in the navigation; staff don't.

### 5. Tests

`tests/events/test_my_events.py`:

```python
from collections.abc import Callable
from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pytest_django import DjangoAssertNumQueries

from accounts.models import User
from events.models import Event, Participation

pytestmark = pytest.mark.django_db


def test_created_has_every_own_event_and_the_reason_when_rejected(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
) -> None:
    me = make_student()
    soon = timezone.now() + timedelta(days=1)
    make_event(
        organizer=me,
        title="Pasta night",
        starts_at=soon + timedelta(days=1),
        status=Event.Status.APPROVED,
    )
    make_event(
        organizer=me,
        title="Pizza night",
        starts_at=soon,
        status=Event.Status.REJECTED,
        review_note="Add the place.",
    )
    make_event(title="Someone else's")
    client.force_login(me)

    response = client.get(reverse("my_events"))

    created = [event.title for event in response.context["created"]]
    assert created == ["Pizza night", "Pasta night"]
    assert b"Add the place." in response.content


def test_joined_has_upcoming_events_first_then_past_and_cancelled(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    me = make_student()
    now = timezone.now()
    approved = Event.Status.APPROVED
    events = [
        make_event(title="Past", starts_at=now - timedelta(days=3), status=approved),
        make_event(
            title="Next week", starts_at=now + timedelta(days=7), status=approved
        ),
        make_event(
            title="Cancelled",
            starts_at=now + timedelta(days=1),
            status=Event.Status.CANCELLED,
        ),
        make_event(
            title="Tomorrow", starts_at=now + timedelta(days=1), status=approved
        ),
    ]
    for event in events:
        make_participation(event=event, user=me)
    Participation.objects.filter(event__title="Next week").update(
        status=Participation.Status.WAITING
    )
    make_event(title="Not joined")
    client.force_login(me)

    response = client.get(reverse("my_events"))

    joined = [event.title for event in response.context["joined"]]
    assert joined == ["Tomorrow", "Next week", "Past", "Cancelled"]
    assert b"You are on the waiting list." in response.content
    # The organizer and me where I'm going; only the organizer where I'm waiting.
    assert response.content.count(b"2 / 8 spots") == 3
    assert response.content.count(b"1 / 8 spots") == 1


def test_joined_by_counts_everyone_going_in_either_order(
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    me = make_student()
    event = make_event(status=Event.Status.APPROVED)
    for student in (me, make_student(), make_student()):
        make_participation(event=event, user=student)

    # Three going, whichever method runs first. A joined_by written as
    # filter(participations__user=me) counts 1 in the first order (worked example 10).
    assert Event.objects.joined_by(me).with_going_count().filter(going_count=3).exists()
    assert Event.objects.with_going_count().joined_by(me).filter(going_count=3).exists()


def test_my_events_runs_the_same_queries_for_any_number_of_events(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    me = make_student()
    for _ in range(3):
        make_event(organizer=me)
        make_participation(event=make_event(), user=me)
    client.force_login(me)

    # The session, the user, then one query per list.
    with django_assert_num_queries(4):
        client.get(reverse("my_events"))


def test_students_see_the_link_and_staff_get_a_404(
    client: Client, make_student: Callable[..., User], make_staff: Callable[..., User]
) -> None:
    link = f'href="{reverse("my_events")}"'.encode()

    client.force_login(make_student())
    assert link in client.get(reverse("home")).content
    client.force_login(make_staff())
    assert link not in client.get(reverse("home")).content
    assert client.get(reverse("my_events")).status_code == 404
```

- **`response.context["created"]`** is the QuerySet the view gave the template: the test checks
  what is in it and in which order, not how it looks.
- **The spots line** ("2 / 8 spots") checks that `going_count` is right on this page too.
- **The either-order test** puts three people on one event: with only you on each event, a
  wrong `joined_by` still counts 1 and every other test passes. It filters on `going_count`
  instead of reading `event.going_count`, which pyrefly can't type (AGENTS.md, Typing).
- **`django_assert_num_queries(4)`** fails, and lists the queries, if someone later shows
  something on the card without loading it in the view. Try it: remove `with_going_count()` and
  run the test.

- [x] The tests above pass.
- [x] `scripts/check.sh` passes.

## Done when

- [x] `/my-events/` lists the student's own events in every state, with the badge, and the reason
      for rejected ones (test).
- [x] It lists the events they joined, going or waiting, upcoming first, then past and cancelled;
      waiting ones say so (test).
- [x] Cards are the list's `event_card` partial, with the right spots (test).
- [x] The page runs 4 queries, however many events there are (test).
- [x] Students have a "My events" link; staff have no link and get a 404 (test).
- [x] `scripts/check.sh` passes.
- [x] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 016-my-events
```

Suggested commits:
1. `Add organized_by, joined_by and upcoming_first to EventQuerySet`
2. `Add the My events page`
3. `Link My events in the navigation`
4. `Close 016 in the issue`

Open a pull request titled "My events". Add a screenshot of the page with a rejected event and
a cancelled one.

## Watch out

- **Same card, same data.** If the card ever shows something new (the organizer's name, for
  example), both views must load it: `event_list` and `my_events`. The query-count tests of both
  pages catch a forgotten one.
- **Don't read `event.waiting` or `event.going_count` in Python.** pyrefly doesn't know they
  exist; templates may read them (AGENTS.md, Typing).
- **A cancelled event that hasn't started yet is not "upcoming"**: `upcoming_first` puts it with
  the past ones, as SPEC.md §2 #30 says.
- **`include` with a `#`**: `"events/event_list.html#event_card"` is a template name plus a
  partial name. A typo in the partial's name is an error when the page renders, so the tests
  above catch it.

## Worked example

- [10, a filter that changes the count](../docs/examples/10-a-join-that-changes-the-count.md):
  after step 1, see `filter(participations__user=me)` count 1 instead of 3, and why `joined_by`
  uses `Exists`.
- [06, N+1 queries](../docs/examples/06-n-plus-one-queries.md): if this page's query-count test
  fails, it shows how to read the printed queries.

## Further reading

- [Django: Conditional expressions](https://docs.djangoproject.com/en/6.1/ref/models/conditional-expressions/)
  (`Case`, `When`).
- [Django: `Exists()` subqueries](https://docs.djangoproject.com/en/6.1/ref/models/expressions/#exists-subqueries).
- [Django: Order of `annotate()` and `filter()`](https://docs.djangoproject.com/en/6.1/topics/db/aggregation/#order-of-annotate-and-filter-clauses):
  why the order of `annotate()` and `filter()` changes a count.
- [Django: Template partials](https://docs.djangoproject.com/en/6.1/ref/templates/builtins/#partialdef).
- [pytest-django: `django_assert_num_queries`](https://pytest-django.readthedocs.io/en/latest/helpers.html#django-assert-num-queries).
- [Django: Lookups that span relationships](https://docs.djangoproject.com/en/6.1/topics/db/queries/#lookups-that-span-relationships):
  how a lookup like `participations__user=user` becomes a join, the join `joined_by` avoids on
  purpose (step 1 says why).
- [Django: Database access optimization](https://docs.djangoproject.com/en/6.1/topics/db/optimization/):
  loading related objects at once, so each card costs no extra query.
