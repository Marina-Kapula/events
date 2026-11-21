# Cancel an event

Status: todo · Opened: 2026-11-21 · Milestone: M2 · Depends on: 011, 013, 014

## Why

Sometimes an event can't happen: the organizer is ill, the trip is off. Everyone who said they
would come must hear about it, so cancelling is a real action with emails, not a delete
(SPEC.md §2 #27). The organizer can cancel their event until it starts; AMFI can cancel any
event, any time, from the admin.

A cancelled event is not deleted. Its participations stay, so it still shows in everyone's
"My events" (016) as cancelled. Cancelling can't be undone, so the page asks "Are you sure?"
first, in a dialog made with HTML alone.

## What you'll build

- The service `event_cancel`: status `cancelled`, the pending `EventChange` deleted, an email to
  everyone going or waiting.
- A "Cancel event" button on the event page for the organizer, which opens a confirmation
  `<dialog>` without any JavaScript.
- A "Cancel event" button on the event's admin page.
- A cancelled event's page: seen only by the organizer and the people on it, marked as
  cancelled, without buttons.

Not in this issue: "My events" (016), cancelling through a soft delete (017).

## Before you start

Read:
- SPEC.md §2 #15, #27; §6.2 (the cancel row), §6.3, §6.6; §7 (the buttons); §8 (Events).
- AGENTS.md: Layers, Views and templates (UI-only state, POST for changes).
- `docs/testing/emails.md`.
- `docs/learn/hypermedia-and-forms.md`: GET or POST, and why the server decides, not the page.
- [MDN: `<dialog>`](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog)
  and [MDN: Invoker Commands](https://developer.mozilla.org/en-US/docs/Web/API/Invoker_Commands_API).

What you use from earlier issues: `Event` (010), 011's admin template and `response_change`,
012/013's event page, `event_detail` and `visible_to`, `Participation` (013), `EventChange`,
`_email_everyone_on` and the `press_admin_button` test fixture (014).

Words you'll meet:
- **`<dialog>`**: an HTML element for a box shown above the page. It stays hidden until opened.
- **Modal**: opened "as modal", the dialog blocks the rest of the page: you can't click behind
  it, keyboard focus moves into it, and Esc closes it.
- **Invoker Commands**: two button attributes, `commandfor` and `command`, that tell the browser
  "when clicked, do this to that element". No JavaScript.
- **`require_POST`**: a Django decorator that answers 405 to anything but a POST.

## Steps

### 1. The service

At the end of `events/services.py`:

```python
@transaction.atomic
def event_cancel(*, event: Event, by: User, now: datetime) -> None:
    """Cancels the event for good (SPEC.md §2 #27).

    `by` is who cancels: the organizer (only before the start) or staff (any time).
    """
    if event.status == Event.Status.CANCELLED:
        raise ValidationError("This event is already cancelled.")
    if not by.is_staff and event.starts_at <= now:
        raise ValidationError("This event has already started.")
    EventChange.objects.filter(event=event).delete()
    event.status = Event.Status.CANCELLED
    event.full_clean()
    event.save()
    _email_everyone_on(event, template="events/emails/event_cancelled")
```

Why each piece is there:

- **`by`** decides which rule applies. The view makes sure `by` is the organizer (step 2); the
  admin passes the staff user, who may cancel after the start too (§6.2).
- **`now` is an argument**, as for every rule that depends on the time (AGENTS.md, Layers): tests
  pass a fixed time instead of waiting for an event to start.
- **Any state but `cancelled`** can be cancelled: `pending`, `rejected` and `approved` (§6.2).
- **The pending change is deleted**: there's nothing left to review (§2 #27).
- **The participations stay.** The event remains in "My events" for everyone on it, and only
  they can still open its page (§6.3).
- **`_email_everyone_on`** is 014's helper: one email per person going or waiting, after the
  commit. The organizer gets none: they did it, or AMFI did and the organizer sees it on the
  page (§6.6).

The email, `events/templates/events/emails/event_cancelled_subject.txt` and `event_cancelled.txt`:

```django
{% autoescape off %}"{{ event.title }}" is cancelled{% endautoescape %}
```

```django
{% autoescape off %}Hi,

The event "{{ event.title }}" on {{ event.starts_at|date:"l j F, H:i" }} is cancelled.
{{ site_url }}{% url 'event_detail' event.pk %}
{% endautoescape %}
```

The `date` filter prints the start in the site's time zone, for example "Friday 4 December,
19:00".

- [ ] `event_cancel` and its two templates.

### 2. The view

Cancelling changes data, so it is a POST to its own URL, which redirects back to the event page
with a message (Post/Redirect/Get, §2 #2). In `events/views.py`:

```python
from events import services


@require_POST
def event_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    user = request.user
    if not isinstance(user, User) or user.is_staff:
        raise Http404
    event = get_object_or_404(Event, pk=pk, organizer=user)
    try:
        services.event_cancel(event=event, by=user, now=timezone.now())
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request, "Event cancelled. Everyone going or waiting was emailed."
        )
    return redirect("event_detail", pk=event.pk)
```

and in `events/urls.py`:

```python
path("events/<int:pk>/cancel/", views.event_cancel, name="event_cancel"),
```

- **`from events import services`**: the view and the service have the same name, so the view
  calls the service through its module.
- **Only the organizer; staff get a 404** (§6.9): staff cancel in the admin.
- **The `try/except` has a real fallback**: the rule's message is shown to the user (AGENTS.md:
  "the view shows it"). Pressing Cancel on a page left open past the start shows "This event has
  already started." instead of an error page.

- [ ] `event_cancel` (view) and its URL.

### 3. The button and the confirmation dialog

On the event page, next to 014's "Edit" link and with the same condition (the organizer, not
cancelled, not started):

```django
{% if event.organizer == user and event.status != "cancelled" and not started %}
  <a href="{% url 'event_edit' event.pk %}">Edit</a>
  <button type="button" commandfor="cancel-event" command="show-modal">Cancel event</button>
  <dialog id="cancel-event" aria-labelledby="cancel-event-title">
    <h2 id="cancel-event-title">Cancel “{{ event.title }}”?</h2>
    <p>Everyone going or waiting gets an email. You can't undo this.</p>
    <form method="post" action="{% url 'event_cancel' event.pk %}">
      {% csrf_token %}
      <button type="submit">Yes, cancel the event</button>
    </form>
    <button type="button" commandfor="cancel-event" command="close">No, keep it</button>
  </dialog>
{% endif %}
```

How it works, piece by piece:

- **The first button opens the dialog.** `commandfor="cancel-event"` names the element it
  controls (by `id`), and `command="show-modal"` says what to do with it: open it as a modal.
  The browser does it; we write no JavaScript. `type="button"` matters: a `<button>` inside a
  form would otherwise submit it.
- **The dialog** is hidden until then. Opened as a modal, it shows above a dimmed page
  (`::backdrop`), the page behind can't be clicked, focus moves into the dialog, and **Esc**
  closes it: all built into the browser, keyboard and screen readers included.
  `aria-labelledby` gives the dialog its title for screen readers.
- **"Yes" is a real form** with a POST and `{% csrf_token %}`. That is the only thing that
  changes data, and the server checks everything again (who you are, the state, the time). The
  dialog is only a question: if it fails to open, nothing gets cancelled by mistake.
- **"No, keep it"** uses `command="close"`, the opposite of `show-modal`.

Style the buttons and the dialog with your UI library (daisyUI, for example, styles a
`<dialog class="modal">` with a `modal-box` inside).

**Browser support.** Invoker Commands are new: Chrome and Edge 135 (April 2025), Firefox 144
(October 2025), Safari 26.2 (December 2025). Since December 2025 they work in all current
browsers ("Baseline newly available"). In an older browser the first button does nothing, so the
organizer can't reach the "Yes" button. If that matters to you (old iPhones that are never
updated), two simple fallbacks:

