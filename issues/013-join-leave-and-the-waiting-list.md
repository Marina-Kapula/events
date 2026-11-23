# Join, leave and the waiting list

Status: done · Opened: 2026-11-21 · Milestone: M2 · Depends on: 012

## Why

An event page you can only look at isn't a meetup yet. Students need to **join** an event, see
who else is going, and **leave** if their plans change (SPEC.md §6.4). Events have a maximum
size, so when an event is full, "Join" becomes "Join the waiting list". When someone going
leaves, the person who has waited longest gets the spot automatically, and an email says so.
Nobody has to accept anyone (SPEC.md §2 #25).

This is where the rules of the app are, so it is where the bugs will be: the last spot, the
order of the waiting list, two people pressing Join at the same second. Every rule lives in one
service, with a test for it.

## What you'll build

- A `Participation` model: who is on which event, `going` or `waiting`.
- Three services: `participation_join`, `participation_leave` and `waiting_list_move_up`.
- Two POST-only URLs, `/events/<id>/join/` and `/events/<id>/leave/`, that redirect back to the
  event page with a message.
- On the event page: the right button (Join; Join the waiting list; Leave; Leave the waiting
  list), "Going (n of max)" with the organizer first and then everyone going (photo, name, age,
  nationality, each a link to the profile), and "Waiting: n".
- On the cards: "5 / 8 spots", where 5 is the organizer plus the people going.
- A cancelled event's page, for the people who were on it (SPEC.md §6.3).
- Emails: the organizer when someone going leaves; a student who gets a spot from the waiting
  list.

Not in this issue: the organizer's Edit and Cancel buttons (014, 015), "My events" (016), and
moving the waiting list up after approved changes (014) or a soft delete (017). They call the
same `waiting_list_move_up`.

## Before you start

Read:
- SPEC.md §2 #24–#26; §5 (`events.Participation`); §6.3; §6.4; §6.6; §7 (the buttons and the
  card); §9 (the SQLite options).
- AGENTS.md: Layers, Views and templates, Django (`transaction.atomic`, `on_commit`).
- `docs/testing/emails.md`.
- `docs/learn/transactions-and-race-conditions.md`: the race condition and its fix, step by
  step, before you read the code.
