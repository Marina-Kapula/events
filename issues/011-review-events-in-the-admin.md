# Approve or reject events in the admin

Status: todo · Opened: 2026-11-21 · Milestone: M2 · Depends on: 010, 012

## Why

After issue 010, a new event waits as `pending` and the AMFI staff get an email with a link to
its admin page. Now they need to act on it: **approve** it (it goes into the event list) or
**reject** it with a reason the organizer can fix (SPEC.md §6.2). Either way the organizer is
emailed (SPEC.md §6.6).

All admin work happens in Django's admin (SPEC.md §2 #15). But `status` is readonly there, on
purpose: a status typed into a form would skip the rules and the emails. So this issue adds two
buttons to the event's admin page, and each one calls a service.

## What you'll build

- Two services: `event_approve` and `event_reject`, each with its rules and its email.
- "Approve" and "Reject" buttons at the bottom of a pending event's admin page.
- Reject uses the "Review note" field as the reason; an empty reason is refused with a message.
- Approving an event that has already started is refused with a message (SPEC.md §6.2).

Not in this issue: the buttons for pending *changes* (014) and "Cancel event" (015). They go
into the same template and the same method, so this issue sets up the pattern they follow.

This issue depends on 012 too: the emails link to the event's page, `event_detail`.

## Before you start

Read:
- SPEC.md §2 #15, #33; §6.2; §6.6; §8 (Events).
- AGENTS.md: Layers (services), Django.
- `docs/testing/emails.md`.
- `docs/learn/transactions-and-race-conditions.md`: why the buttons call services instead of
  changing `status` themselves.