- **`<details>`** works in every browser, with no JavaScript:

  ```html
  <details>
    <summary>Cancel event</summary>
    <p>Everyone going or waiting gets an email. You can't undo this.</p>
    <form method="post" action="..."> ... Yes, cancel the event ... </form>
  </details>
  ```

  It opens in place instead of above the page, which is less pretty but just as safe.
- **Two lines of plain JavaScript** in `assets/static/js/ui.js` that call
  `document.getElementById("cancel-event").showModal()` on click (AGENTS.md allows plain JS
  there, after HTML and CSS).

Check: open the page as the organizer, click "Cancel event", press Esc, click again, click "No,
keep it", click again and confirm. Try it with the keyboard only (Tab, Enter, Esc).

- [ ] The button and the dialog; checked by hand in a browser.

### 4. The cancelled event's page

§6.3: a cancelled event's page is seen by the organizer and the people on it, marked as
cancelled, with no buttons. Most of it is there already: 012's `Event.objects.visible_to(user)`
lets the organizer in, 013 added "a cancelled event, for the people who were on it", and 012's
page says "This event was cancelled." at the top. Check that every button (join, leave, edit,
cancel) sits inside a condition that is false for a cancelled event, as the one in step 3 does.
The tests in step 6 tell you if anything is missing.