- [Django: Database transactions](https://docs.djangoproject.com/en/6.1/topics/db/transactions/),
  up to "Performing actions after commit".
- [Django: SQLite transaction behavior](https://docs.djangoproject.com/en/6.1/ref/databases/#sqlite-transaction-behavior).

Words you'll meet:
- **Transaction**: a group of database changes that happen all together or not at all.
  `with transaction.atomic():` opens one; leaving the block normally commits it, an exception
  rolls it back.
- **Race condition**: a bug that only happens when two requests run at the same moment, each
  acting on what it read before the other one wrote.
- **Write lock**: SQLite lets one connection write at a time. Whoever holds the lock writes;
  everyone else waits for it.
- **`UniqueConstraint`**: a rule in the database that no two rows have the same values in some
  columns. Here: one participation per student per event.
- **Annotation**: an extra value computed by the database for each row of a query, like
  "how many going" (`.annotate(going_count=Count(...))`).

## Steps

### 1. The model

Add to `events/models.py`, below `Event`:

```python
class Participation(models.Model):
    class Status(models.TextChoices):
        GOING = "going", "Going"
        WAITING = "waiting", "Waiting"

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="participations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="participations",
    )
    status = models.CharField(max_length=10, choices=Status.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("event", "user"), name="one_participation_per_user_and_event"
            ),
        )
        # First come, first served: the waiting list moves up in this order.
        ordering = ("created_at", "id")

    @override
    def __str__(self) -> str:
        return f"{self.user} {self.status} {self.event}"
```

- **The organizer has no participation row** (SPEC.md §2 #24). They always have a spot, so the
  spots taken are `1 + going`, and join and leave need no special case for them.
- **Leaving deletes the row** (SPEC.md §2 #26): no "left" status to filter out everywhere.
- **`UniqueConstraint`**: even if a bug (or a double click) tried to add a student twice, the
  database refuses. `full_clean()` checks it too, before saving.
- **`ordering`**: the waiting list is in `created_at` order, oldest first. `id` breaks a tie if
  two rows were created in the same microsecond.
- **`related_name="participations"`** names the way back from an event (and from a user):
  `Count("participations")` in step 2 uses it.

```sh
uv run python manage.py makemigrations events
```

- [x] `events/migrations/0002_participation.py` creates the table and the constraint.

### 2. Two QuerySet changes

At the top of `events/models.py`, import three more names:

```python
from django.db.models import Count, Exists, OuterRef, Q
```

In `EventQuerySet`, `visible_to` learns the cancelled case, and a new method counts the people
going:

```python
    def visible_to(self, user: User) -> Self:
        """The events whose page `user` may open (SPEC §6.3)."""
        is_on_it = Exists(Participation.objects.filter(event=OuterRef("pk"), user=user))
        return self.filter(
            Q(status=Event.Status.APPROVED)
            | Q(organizer=user)
            | (Q(status=Event.Status.CANCELLED) & is_on_it)
        )

    def with_going_count(self) -> Self:
        """Adds `going_count`: how many people are going, the organizer not counted."""
        return self.annotate(
            going_count=Count(
                "participations",
                filter=Q(participations__status=Participation.Status.GOING),
            )
        )
```

- **`Exists(...)` with `OuterRef("pk")`** is a subquery: "there is a participation of this user
  for *this* event". A plain `Q(participations__user=user)` would join the participations and
  return the event once per person on it.
- **`with_going_count()`** adds a `going_count` to every event in one query, so the list can
  show "5 / 8 spots" without one more query per card. Python code doesn't read `going_count`
  (pyrefly doesn't know it exists, AGENTS.md, Typing); templates may. Issue 016 calls it too,
  for the cards on "My events".

- [x] `visible_to` and `with_going_count` as above.

### 3. The services

At the top of `events/services.py`, import `partial` and `Participation` (and, if 011 isn't
merged yet, `datetime` and `ValidationError`):

```python
from datetime import datetime
from functools import partial

from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User
from config.emails import send_email
from events.models import Event, Participation
```

**Joining.** Here is the race condition this code must prevent. An event has one free spot. Two
students press Join at the same second. Both requests count "1 + 6 going < 8: a spot is free",
both insert a `going` row, and the event has 9 people out of 8.

The fix has two parts:

1. **The count and the insert are one transaction** (`with transaction.atomic():`), so no other
   write can land between them.
2. **SQLite's `IMMEDIATE` mode** (already in `config/settings.py`: `"transaction_mode":
   "IMMEDIATE"`). Normally SQLite takes its write lock at the first *write*. In `IMMEDIATE` mode
   it takes it when the transaction *starts*. So the second request stops at the `with` line and
   waits (up to `"timeout": 20` seconds) until the first one commits. Then it counts again, sees
   that the event is full, and goes on the waiting list.

Without `IMMEDIATE`, both requests would read at the same time, and the second one's write would
fail with "database is locked": an error page instead of a place on the waiting list.

```python
def participation_join(*, event: Event, user: User, now: datetime) -> Participation:
    """Put `user` on the event: going if a spot is free, else waiting (SPEC §6.4)."""
    # With SQLite's IMMEDIATE mode the transaction takes the write lock right here: a
    # second join waits until this one commits, then counts the spot we just took.
    with transaction.atomic():
        event.refresh_from_db()
        if event.status != Event.Status.APPROVED or event.starts_at <= now:
            raise ValidationError("This event is not open for sign-ups.")
        if user.is_staff:
            raise ValidationError("Staff don't join events.")
        if event.organizer == user:
            raise ValidationError("You organize this event: you already have a spot.")
        if Participation.objects.filter(event=event, user=user).exists():
            raise ValidationError("You are already on this event.")
        going = Participation.objects.filter(
            event=event, status=Participation.Status.GOING
        ).count()
        participation = Participation(
            event=event,
            user=user,
            status=Participation.Status.GOING
            if 1 + going < event.max_people
            else Participation.Status.WAITING,
        )
        participation.full_clean()
        participation.save()
    return participation
```

`event.refresh_from_db()` reads the event again *after* taking the lock: if it was cancelled a
moment ago, we see it. Every rule is checked inside the transaction for the same reason.

**Leaving, and moving the waiting list up:**

```python
def participation_leave(*, event: Event, user: User, now: datetime) -> None:
    """Take `user` off the event, going or waiting (SPEC §6.4)."""
    with transaction.atomic():
        if event.status != Event.Status.APPROVED or event.starts_at <= now:
            raise ValidationError("You can't leave this event any more.")
        participation = Participation.objects.filter(event=event, user=user).first()
        if participation is None:
            raise ValidationError("You are not on this event.")
        participation.delete()
        if participation.status == Participation.Status.GOING:
            transaction.on_commit(
                lambda: send_email(
                    to=[event.organizer.email],
                    template="events/emails/participant_left",
                    context={"event": event, "participant": user},
                )
            )
            waiting_list_move_up(event=event)


def waiting_list_move_up(*, event: Event) -> None:
    """While a spot is free, give it to whoever has waited longest (SPEC §6.4)."""
    with transaction.atomic():
        going = Participation.objects.filter(
            event=event, status=Participation.Status.GOING
        ).count()
        waiting = Participation.objects.filter(
            event=event, status=Participation.Status.WAITING
        ).select_related("user")
        for participation in waiting:
            if 1 + going >= event.max_people:
                break
            participation.status = Participation.Status.GOING
            participation.full_clean()
            participation.save()
            going += 1
            # partial, not lambda: a lambda would see the loop's last participation.
            transaction.on_commit(
                partial(
                    send_email,
                    to=[participation.user.email],
                    template="events/emails/spot_free",
                    context={"event": event, "student": participation.user},
                )
            )
```

- **Leaving a cancelled event is refused.** Its participations stay, so it stays in everyone's
  "My events" (SPEC.md §2 #27), and a move-up there would email "you got a spot" for an event
  that won't happen.
- **Only someone *going* frees a spot.** Leaving the waiting list emails nobody (SPEC.md §6.4,
  §6.6): the organizer isn't told about the waiting list.
- **`waiting_list_move_up` is its own service**, because three things free spots: a leave (here),
  approved changes that raise `max_people` (014) and a soft delete (017). It loops "while there
  is a free spot and someone waiting", so it also fills several spots at once.
- **`partial`, not `lambda`, inside the loop.** A lambda looks its variables up when it *runs*,
  after the commit, when the loop is over: every email would go to the last person. `partial`
  stores the values now. (Ruff warns about the lambda version: rule B023.)
- **`atomic` inside `atomic`** is fine: called from `participation_leave`, the inner block
  becomes part of the outer transaction (Django uses a savepoint).

The two emails. `events/templates/events/emails/participant_left_subject.txt`:

```django
{% autoescape off %}{{ participant.full_name }} left {{ event.title }}{% endautoescape %}
```

`events/templates/events/emails/participant_left.txt`:

```django
{% autoescape off %}Hi {{ event.organizer.full_name }},

{{ participant.full_name }} is no longer going to "{{ event.title }}". If someone was on the
waiting list, they have the spot now.

{{ site_url }}{% url "event_detail" event.pk %}
{% endautoescape %}
```

`events/templates/events/emails/spot_free_subject.txt`:

```django
{% autoescape off %}You got a spot: {{ event.title }}{% endautoescape %}
```

`events/templates/events/emails/spot_free.txt`:

```django
{% autoescape off %}Hi {{ student.full_name }},

A spot freed up and it's yours: you are going to "{{ event.title }}" on
{{ event.starts_at|date:"l j F, H:i" }}.

Can't make it? Leave the event, so the next person gets the spot:
{{ site_url }}{% url "event_detail" event.pk %}
{% endautoescape %}
```

- [x] The three services and four templates.

### 4. The views

Add to `events/views.py` (imports: `ValidationError`, `require_POST` from
`django.views.decorators.http`, `Participation`, and the two services):

```python
@require_POST
def event_join(request: HttpRequest, pk: int) -> HttpResponse:
    user = request.user
    if not isinstance(user, User) or user.is_staff:
        raise Http404
    event = get_object_or_404(Event.objects.visible_to(user), pk=pk)
    try:
        participation = participation_join(event=event, user=user, now=timezone.now())
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        if participation.status == Participation.Status.GOING:
            messages.success(request, "You're going. See you there!")
        else:
            messages.success(
                request,
                "The event is full: you're on the waiting list. "
                "We'll email you if a spot frees up.",
            )
    return redirect("event_detail", pk=event.pk)


@require_POST
def event_leave(request: HttpRequest, pk: int) -> HttpResponse:
    user = request.user
    if not isinstance(user, User) or user.is_staff:
        raise Http404
    event = get_object_or_404(Event.objects.visible_to(user), pk=pk)
    try:
        participation_leave(event=event, user=user, now=timezone.now())
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "You left the event.")
    return redirect("event_detail", pk=event.pk)
```

- **`@require_POST`**: joining changes data, so it must be a POST (AGENTS.md, Views). A GET gets
  "405 Method Not Allowed". Otherwise a link, a browser prefetching links, or a search engine
  could join people to events.
- **Who may do what:** staff get a 404 (SPEC.md §6.9); an event you can't see is a 404 too.
  Everything else (started, full, already on it, the organizer) is the service's job: its
  `ValidationError` comes back as an error message on the event page.
- **Always a redirect** (Post/Redirect/Get), with a message that says what happened.

`events/urls.py`:

```python
    path("events/<int:pk>/join/", views.event_join, name="event_join"),
    path("events/<int:pk>/leave/", views.event_leave, name="event_leave"),
```

Then two changes to the views from 012. `event_list` asks for the count:

```python
    events = Event.objects.listed(now=timezone.now()).with_going_count()
```

and `event_detail` loads the participations, in **one** query with their users, and works out
what the page needs:

```python
def event_detail(request: HttpRequest, pk: int) -> HttpResponse:
    user = request.user
    if not isinstance(user, User):
        raise Http404
    event = get_object_or_404(
        Event.objects.visible_to(user).select_related("organizer"), pk=pk
    )
    participations = list(
        Participation.objects.filter(event=event).select_related("user")
    )
    going = [p for p in participations if p.status == Participation.Status.GOING]
    mine = next((p for p in participations if p.user == user), None)
    return render(
        request,
        "events/event_detail.html",
        {
            "event": event,
            "going": going,
            "spots_taken": 1 + len(going),
            "waiting_count": len(participations) - len(going),
            "mine": mine,
            "is_full": 1 + len(going) >= event.max_people,
            "is_open": event.status == Event.Status.APPROVED
            and event.starts_at > timezone.now(),
        },
    )
```

The view decides the facts (open? full? am I on it?); the template only picks the button. The
service checks them all again when the button is pressed, so a stale page can't break a rule.

- [x] Join and Leave work from the event page, with a message each time.

### 5. The templates

In the card (`events/event_list.html`), the line with max people becomes:

```django
<p>{{ event.going_count|add:1 }} / {{ event.max_people }} spots</p>
```

In `events/event_detail.html`, the buttons go below the description, and the "Going" list
replaces the one from 012. The structure; style it with your UI library:

```django
  {% if is_open and event.organizer != user and not user.is_staff %}
    {% if mine %}
      <form method="post" action="{% url 'event_leave' event.pk %}">
        {% csrf_token %}
        <button type="submit">{% if mine.status == "going" %}Leave{% else %}Leave the waiting list{% endif %}</button>
      </form>
      {% if mine.status == "waiting" %}<p>You're on the waiting list. We'll email you if a spot frees up.</p>{% endif %}
    {% else %}
      <form method="post" action="{% url 'event_join' event.pk %}">
        {% csrf_token %}
        <button type="submit">{% if is_full %}Join the waiting list{% else %}Join{% endif %}</button>
      </form>
    {% endif %}
  {% endif %}

  <h2>Going ({{ spots_taken }} of {{ event.max_people }})</h2>
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
    {% for participation in going %}
      {% with student=participation.user %}
      <li>
        <a href="{% url 'student_detail' student.pk %}">
          <img src="{{ student.photo.url }}" alt="" width="48" height="48">
          {{ student.full_name }}
        </a>
        {{ student.age }} · {{ student.nationality.name }}
      </li>
      {% endwith %}
    {% endfor %}
  </ul>
  <p>Waiting: {{ waiting_count }}</p>
```

- **Each button is a small `<form method="post">`** with `{% csrf_token %}`: a POST, never a
  link (AGENTS.md, Views).
- **No buttons** for the organizer (they edit or cancel instead, 014 and 015), for staff, and
  when the event isn't open: started, cancelled, pending or rejected.
- **`student.nationality.name`**: django-countries turns `"ES"` into "Spain".
- **The waiting list shows only a number.** Who is waiting isn't anyone's business.

- [x] The page shows the right button in each state, the people going and the waiting count.

### 6. Tests

The fixture, in `tests/conftest.py` below `make_event` (import `Participation` next to
`Event`):

```python
@pytest.fixture
def make_participation(
    make_student: Callable[..., User],
) -> Callable[..., Participation]:
    def make(event: Event, **overrides: object) -> Participation:
        fields: dict[str, object] = {"status": Participation.Status.GOING, **overrides}
        if "user" not in fields:
            fields["user"] = make_student()
        participation = Participation(event=event, **fields)
        participation.full_clean()
        participation.save()
        return participation

    return make
```

A participation always belongs to an event you made first, so `event` is required:
`make_participation(event)`, `make_participation(event, status=Participation.Status.WAITING)`.

`tests/events/test_participation.py`, the rules:

```python
from collections.abc import Callable
from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.utils import timezone
from pytest_django import DjangoCaptureOnCommitCallbacks

from accounts.models import User
from events.models import Event, Participation
from events.services import (
    participation_join,
    participation_leave,
    waiting_list_move_up,
)

pytestmark = pytest.mark.django_db

GOING = Participation.Status.GOING
WAITING = Participation.Status.WAITING


def test_the_last_spot_then_the_waiting_list(
    make_student: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    event = make_event(max_people=3)  # the organizer and two more
    now = timezone.now()

    first = participation_join(event=event, user=make_student(), now=now)
    last = participation_join(event=event, user=make_student(), now=now)
    late = participation_join(event=event, user=make_student(), now=now)

    assert [first.status, last.status, late.status] == [GOING, GOING, WAITING]


def test_the_organizer_cannot_join(make_event: Callable[..., Event]) -> None:
    event = make_event()

    with pytest.raises(ValidationError, match="You organize this event"):
        participation_join(event=event, user=event.organizer, now=timezone.now())


def test_staff_cannot_join(
    make_staff: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    with pytest.raises(ValidationError):
        participation_join(event=make_event(), user=make_staff(), now=timezone.now())


def test_nobody_joins_twice(
    make_event: Callable[..., Event], make_participation: Callable[..., Participation]
) -> None:
    participation = make_participation(make_event(), status=WAITING)

    with pytest.raises(ValidationError, match="already on this event"):
        participation_join(
            event=participation.event, user=participation.user, now=timezone.now()
        )


def test_a_started_event_cannot_be_joined(
    make_student: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    now = timezone.now()
    event = make_event(starts_at=now - timedelta(minutes=1))

    with pytest.raises(ValidationError, match="not open"):
        participation_join(event=event, user=make_student(), now=now)


@pytest.mark.parametrize(
    "status", [Event.Status.PENDING, Event.Status.REJECTED, Event.Status.CANCELLED]
)
def test_only_an_approved_event_can_be_joined(
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    status: Event.Status,
) -> None:
    event = make_event(status=status)

    with pytest.raises(ValidationError, match="not open"):
        participation_join(event=event, user=make_student(), now=timezone.now())


def test_leaving_frees_the_spot_for_the_first_one_waiting(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(max_people=2)
    leaving = make_participation(event, status=GOING)
    first = make_participation(event, status=WAITING)
    second = make_participation(event, status=WAITING)

    with django_capture_on_commit_callbacks(execute=True):
        participation_leave(event=event, user=leaving.user, now=timezone.now())

    assert not Participation.objects.filter(pk=leaving.pk).exists()
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.status, second.status) == (GOING, WAITING)
    assert [message.to for message in mailoutbox] == [
        [event.organizer.email],
        [first.user.email],
    ]
    assert leaving.user.full_name in mailoutbox[0].body
    assert first.user.full_name in mailoutbox[1].body


def test_leaving_the_waiting_list_emails_nobody(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    participation = make_participation(make_event(), status=WAITING)

    with django_capture_on_commit_callbacks(execute=True):
        participation_leave(
            event=participation.event, user=participation.user, now=timezone.now()
        )

    assert not Participation.objects.exists()
    assert mailoutbox == []


def test_nobody_leaves_a_started_event(
    make_event: Callable[..., Event], make_participation: Callable[..., Participation]
) -> None:
    participation = make_participation(make_event())
    later = participation.event.starts_at + timedelta(minutes=1)

    with pytest.raises(ValidationError):
        participation_leave(
            event=participation.event, user=participation.user, now=later
        )

    assert Participation.objects.exists()


def test_move_up_fills_every_free_spot_oldest_first(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(max_people=2)
    make_participation(event, status=GOING)
    waiting = [make_participation(event, status=WAITING) for _ in range(3)]
    # Two more spots, as when the admin approves a bigger event (issue 014).
    event.max_people = 4
    event.save()

    with django_capture_on_commit_callbacks(execute=True):
        waiting_list_move_up(event=event)

    for participation in waiting:
        participation.refresh_from_db()
    assert [p.status for p in waiting] == [GOING, GOING, WAITING]
    assert [message.to for message in mailoutbox] == [
        [waiting[0].user.email],
        [waiting[1].user.email],
    ]
```

`tests/events/test_participation_views.py`, the pages:

```python
from collections.abc import Callable

import pytest
from django.test import Client
from pytest_django import DjangoAssertNumQueries

from accounts.models import User
from events.models import Event, Participation

pytestmark = pytest.mark.django_db


def test_join_and_leave_redirect_to_the_event_with_a_message(
    client: Client, make_student: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    event = make_event()
    student = make_student()
    client.force_login(student)

    response = client.post(f"/events/{event.pk}/join/", follow=True)

    assert response.redirect_chain == [(f"/events/{event.pk}/", 302)]
    assert b"You&#x27;re going" in response.content
    assert Participation.objects.get().user == student

    response = client.post(f"/events/{event.pk}/leave/", follow=True)

    assert b"You left the event." in response.content
    assert not Participation.objects.exists()


def test_a_broken_rule_comes_back_as_an_error_message(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event()
    client.force_login(event.organizer)

    response = client.post(f"/events/{event.pk}/join/", follow=True)

    assert b"You organize this event" in response.content
    assert not Participation.objects.exists()


@pytest.mark.parametrize("action", ["join", "leave"])
def test_get_changes_nothing(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    action: str,
) -> None:
    event = make_event()
    client.force_login(make_student())

    assert client.get(f"/events/{event.pk}/{action}/").status_code == 405


@pytest.mark.parametrize("action", ["join", "leave"])
def test_staff_get_a_404(
    client: Client,
    make_staff: Callable[..., User],
    make_event: Callable[..., Event],
    action: str,
) -> None:
    event = make_event()
    client.force_login(make_staff())

    assert client.post(f"/events/{event.pk}/{action}/").status_code == 404


def test_someone_elses_pending_event_is_a_404(
    client: Client, make_student: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.PENDING)
    client.force_login(make_student())

    assert client.post(f"/events/{event.pk}/join/").status_code == 404


@pytest.mark.parametrize(
    ("mine", "full", "button"),
    [
        (None, False, b">Join</button>"),
        (None, True, b">Join the waiting list</button>"),
        (Participation.Status.GOING, False, b">Leave</button>"),
        (Participation.Status.WAITING, True, b">Leave the waiting list</button>"),
    ],
)
def test_the_event_page_shows_the_right_button(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mine: Participation.Status | None,
    full: bool,
    button: bytes,
) -> None:
    event = make_event(max_people=2)
    if full:
        make_participation(event, status=Participation.Status.GOING)
    student = make_student()
    if mine:
        make_participation(event, user=student, status=mine)
    client.force_login(student)

    response = client.get(f"/events/{event.pk}/")

    assert button in response.content


def test_the_organizer_sees_no_join_button(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event()
    client.force_login(event.organizer)

    response = client.get(f"/events/{event.pk}/")

    assert b"/join/" not in response.content


def test_the_event_page_lists_who_is_going(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    event = make_event(organizer=make_student(full_name="Organizer Person"))
    make_participation(event, user=make_student(full_name="Going Person"))
    make_participation(
        event,
        user=make_student(full_name="Waiting Person"),
        status=Participation.Status.WAITING,
    )
    client.force_login(make_student())

    content = client.get(f"/events/{event.pk}/").content.decode()

    assert "Going (2 of 8)" in content
    assert content.index("Organizer Person") < content.index("Going Person")
    assert "Waiting Person" not in content
    assert "Waiting: 1" in content


def test_a_cancelled_event_is_visible_to_the_people_on_it_only(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    event = make_event(status=Event.Status.CANCELLED)
    participation = make_participation(event)

    client.force_login(participation.user)
    response = client.get(f"/events/{event.pk}/")
    assert response.status_code == 200
    assert b"/leave/" not in response.content

    client.force_login(make_student())
    assert client.get(f"/events/{event.pk}/").status_code == 404


def test_the_list_shows_spots_taken_without_extra_queries(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    for _ in range(3):
        event = make_event()
        make_participation(event)
        make_participation(event, status=Participation.Status.WAITING)
    client.force_login(make_student())

    with django_assert_num_queries(3):
        response = client.get("/")

    assert response.content.count(b"2 / 8 spots") == 3
```

The messages appear HTML-escaped in the page: `You're` is `You&#x27;re` in `response.content`.
A test can't easily press Join twice at the same moment; the transaction, `IMMEDIATE` and the
unique constraint are what keep that case right, and the code review is where you check them.

- [x] The tests above pass. 012's `django_assert_num_queries` test still counts 3.
- [x] `scripts/check.sh` passes.

## Done when

- [x] Join puts a student on the event: `going` while `1 + going < max_people`, then `waiting`
      (test with the last spot).
- [x] The organizer, staff, a second join, a started event and an event that isn't approved are
      refused (tests).
- [x] Leave deletes the row before the start; someone going leaving emails the organizer and
      gives the spot to the oldest waiting, who is emailed (tests).
- [x] `waiting_list_move_up` fills every free spot, oldest first (test).
- [x] Join and leave are POST only (405 for GET), redirect to the event with a message, and 404
      for staff and for events you can't see (tests).
- [x] The event page shows the right button, the organizer first then everyone going, and
      "Waiting: n"; cards show "n / max spots" in 3 queries for the list (tests).
- [x] A cancelled event's page opens for the people on it, without buttons, and 404s for others
      (test).
- [x] `scripts/check.sh` passes.
- [x] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 013-join-leave-and-the-waiting-list
```

Suggested commits:
1. `Add the Participation model`
2. `Add the join, leave and waiting list services`
3. `Add Join and Leave buttons to the event page`
4. `Show who is going and the spots taken`
5. `Close 013 in the issue`

Open a pull request titled "Join, leave and the waiting list". Show the event page in each state
(Join, Join the waiting list, Leave, Leave the waiting list). Ask the reviewer to read
`participation_join` with the race condition in mind. `docs/workflow/git.md` has every step.

## Watch out

- **Count and insert in the same `atomic` block.** Moving the count above the `with` line looks
  harmless and brings the race condition back.
- **Don't decide the spot in the template or the view.** The page says "Join" or "Join the
  waiting list", but the service decides, at the moment of the click. The page may be minutes
  old.
- **`select_related("user")`** in `event_detail`: without it, each name in the going list is one
  more query.
- **The lambda in a loop** (see `waiting_list_move_up`): every callback would use the loop's last
  value. Use `partial`, or pass the value as a default argument.
- **`full_clean()` checks the unique constraint** with a query. The service checks "already on
  this event" first anyway, to give a friendly message instead of Django's generic one.
- **Other databases work differently.** On PostgreSQL you would lock the event row with
  `select_for_update()`; SQLite ignores that and locks the whole database instead, which is
  what `IMMEDIATE` is for.

## Worked example

- [07, the last spot](../docs/examples/07-the-last-spot-race.md): after step 3, run two joins at
  the same moment, with and without `transaction.atomic` and `IMMEDIATE`.
- [08, `on_commit` in a loop](../docs/examples/08-on-commit-in-a-loop.md): after step 6, swap the
  `partial` for a `lambda` and watch the tests catch the wrong emails.
- [06, N+1 queries](../docs/examples/06-n-plus-one-queries.md), "Try this" 1: `prefetch_related`
  for the people going.

## Further reading

- [Django: Database transactions](https://docs.djangoproject.com/en/6.1/topics/db/transactions/)
  (`atomic`, savepoints, `on_commit`).
- [Django: SQLite notes, transaction behavior](https://docs.djangoproject.com/en/6.1/ref/databases/#sqlite-transaction-behavior)
  and [SQLite: BEGIN TRANSACTION](https://www.sqlite.org/lang_transaction.html) (deferred,
  immediate, exclusive).
- [Django: Aggregation](https://docs.djangoproject.com/en/6.1/topics/db/aggregation/)
  (`annotate`, `Count` with `filter=`).
- [Django: Query expressions, `Exists` and `OuterRef`](https://docs.djangoproject.com/en/6.1/ref/models/expressions/#exists-subqueries).
- [Django: `require_POST`](https://docs.djangoproject.com/en/6.1/topics/http/decorators/#django.views.decorators.http.require_POST).
- [Python: `functools.partial`](https://docs.python.org/3/library/functools.html#functools.partial)
  and the Python FAQ: [Why do lambdas defined in a loop all return the same result?](https://docs.python.org/3/faq/programming.html#why-do-lambdas-defined-in-a-loop-with-different-values-all-return-the-same-result)
- [Adam Johnson: use `partial()` with `transaction.on_commit()`](https://adamj.eu/tech/2022/08/22/use-partial-with-djangos-transaction-on-commit/):
  the late-binding bug of `waiting_list_move_up`, shown in a loop.
- [Giovanni Collazo: Optimal SQLite settings for Django](https://gcollazo.com/optimal-sqlite-settings-for-django/):
  why `IMMEDIATE`, WAL and a timeout are in our settings.
- [SQLite: Write-Ahead Logging](https://www.sqlite.org/wal.html): readers don't block the writer,
  and there is only one writer at a time.
- [MDN: Safe HTTP methods](https://developer.mozilla.org/en-US/docs/Glossary/Safe/HTTP): why Join
  and Leave are POSTs, never links.