- [Django: Overriding admin templates](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#overriding-admin-templates).
- [Django: `ModelAdmin.response_change`](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#django.contrib.admin.ModelAdmin.response_change)
  (and the other `ModelAdmin` methods next to it).

Words you'll meet:
- **Template override**: your own copy of one of Django's templates, found first because of
  where it lives. Ours *extends* the admin's template and changes one block.
- **Block**: a named part of a template (`{% block submit_buttons_bottom %}`) that a child
  template can replace. `{{ block.super }}` puts the parent's content back in.
- **`response_change`**: the admin method that decides what happens *after* a change form was
  saved. Normally it shows "changed successfully" and goes back to the list.
- **`ValidationError`**: the exception for "this breaks a rule". Services raise it; whoever
  called them shows the message.

## Steps

### 1. The two services

Add to `events/services.py` (and at the top: `from datetime import datetime` and
`from django.core.exceptions import ValidationError`):

```python
def event_approve(*, event: Event, now: datetime) -> None:
    if event.status != Event.Status.PENDING:
        raise ValidationError("Only an event waiting for review can be approved.")
    if event.starts_at <= now:
        raise ValidationError("This event has already started: it can't be approved.")
    event.status = Event.Status.APPROVED
    event.full_clean()
    event.save()
    transaction.on_commit(
        lambda: send_email(
            to=[event.organizer.email],
            template="events/emails/event_approved",
            context={"event": event},
        )
    )


def event_reject(*, event: Event, reason: str) -> None:
    if event.status != Event.Status.PENDING:
        raise ValidationError("Only an event waiting for review can be rejected.")
    if not reason.strip():
        raise ValidationError("Write the reason for the organizer in “Review note”.")
    event.status = Event.Status.REJECTED
    event.review_note = reason.strip()
    event.full_clean()
    event.save()
    transaction.on_commit(
        lambda: send_email(
            to=[event.organizer.email],
            template="events/emails/event_rejected",
            context={"event": event},
        )
    )
```

- **Rules first, then the change.** If a rule is broken, the service raises before it touches
  anything. That is why the state checks are here and not in the admin: the next caller (a test,
  issue 017's soft delete) gets the same rules for free.
- **`now` is an argument**, not `timezone.now()` inside. The admin passes the real time; a test
  passes whatever time it needs (AGENTS.md, Layers).
- **Only `pending` can be approved or rejected.** Approving a cancelled event, or rejecting an
  approved one that people already joined, would make a mess.

The emails. `events/templates/events/emails/event_approved_subject.txt`:

```django
{% autoescape off %}Your event is online: {{ event.title }}{% endautoescape %}
```

`events/templates/events/emails/event_approved.txt`:

```django
{% autoescape off %}Hi {{ event.organizer.full_name }},

AMFI approved your event "{{ event.title }}". It is in the event list now, and other students
can join it:
{{ site_url }}{% url "event_detail" event.pk %}
{% endautoescape %}
```

`events/templates/events/emails/event_rejected_subject.txt`:

```django
{% autoescape off %}Your event needs changes: {{ event.title }}{% endautoescape %}
```

`events/templates/events/emails/event_rejected.txt`:

```django
{% autoescape off %}Hi {{ event.organizer.full_name }},

AMFI didn't approve your event "{{ event.title }}". The reason:

{{ event.review_note }}

You can edit the event and send it again, or cancel it:
{{ site_url }}{% url "event_detail" event.pk %}
{% endautoescape %}
```

(Editing and cancelling come in 014 and 015; the event page from 012 already shows the reason to
the organizer.)

- [ ] `event_approve`, `event_reject` and the four templates.

### 2. The buttons

Django's admin looks for a change form template in several places, most specific first:
`admin/<app>/<model>/change_form.html`, then `admin/<app>/change_form.html`, then its own
`admin/change_form.html`. Put ours at
`events/templates/admin/events/event/change_form.html`:

```django
{% extends "admin/change_form.html" %}

{% block submit_buttons_bottom %}
{{ block.super }}
{% if original.status == "pending" %}
<div class="submit-row">
  <input type="submit" name="_approve" value="Approve">
  <input type="submit" name="_reject" value="Reject (write the reason in Review note first)">
</div>
{% endif %}
{% endblock %}
```

- **It extends the admin's own template** and replaces only the block with the buttons at the
  bottom. `{{ block.super }}` keeps Save, "Save and continue editing" and Delete.
- **The buttons are inside the admin's `<form>`.** Pressing one submits the whole form, like
  Save does, plus its own `name`: `_approve=Approve` or `_reject=…`. That name is how the server
  knows which button was pressed. (Django's own buttons work the same way: `_save`,
  `_continue`, `_addanother`.)
- **`original`** is the event being edited (the admin puts it in the context). On the Add page it
  is empty, so no buttons show there.
- The admin has its own look: `submit-row` is the admin's CSS class for that row of buttons, not
  your UI library's.

In `EventAdmin`, name the template, below `formfield_overrides`:

```python
    # Our template adds the review buttons under the form.
    change_form_template = "admin/events/event/change_form.html"
```

Django would find the file by its path alone; naming it here makes the link visible to the next
reader.

- [ ] A pending event's admin page shows Approve and Reject; other events don't.

### 3. What the buttons do: `response_change`

When a change form is sent, the admin validates it, saves the event, and then calls
`response_change(request, obj)` to answer. That is the place to look for our buttons.

Add to `events/admin.py` (and to its imports: `messages` from `django.contrib`,
`ValidationError`, `HttpResponse` and `HttpResponseRedirect` from `django.http`,
`from django.utils import timezone`, and the two services):

```python
    @override
    def response_change(self, request: HttpRequest, obj: Event) -> HttpResponse:
        # Runs after the form is saved. A review button sends its name with the form.
        try:
            if "_approve" in request.POST:
                event_approve(event=obj, now=timezone.now())
                self.message_user(request, "Approved. The organizer has been emailed.")
            elif "_reject" in request.POST:
                event_reject(event=obj, reason=obj.review_note)
                self.message_user(request, "Rejected. The organizer has been emailed.")
            else:
                return super().response_change(request, obj)
        except ValidationError as error:
            self.message_user(request, " ".join(error.messages), messages.ERROR)
        # Back to the same page, which now shows the new status.
        return HttpResponseRedirect(request.path)
```

The imports now look like this:

```python
from typing import ClassVar, override

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import models
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.utils import timezone

from accounts.models import User
from config.photos import PhotoField
from events.models import Event
from events.services import event_approve, event_reject
```

How it works, step by step, for Reject:

1. The admin types the reason into "Review note" and presses Reject.
2. The admin saves the form: `review_note` is now in the event.
3. `response_change` sees `_reject` in the POST and calls `event_reject` with that note.
4. The service checks the rules, sets `rejected`, and queues the email for after the commit.
5. A message and a redirect back to the same page, which shows "Rejected" and no buttons.

If the service raises `ValidationError` (no reason, already started, not pending), the message
says why and the status stays as it was. Anything else (plain Save) goes to Django's own
`response_change`. Django runs the whole admin request in one transaction, so the email leaves
only after everything is saved.

- [ ] Approve and Reject work from the admin page, with a message each time.

### 4. Tests

`tests/events/test_review.py`. The services are tested directly; then the buttons once each
through `admin_client`, which posts the admin form like a browser would:

```python
from collections.abc import Callable
from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client
from django.utils import timezone
from pytest_django import DjangoCaptureOnCommitCallbacks

from events.models import Event
from events.services import event_approve, event_reject

pytestmark = pytest.mark.django_db


def test_approving_emails_the_organizer(
    make_event: Callable[..., Event],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(status=Event.Status.PENDING)

    with django_capture_on_commit_callbacks(execute=True):
        event_approve(event=event, now=timezone.now())

    event.refresh_from_db()
    assert event.status == Event.Status.APPROVED
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [event.organizer.email]
    assert f"/events/{event.pk}/" in mailoutbox[0].body


def test_a_started_event_cannot_be_approved(make_event: Callable[..., Event]) -> None:
    now = timezone.now()
    event = make_event(status=Event.Status.PENDING, starts_at=now - timedelta(hours=1))

    with pytest.raises(ValidationError, match="already started"):
        event_approve(event=event, now=now)

    event.refresh_from_db()
    assert event.status == Event.Status.PENDING


@pytest.mark.parametrize(
    "status", [Event.Status.APPROVED, Event.Status.REJECTED, Event.Status.CANCELLED]
)
def test_only_a_pending_event_can_be_reviewed(
    make_event: Callable[..., Event], status: Event.Status
) -> None:
    event = make_event(status=status)

    with pytest.raises(ValidationError):
        event_approve(event=event, now=timezone.now())
    with pytest.raises(ValidationError):
        event_reject(event=event, reason="Too vague.")


def test_rejecting_emails_the_reason(
    make_event: Callable[..., Event],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(status=Event.Status.PENDING)

    with django_capture_on_commit_callbacks(execute=True):
        event_reject(event=event, reason="The place is missing.")

    event.refresh_from_db()
    assert event.status == Event.Status.REJECTED
    assert event.review_note == "The place is missing."
    assert mailoutbox[0].to == [event.organizer.email]
    assert "The place is missing." in mailoutbox[0].body


def test_rejecting_needs_a_reason(make_event: Callable[..., Event]) -> None:
    event = make_event(status=Event.Status.PENDING)

    with pytest.raises(ValidationError, match="reason"):
        event_reject(event=event, reason="  ")


def change_form(event: Event, **extra: str) -> dict[str, object]:
    """What the admin's change form sends for `event`, plus a button's name."""
    starts_at = timezone.localtime(event.starts_at)
    return {
        "title": event.title,
        "description": event.description,
        "city": event.city,
        "place": event.place,
        "starts_at_0": starts_at.strftime("%Y-%m-%d"),
        "starts_at_1": starts_at.strftime("%H:%M:%S"),
        "type": event.type,
        "max_people": event.max_people,
        "language": event.language,
        "review_note": event.review_note,
        **extra,
    }


def test_the_approve_button(
    admin_client: Client,
    make_event: Callable[..., Event],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(status=Event.Status.PENDING)
    url = f"/admin/events/event/{event.pk}/change/"
    assert b'name="_approve"' in admin_client.get(url).content

    with django_capture_on_commit_callbacks(execute=True):
        response = admin_client.post(url, change_form(event, _approve="Approve"))

    assert response.status_code == 302
    assert response["Location"] == url
    event.refresh_from_db()
    assert event.status == Event.Status.APPROVED
    assert len(mailoutbox) == 1
    assert b'name="_approve"' not in admin_client.get(url).content


def test_the_reject_button_takes_the_review_note(
    admin_client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.PENDING)
    url = f"/admin/events/event/{event.pk}/change/"

    admin_client.post(
        url, change_form(event, review_note="Add the address.", _reject="Reject")
    )

    event.refresh_from_db()
    assert event.status == Event.Status.REJECTED
    assert event.review_note == "Add the address."


def test_the_reject_button_without_a_reason_shows_an_error(
    admin_client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.PENDING)
    url = f"/admin/events/event/{event.pk}/change/"

    response = admin_client.post(url, change_form(event, _reject="Reject"), follow=True)

    assert "Write the reason" in response.content.decode()
    event.refresh_from_db()
    assert event.status == Event.Status.PENDING
```

`change_form()` sends every field the admin form has, as a browser would. The admin splits a
date and time into two inputs (`starts_at_0`, `starts_at_1`). The photo isn't sent: on a change
form, "no new file" keeps the old one. The buttons of 014 and 015 can be tested the same way.

- [ ] The tests above pass.
- [ ] `scripts/check.sh` passes.

## Done when

- [ ] A pending event's admin page has Approve and Reject; once it is reviewed, they are gone
      (test).
- [ ] Approve: the event is `approved` and the organizer gets an email with the event's link
      (tests).
- [ ] Reject: the event is `rejected`, `review_note` holds the reason, and the organizer gets it
      by email (tests).
- [ ] Rejecting without a reason, approving a started event, and reviewing anything but a pending
      event are refused with a message; nothing changes (tests).
- [ ] `scripts/check.sh` passes.
- [ ] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 011-review-events-in-the-admin
```

Suggested commits:
1. `Add the event_approve and event_reject services`
2. `Add Approve and Reject buttons to the event admin page`
3. `Close 011 in the issue`

Open a pull request titled "Approve or reject events in the admin". Show screenshots of a pending
event's admin page with the buttons, and of the message after rejecting without a reason. Ask the
reviewer to try both buttons by hand. `docs/workflow/git.md` has every step.

## Watch out

- **The form is saved before `response_change`.** Whatever else the admin changed on the page is
  kept, even when the service then refuses. That's fine (the admin meant to change it), but it
  means the reason must be *in the form* when Reject is pressed: type it, then press Reject.
- **An old reason is still in "Review note"** when an event comes back after an edit (014).
  Replace it before pressing Reject, or the organizer gets last time's reason again.
- **The template's path matters**: `admin/events/event/change_form.html` inside
  `events/templates/`. A typo in a folder name and Django quietly uses its own template: no
  buttons, and no error.
- **Don't change `status` anywhere else** (not in `save_model`, not in a signal). The buttons and
  the services are the only way (SPEC.md §6.2), so the emails can't be forgotten.
- **Admin actions are not the right tool here.** An action works on rows ticked in the list and
  can't ask for one event's reason. The buttons on the page are per event, like SPEC.md §8 says.
- **Edits in the admin send no emails** (SPEC.md §2 #33). If a student asks why they weren't
  told about a typo fix, that is why.

## Further reading

- [Django: The admin site](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/), especially
  "Overriding admin templates" and the `ModelAdmin` methods `save_model`, `response_change` and
  `message_user`.
- [Django: Template inheritance](https://docs.djangoproject.com/en/6.1/ref/templates/language/#template-inheritance)
  (`{% extends %}`, `{% block %}`, `{{ block.super }}`).
- [Django: Form and field validation](https://docs.djangoproject.com/en/6.1/ref/forms/validation/)
  (`ValidationError`).
- [Django: Performing actions after commit](https://docs.djangoproject.com/en/6.1/topics/db/transactions/#performing-actions-after-commit).
- [Django: How to override templates](https://docs.djangoproject.com/en/6.1/howto/overriding-templates/):
  how Django finds your `change_form.html` before its own, and how extending the template you
  override works.
- [Django tutorial, part 7](https://docs.djangoproject.com/en/6.1/intro/tutorial07/): customizing
  the admin, including overriding one of its templates, on a small example.
- [Django: The messages framework](https://docs.djangoproject.com/en/6.1/ref/contrib/messages/):
  what `message_user` uses underneath, and how the message survives the redirect.
- [Django: The test client](https://docs.djangoproject.com/en/6.1/topics/testing/tools/#the-test-client):
  `post(..., follow=True)`, how the tests press the buttons and read the message.