- [ ] A cancelled event's page says so and has no buttons.

### 5. The admin button

In 011's template `admin/events/event/change_form.html`, after 014's buttons:

```django
{% if original and original.status != "cancelled" %}
  <div class="submit-row">
    <input type="submit" name="_cancel" value="Cancel event (emails everyone on it)">
  </div>
{% endif %}
```

`original` is the event being changed; on the "Add event" page there is none, hence the first
check. And one more branch in `EventAdmin.response_change`, next to the others:

```python
            elif "_cancel" in request.POST:
                assert isinstance(request.user, User)  # the admin requires a login
                event_cancel(event=obj, by=request.user, now=timezone.now())
                self.message_user(
                    request, "Cancelled. Everyone going or waiting was emailed."
                )
```

The `assert` is the same as in 007: `request.user` is typed "a user, or `AnonymousUser`", and
the admin only lets staff in.

- [ ] The admin shows "Cancel event" on every event that isn't cancelled, and it works.

### 6. Tests

`tests/events/test_event_cancel.py`:

```python
from collections.abc import Callable
from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.http import HttpResponseBase
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pytest_django import DjangoCaptureOnCommitCallbacks

from accounts.models import User
from events.models import Event, EventChange, Participation
from events.services import event_cancel

pytestmark = pytest.mark.django_db


def test_cancelling_emails_everyone_going_or_waiting(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(status=Event.Status.APPROVED, max_people=2)
    going = make_participation(event=event, status=Participation.Status.GOING)
    waiting = make_participation(event=event, status=Participation.Status.WAITING)

    with django_capture_on_commit_callbacks(execute=True):
        event_cancel(event=event, by=event.organizer, now=timezone.now())

    event.refresh_from_db()
    assert event.status == Event.Status.CANCELLED
    assert sorted(message.to[0] for message in mailoutbox) == sorted(
        [going.user.email, waiting.user.email]
    )
    assert event.title in mailoutbox[0].subject
    # Kept, so the event stays in everyone's "My events".
    assert Participation.objects.filter(event=event).count() == 2


def test_cancelling_deletes_the_pending_changes(
    make_event: Callable[..., Event],
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    change = EventChange(event=event)
    event.copy_fields_to(change)
    change.save()

    event_cancel(event=event, by=event.organizer, now=timezone.now())

    assert not EventChange.objects.exists()


def test_the_organizer_cannot_cancel_after_the_start(
    make_event: Callable[..., Event],
) -> None:
    event = make_event(status=Event.Status.APPROVED)

    with pytest.raises(ValidationError, match="started"):
        event_cancel(
            event=event,
            by=event.organizer,
            now=event.starts_at + timedelta(minutes=1),
        )


def test_staff_can_cancel_any_time(
    make_event: Callable[..., Event], make_staff: Callable[..., User]
) -> None:
    event = make_event(status=Event.Status.APPROVED)

    event_cancel(
        event=event, by=make_staff(), now=event.starts_at + timedelta(hours=1)
    )

    assert event.status == Event.Status.CANCELLED


def test_a_cancelled_event_cannot_be_cancelled_again(
    make_event: Callable[..., Event], make_staff: Callable[..., User]
) -> None:
    event = make_event(status=Event.Status.CANCELLED)

    with pytest.raises(ValidationError, match="already cancelled"):
        event_cancel(event=event, by=make_staff(), now=timezone.now())


def test_the_organizer_cancels_from_the_event_page(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.PENDING)
    client.force_login(event.organizer)
    url = reverse("event_detail", args=[event.pk])

    page = client.get(url)
    response = client.post(reverse("event_cancel", args=[event.pk]), follow=True)

    assert b'command="show-modal"' in page.content
    assert response.redirect_chain == [(url, 302)]
    assert b"Event cancelled" in response.content
    assert b'command="show-modal"' not in response.content
    event.refresh_from_db()
    assert event.status == Event.Status.CANCELLED


def test_cancelling_a_started_event_shows_an_error(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(
        status=Event.Status.APPROVED, starts_at=timezone.now() - timedelta(hours=1)
    )
    client.force_login(event.organizer)

    response = client.post(reverse("event_cancel", args=[event.pk]), follow=True)

    assert b"already started" in response.content
    event.refresh_from_db()
    assert event.status == Event.Status.APPROVED


def test_only_the_organizer_may_cancel(
    client: Client,
    make_event: Callable[..., Event],
    make_student: Callable[..., User],
    make_staff: Callable[..., User],
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    url = reverse("event_cancel", args=[event.pk])

    client.force_login(make_student())
    assert client.post(url).status_code == 404
    client.force_login(make_staff())
    assert client.post(url).status_code == 404
    assert client.get(url).status_code == 405


def test_a_cancelled_event_is_seen_by_the_people_on_it_only(
    client: Client,
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    make_student: Callable[..., User],
) -> None:
    event = make_event(status=Event.Status.CANCELLED)
    participation = make_participation(event=event)
    url = reverse("event_detail", args=[event.pk])

    client.force_login(participation.user)
    page = client.get(url)
    assert b"cancelled" in page.content
    assert reverse("event_leave", args=[event.pk]).encode() not in page.content
    client.force_login(make_student())
    assert client.get(url).status_code == 404


def test_the_admin_cancels_an_event(
    admin_client: Client,
    press_admin_button: Callable[..., HttpResponseBase],
    make_event: Callable[..., Event],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    url = reverse("admin:events_event_change", args=[event.pk])
    assert b'name="_cancel"' in admin_client.get(url).content

    with django_capture_on_commit_callbacks(execute=True):
        response = press_admin_button(event, "_cancel")

    assert response.status_code == 302
    event.refresh_from_db()
    assert event.status == Event.Status.CANCELLED
    assert b'name="_cancel"' not in admin_client.get(url).content
```

