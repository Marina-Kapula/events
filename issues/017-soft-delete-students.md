# Soft delete a student

Status: todo · Opened: 2026-11-21 · Milestone: M3 · Depends on: 013, 015

## Why

Sometimes a student must leave the app: they asked to, they went home early, or they broke the
rules. Deleting the row for real would break things: the events they organized point at them
(`organizer` is `PROTECT`), and past events would lose their history.

A **soft delete** keeps the row but closes the account (SPEC.md §2 #32, §6.7): the student can't
log in, their profile disappears, their upcoming events are cancelled with the usual emails, and
they leave every event they joined, so the waiting lists move up. Past events they organized
stay, with the organizer shown as "Deleted student". AMFI does it from the Users page of the
admin, with an action that asks for confirmation first.

## What you'll build

- The service `accounts.services.user_soft_delete(*, user, now)`.
- An admin action "Soft delete the selected students", with a confirmation page.
- Tests for every effect: the account, the events, the participations and waiting lists, the
  profile page, "Deleted student", the login.

Not in this issue: a real erasure. If someone asks for their data to be erased, an admin deletes
the student's events in the admin, then the student (§2 #32).

## Before you start

Read:
- SPEC.md §2 #27, #32; §4 (the one exception to "accounts never imports events"); §6.7; §8
  (Users).
- AGENTS.md: Layers, Django (`transaction.atomic`).
- `docs/learn/transactions-and-race-conditions.md`: why the whole soft delete is one
  transaction, with the emails sent after the commit.
- [Django: Admin actions](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/actions/),
  especially [Actions that provide intermediate pages](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/actions/#actions-that-provide-intermediate-pages).

What you use from earlier issues: `User.deleted_at` (002); `accounts/services.py` (008) and
`student_detail` (009); `Event`, `Participation`, `waiting_list_move_up` (013); `event_cancel`
(015); 012's "Deleted student" on the event page.

Words you'll meet:
- **Soft delete**: marking a row as deleted (`deleted_at`, `is_active = False`) instead of
  removing it from the database.
- **Admin action**: an entry of the "Action" menu above an admin list; it runs on the rows you
  ticked.
- **Intermediate page**: a page an action shows *before* it does anything, to ask "are you
  sure?". Django's own "Delete selected" does this.

## Steps

### 1. The service

Add to `accounts/services.py` (008 created it):

```python
from datetime import datetime

from django.db import transaction

from accounts.models import User

# The one place accounts uses events (SPEC.md §4): a deleted student's events and
# sign-ups must follow the events rules, emails included.
from events.models import Event, Participation
from events.services import event_cancel, waiting_list_move_up


@transaction.atomic
def user_soft_delete(*, user: User, now: datetime) -> None:
    """Closes a student's account but keeps the row (SPEC.md §6.7)."""
    upcoming = Event.objects.filter(organizer=user, starts_at__gt=now).exclude(
        status=Event.Status.CANCELLED
    )
    for event in upcoming:
        event_cancel(event=event, by=user, now=now)

    participations = Participation.objects.filter(user=user).select_related("event")
    events = [participation.event for participation in participations]
    participations.delete()
    for event in events:
        if event.status == Event.Status.APPROVED and event.starts_at > now:
            waiting_list_move_up(event=event)

    user.is_active = False
    user.deleted_at = now
    user.full_clean()
    user.save()
```

Why each piece is there:

- **`event_cancel`, not `status = "cancelled"`.** The service from 015 deletes the pending
  change and emails everyone going or waiting. Setting the status by hand would skip both: that
  is why rules live in services, and why this is the one place `accounts` imports `events`
  (SPEC.md §4).
- **`by=user`**: the student cancels their own events, as the organizer, before they start, so
  015's rule ("the organizer, before the start") holds. Pending and rejected events are upcoming
  too, and are cancelled the same way. Past events are left alone.
- **The events are read before the participations are deleted.** Once the rows are gone, there
  is no way back to their events.
- **The waiting list moves up only on approved events that haven't started.** On a past event
  there is nothing to join any more; on a cancelled one, "you got a spot" would be a lie (013's
  `waiting_list_move_up` doesn't check that itself).
- **`is_active = False`** is what keeps them out: Django's login refuses inactive users, and a
  student who is logged in on their phone is logged out at their next click (Django checks
  `is_active` again on every request).
- **`full_clean()` before `save()`** (AGENTS.md): the student keeps their full profile, so the
  `CheckConstraint` of 002 still passes.
- **`transaction.atomic`**: all of it, or nothing. The emails of `event_cancel` and
  `waiting_list_move_up` wait in `on_commit` until the end.

- [ ] `user_soft_delete` as above.

### 2. The admin action, with a confirmation page

Soft deleting can't be undone from the app, so the action asks first, as Django's own "Delete
selected" does. In `accounts/admin.py`, on `UserAdmin`:

```python
    actions = ("soft_delete",)

    @admin.action(description="Soft delete the selected students")
    def soft_delete(
        self, request: HttpRequest, queryset: QuerySet[User]
    ) -> TemplateResponse | None:
        students = list(queryset.filter(is_staff=False, deleted_at=None))
        if "confirm" not in request.POST:
            # First click: show what will happen, and ask again.
            return TemplateResponse(
                request,
                "admin/accounts/user/soft_delete_confirmation.html",
                {
                    **self.admin_site.each_context(request),
                    "title": "Soft delete these students?",
                    "students": students,
                    "action_checkbox_name": ACTION_CHECKBOX_NAME,
                },
            )
        now = timezone.now()
        for student in students:
            user_soft_delete(user=student, now=now)
        self.message_user(
            request,
            f"Soft deleted {len(students)} student(s). Their upcoming events are "
            "cancelled and everyone on them was emailed.",
            messages.SUCCESS,
        )
        return None
```

The imports this needs:

```python
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.db.models import QuerySet
from django.template.response import TemplateResponse
from django.utils import timezone

from accounts.services import user_soft_delete
```

And the page, `accounts/templates/admin/accounts/user/soft_delete_confirmation.html`:

```django
{% extends "admin/base_site.html" %}

{% block content %}
<p>For each student below:</p>
<ul>
  <li>the account is closed: they can't log in, and their profile page is gone;</li>
  <li>their events that haven't started are cancelled, and everyone going or waiting is emailed;</li>
  <li>they leave every event they joined, and the waiting lists move up.</li>
</ul>
<p>Past events they organized stay, with the organizer shown as "Deleted student".</p>
<ul>
  {% for student in students %}
    <li>{{ student.full_name }} ({{ student.email }})</li>
  {% empty %}
    <li>None: staff and students already deleted are skipped.</li>
  {% endfor %}
</ul>
<form method="post">
  {% csrf_token %}
  {% for student in students %}
    <input type="hidden" name="{{ action_checkbox_name }}" value="{{ student.pk }}">
  {% endfor %}
  <input type="hidden" name="action" value="soft_delete">
  <input type="hidden" name="confirm" value="yes">
  <input type="submit" value="Yes, soft delete">
  <a href="{% url 'admin:accounts_user_changelist' %}" class="button cancel-link">No, go back</a>
</form>
{% endblock %}
```

How the two clicks work:

1. The admin ticks students, picks "Soft delete the selected students" and presses Go. Django
   calls the action with the ticked rows. There is no `confirm` in the POST, so the action
   returns the confirmation page instead of doing anything. (An action that returns a response
   shows that response; one that returns `None` goes back to the list.)
2. The page's form posts to the same list URL, with the same action (`action`), the same rows
   (`_selected_action`, Django's name for the ticked boxes, `ACTION_CHECKBOX_NAME`) and
   `confirm=yes`. Django calls the action again; now it soft deletes, adds a message, and
   returns `None`: back to the list.

Also:

- **Staff and already deleted students are skipped** by the filter: an admin who ticks
  "everyone" can't close the admins' accounts.
- **`list(...)`**: the list is read once, shown on the page or soft deleted, and counted for the
  message.
- **`each_context(request)`** gives the page the admin's header, navigation and colours.
- **One transaction per student**: if one fails, the ones before it stay soft deleted.

- [ ] In `/admin/accounts/user/`, the action asks first, then soft deletes and says how many.

### 3. What students see afterwards

Most of it is already there; check each with the tests below:

- **The profile is a 404**: 009's `student_detail` only shows active, not deleted students.
- **"Deleted student"**: 012's event page shows it, without photo or link, for an organizer with
  a `deleted_at`.
- **No login**: Django's `ModelBackend` refuses inactive users, and 008's verification link and
  Django's password reset ignore them too (§6.1.5; `PasswordResetForm` only emails active users).
- **Gone from the going lists**: their participations are deleted.

- [ ] Each of the four checked by a test.

### 4. Tests

`tests/accounts/test_soft_delete.py`:

```python
from collections.abc import Callable
from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pytest_django import DjangoCaptureOnCommitCallbacks

from accounts.models import User
from accounts.services import user_soft_delete
from events.models import Event, Participation

pytestmark = pytest.mark.django_db


def test_the_account_is_closed(make_student: Callable[..., User]) -> None:
    student = make_student()
    now = timezone.now()

    user_soft_delete(user=student, now=now)

    student.refresh_from_db()
    assert not student.is_active
    assert student.deleted_at == now


def test_upcoming_events_are_cancelled_and_past_ones_stay(
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    student = make_student()
    now = timezone.now()
    upcoming = make_event(
        organizer=student,
        starts_at=now + timedelta(days=2),
        status=Event.Status.APPROVED,
    )
    pending = make_event(
        organizer=student,
        starts_at=now + timedelta(days=3),
        status=Event.Status.PENDING,
    )
    past = make_event(
        organizer=student,
        starts_at=now - timedelta(days=2),
        status=Event.Status.APPROVED,
    )
    going = make_participation(event=upcoming)

    with django_capture_on_commit_callbacks(execute=True):
        user_soft_delete(user=student, now=now)

    for event in (upcoming, pending, past):
        event.refresh_from_db()
    assert upcoming.status == Event.Status.CANCELLED
    assert pending.status == Event.Status.CANCELLED
    assert past.status == Event.Status.APPROVED
    assert [message.to for message in mailoutbox] == [[going.user.email]]


def test_participations_go_and_the_waiting_list_moves_up(
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    student = make_student()
    event = make_event(status=Event.Status.APPROVED, max_people=2)
    make_participation(event=event, user=student, status=Participation.Status.GOING)
    waiting = make_participation(event=event, status=Participation.Status.WAITING)

    with django_capture_on_commit_callbacks(execute=True):
        user_soft_delete(user=student, now=timezone.now())

    assert not Participation.objects.filter(user=student).exists()
    waiting.refresh_from_db()
    assert waiting.status == Participation.Status.GOING
    assert [message.to for message in mailoutbox] == [[waiting.user.email]]


def test_the_profile_is_gone_and_past_events_say_deleted_student(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
) -> None:
    student = make_student(full_name="Student One")
    past = make_event(
        organizer=student,
        starts_at=timezone.now() - timedelta(days=1),
        status=Event.Status.APPROVED,
    )
    user_soft_delete(user=student, now=timezone.now())
    client.force_login(make_student())

    assert client.get(reverse("student_detail", args=[student.pk])).status_code == 404
    page = client.get(reverse("event_detail", args=[past.pk]))
    assert b"Deleted student" in page.content
    assert b"Student One" not in page.content


def test_a_deleted_student_cannot_log_in(
    client: Client, make_student: Callable[..., User]
) -> None:
    student = make_student()
    user_soft_delete(user=student, now=timezone.now())

    response = client.post(
        reverse("login"), {"username": student.email, "password": "s3cret-pass"}
    )

    assert response.status_code == 200  # the form again, with an error
    assert "_auth_user_id" not in client.session


def test_the_admin_action_asks_first_then_soft_deletes_students_only(
    admin_client: Client,
    make_student: Callable[..., User],
    make_staff: Callable[..., User],
) -> None:
    student = make_student(full_name="Student One")
    staff = make_staff()
    url = reverse("admin:accounts_user_changelist")
    data = {"action": "soft_delete", "_selected_action": [student.pk, staff.pk]}

    page = admin_client.post(url, data)
    student.refresh_from_db()
    assert page.status_code == 200
    assert b"Student One" in page.content
    assert student.is_active

    response = admin_client.post(url, {**data, "confirm": "yes"}, follow=True)
    student.refresh_from_db()
    staff.refresh_from_db()
    assert not student.is_active
    assert staff.is_active
    assert b"Soft deleted 1 student(s)" in response.content
```

- **`now` is passed in**, so `deleted_at == now` can be checked exactly.
- **Only one email in the cancel test**: the pending event had nobody on it, and the past event
  isn't touched.
- **The admin test posts what the browser posts**: first the action form of the list, then the
  confirmation form.

- [ ] The tests above pass.
- [ ] `scripts/check.sh` passes.

## Done when

- [ ] `user_soft_delete` sets `is_active = False` and `deleted_at`, in one transaction (test).
- [ ] The student's upcoming events (pending, approved, rejected) are cancelled through
      `event_cancel`, with emails; past ones stay (test).
- [ ] Their participations are deleted, and the waiting lists of approved events that haven't
      started move up, with emails (test).
- [ ] Their profile is a 404; past events show "Deleted student"; they can't log in (tests).
- [ ] The admin action asks for confirmation, skips staff, and reports how many were soft
      deleted (test).
- [ ] `scripts/check.sh` passes.
- [ ] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 017-soft-delete-students
```

Suggested commits:
1. `Add the user_soft_delete service`
2. `Add a Soft delete action to the users admin, with a confirmation page`
3. `Close 017 in the issue`

Open a pull request titled "Soft delete a student". Add a screenshot of the confirmation page.
Ask the reviewer to check the order of the steps in `user_soft_delete`.

## Watch out

- **Don't call `participation.delete()` and forget the waiting list**, and don't move up the
  list of a past or cancelled event: the test with `max_people=2` checks the first, the status
  check in the service the second.
- **Don't import `events` anywhere else in `accounts`.** This service is the one exception
  (SPEC.md §4). Everywhere else, `events` imports `accounts`, never the other way round, or the
  two apps end up importing each other.
- **The admin's Delete button is a hard delete.** It fails for a student who organized events
  (`PROTECT`), and it sends no emails. Use the action.
- **A soft-deleted student can't come back through registration**: their email is still taken
  (`unique`). Ticking "active" again in the admin brings back the login, but nothing else: the
  profile stays hidden (009 checks `deleted_at`), the events stay cancelled, the sign-ups gone.
- **The photos stay on the server.** A soft delete hides the profile; erasing the files is part
  of a real erasure.

## Further reading

- [Django: Admin actions](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/actions/), the
  whole page.
- [Django: `ModelAdmin.message_user`](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#django.contrib.admin.ModelAdmin.message_user).
- [Django: `User.is_active`](https://docs.djangoproject.com/en/6.1/ref/contrib/auth/#django.contrib.auth.models.User.is_active):
  what an inactive user can't do.
- [Django: Database transactions](https://docs.djangoproject.com/en/6.1/topics/db/transactions/).
- [GDPR, Article 17: the right to erasure](https://gdpr-info.eu/art-17-gdpr/), for when someone
  asks for more than a soft delete.
- [Django: `ForeignKey.on_delete`](https://docs.djangoproject.com/en/6.1/ref/models/fields/#django.db.models.ForeignKey.on_delete):
  `PROTECT`, `CASCADE` and the others, and why the admin's Delete fails for an organizer.
- [Brandur Leach: Soft deletion probably isn't worth it](https://brandur.org/soft-deletion): the
  costs of soft deletes (every query must remember them), to weigh against our reasons in
  SPEC.md §2 #32.