- [ ] The tests above pass.
- [ ] `scripts/check.sh` passes.

## Done when

- [ ] The organizer cancels their event before it starts, after confirming in a `<dialog>`;
      afterwards they can't (tests).
- [ ] Staff cancel any event that isn't cancelled yet, any time, from the admin (tests).
- [ ] Cancelling deletes the pending `EventChange` and emails everyone going or waiting, one
      email each (tests).
- [ ] Others and staff get a 404 on the cancel URL, and a GET is a 405 (test).
- [ ] A cancelled event's page is seen only by the organizer and the people on it, says
      "cancelled" and has no buttons (test).
- [ ] The dialog works with the mouse and with the keyboard (checked by hand).
- [ ] `scripts/check.sh` passes.
- [ ] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 015-cancel-an-event
```

Suggested commits:
1. `Add the event_cancel service`
2. `Let the organizer cancel from the event page, after a confirmation dialog`
3. `Show cancelled events without buttons`
4. `Add a Cancel event button to the admin`
5. `Close 015 in the issue`

Open a pull request titled "Cancel an event". Add a screenshot of the open dialog, and say which
browsers you tried it in.

## Watch out

- **Cancelling is a POST, never a link.** A GET link could be followed by a browser's prefetch,
  a link preview or a crawler, and cancel the event (AGENTS.md: anything that changes data is a
  POST). The test checks that a GET answers 405.
- **`type="button"` on the opener.** Without it, a button inside a form submits that form.
- **The dialog decides nothing.** The service checks the state and the time again; an old page
  left open must not cancel a started event.
- **Ids must be unique on the page.** If you ever put several cancel dialogs on one page, give
  each its own `id` (`cancel-event-{{ event.pk }}`).
- **Don't delete the participations.** "My events" (016) needs them to show the cancelled event.
- **015 needs 014's `EventChange`**: that's why it depends on 014, although 014 and 015 touch
  different features.

## Worked example

- [08, `on_commit` in a loop](../docs/examples/08-on-commit-in-a-loop.md), if you skipped it in
  013: why `_email_everyone_on` uses `partial`.

## Further reading

- [MDN: `<dialog>`](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog):
  modal and non-modal, `::backdrop`, accessibility.
- [MDN: Invoker Commands API](https://developer.mozilla.org/en-US/docs/Web/API/Invoker_Commands_API)
  and the [`command` attribute of `<button>`](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/button#command).
- [Web features explorer: Invoker Commands](https://web-platform-dx.github.io/web-features-explorer/features/invoker-commands/):
  which browsers support it, and since when.
- [MDN: `<details>`](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/details).
- [Django: `require_POST`](https://docs.djangoproject.com/en/6.1/topics/http/decorators/#django.views.decorators.http.require_POST).
- [Django: The messages framework](https://docs.djangoproject.com/en/6.1/ref/contrib/messages/).
- [MDN: Safe HTTP methods](https://developer.mozilla.org/en-US/docs/Glossary/Safe/HTTP): browsers
  and crawlers call GETs freely, so a GET must never cancel anything.
- [MDN: 405 Method Not Allowed](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/405):
  what `require_POST` answers to a GET, and what the test checks.
- [hypermedia.systems, "A Web 1.0 Application"](https://hypermedia.systems/a-web-1-0-application/):
  deleting a contact with a POST button, a redirect and a flash message: the same shape as
  cancelling here.
