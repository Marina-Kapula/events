# Edit an event, and review the changes in the admin

Status: done · Opened: 2026-11-21 · Milestone: M2 · Depends on: 011, 013

## Why

Plans change: the pizzeria is full, the bus leaves an hour later. The organizer must be able to
fix their event. But AMFI reviews every event so that there are no fakes, so an edit can't just
go public either (SPEC.md §2 #16–#18).

The rule: an event that is still `pending` or `rejected` is edited directly and goes (back) to
review. An event that is already `approved` keeps its public version, and sign-ups stay open,
until AMFI approves the changes. The proposed changes wait in a second model, `EventChange`,
which the admin sees on the event's admin page, next to the current values (§2 #17, §6.5).

## What you'll build

- An `EventChange` model: the editable fields of an event, plus the event it belongs to.
- An "Edit" page for the organizer (`/events/<id>/edit/`) that explains what saving will do.
- The services `event_update`, `event_change_approve` and `event_change_reject`, with their
  emails.
- In the admin: the proposed changes, read only, on the event's page; the buttons "Approve
  changes" and "Reject changes"; a "Changes pending" column in the list.
- A "Changes pending" badge on the event's card and one line on its page.

Not in this issue: cancelling (015), "My events" (016).

## Before you start

Read:
- SPEC.md §2 #16, #17, #18, #33; §6.2 (the edit rows), §6.5, §6.6; §8 (Events).
- AGENTS.md: Layers, Views and templates, Django.
- `docs/testing/emails.md`.
- `docs/learn/transactions-and-race-conditions.md` and `docs/learn/hypermedia-and-forms.md`, if
  you haven't read them for 010–013: this issue uses both all the way through.
- [Django: Abstract base classes](https://docs.djangoproject.com/en/6.1/topics/db/models/#abstract-base-classes)
  and [One-to-one relationships](https://docs.djangoproject.com/en/6.1/topics/db/examples/one_to_one/).
- [Django: InlineModelAdmin objects](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#inlinemodeladmin-objects).

What you use from earlier issues: `EventFields`, `Event` and `EventForm` (010); the admin's
change form template `admin/events/event/change_form.html` and `EventAdmin.response_change` (011);
the event list's `{% partialdef event_card %}` and the event page (012); `Participation` and
`waiting_list_move_up` (013); `send_email` (005); the fixtures `make_event`,
`make_participation`, `make_student`, `make_staff`.

Words you'll meet:
- **Abstract model**: a model class with `abstract = True`. It has no table of its own; it only
  gives its fields to the models that inherit from it.
- **`OneToOneField`**: a foreign key that is also unique. Here: an event has at most one
  `EventChange`.
- **Reverse accessor**: the attribute Django adds on the *other* side of a relation. With
  `related_name="change"`, `event.change` is the event's `EventChange`.
- **Inline**: a related model shown inside its parent's admin page.
- **`functools.partial`**: makes a function call with its arguments filled in, to be run later.

## Steps

### 1. The `EventChange` model

Issue 010 already put the editable fields (title, description, photo, city, place, start, type,
max people, language) in the abstract `EventFields`, and `Event` inherits from it. If yours has
them on `Event`, move them up now: that is the whole point of `EventFields`.

In `events/models.py`, give `EventFields` one method, and add the new model after `Event`:

```python
class EventFields(models.Model):
    # ... the fields and Type from issue 010 ...

    class Meta:
        abstract = True

    def copy_fields_to(self, other: EventFields) -> None:
        """Copies the editable fields (the ones of this class) onto `other`."""
        for field in EventFields._meta.fields:
            setattr(other, field.name, getattr(self, field.name))


class EventChange(EventFields):
    """An organizer's edit of an approved event, waiting for AMFI (SPEC.md §2 #17)."""

    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name="change"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @override
    def __str__(self) -> str:
        return f"Changes to {self.event}"
```

Why each piece is there:

- **`EventChange(EventFields)`** gets exactly the fields an organizer can edit, with the same
  types and validators as `Event`. No JSON, no second list of fields to keep in sync.
- **`OneToOneField`** makes "at most one pending change per event" a database rule.
  **`CASCADE`**: if an event is deleted, its pending change goes with it.
- **`related_name="change"`** lets templates write `event.change`. When an event has no change,
  Django raises an error, but templates swallow that error, so `{% if event.change %}` is simply
  false. In Python code, ask the database instead:
  `EventChange.objects.filter(event=event).first()`.
- **`copy_fields_to`** is used three times in this issue (to pre-fill the form, to save an edit,
  to approve a change). `EventFields._meta.fields` lists the fields of the abstract class only
  (not `organizer`, `status`, `event`, …), so a field added to `EventFields` later is copied too.
  [`_meta`](https://docs.djangoproject.com/en/6.1/ref/models/meta/) is a documented Django API
  despite the underscore.
- **The photo is copied as it is.** If the organizer didn't upload a new photo, the change points
  at the same file name as the event; approving copies the name back. No file is copied or
  deleted (§6.8: old files stay).

```sh
uv run python manage.py makemigrations events
```

- [x] `EventFields.copy_fields_to` and `EventChange` as above; the migration exists.

### 2. Max people can't go below the people already going

Someone may already be going when the organizer edits an approved event. Lowering "max people"
below `1 + going` (the organizer counts too, §2 #24) would leave people without a spot, so the
form refuses it (§6.5). Add this method to `EventForm` in `events/forms.py` (import
`Participation` next to `Event`):

```python
    def clean_max_people(self) -> int:
        max_people: int = self.cleaned_data["max_people"]
        if self.instance.pk is None:  # a new event: nobody is going yet
            return max_people
        going = Participation.objects.filter(
            event=self.instance, status=Participation.Status.GOING
        ).count()
        if max_people < 1 + going:
            raise forms.ValidationError(
                f"{going} people are going, so you need at least {1 + going} spots "
                "(you count too)."
            )
        return max_people
```

`clean_<field>()` runs after the field's own checks, and its error shows under that field
([form validation](https://docs.djangoproject.com/en/6.1/ref/forms/validation/)). On the create
page (010) the instance has no `pk` yet, so the check is skipped.

- [x] `EventForm.clean_max_people` as above.

### 3. The services

The edit has a rule (where do the values go?) and a side effect (staff get an email), so it goes
through a service, not `form.save()` (AGENTS.md, Layers). Issue 010's `event_create` already
emails every active staff user; now a second service needs the same email. If 010 wrote that
code inside `event_create`, move it into a small private function and call it from both:

```python
def _email_staff(*, event: Event, template: str) -> None:
    staff = User.objects.filter(is_staff=True, is_active=True)
    emails = [user.email for user in staff]
    transaction.on_commit(
        partial(send_email, to=emails, template=template, context={"event": event})
    )
```

Then add to `events/services.py` (imports: `from functools import partial`, `EventChange`):

```python
@transaction.atomic
def event_update(*, event: Event, edited: Event) -> None:
    """Saves the organizer's edit (SPEC.md §6.5).

    `edited` is a second copy of `event` that holds the form's values.
    """
    if event.status == Event.Status.APPROVED:
        # The public version stays as it is until AMFI approves the changes.
        change = EventChange.objects.filter(event=event).first() or EventChange(
            event=event
        )
        edited.copy_fields_to(change)
        change.full_clean()
        change.save()
    else:
        edited.copy_fields_to(event)
        event.status = Event.Status.PENDING
        event.full_clean()
        event.save()
    _email_staff(event=event, template="events/emails/event_edited")


def _email_everyone_on(event: Event, *, template: str) -> None:
    """One email per person going or waiting: they don't see each other's address."""
    participations = Participation.objects.filter(event=event).select_related("user")
    for participation in participations:
        transaction.on_commit(
            partial(
                send_email,
                to=[participation.user.email],
                template=template,
                context={"event": event},
            )
        )


@transaction.atomic
def event_change_approve(*, event: Event, now: datetime) -> None:
    change = EventChange.objects.filter(event=event).first()
    if event.status != Event.Status.APPROVED or change is None:
        raise ValidationError("This event has no changes to approve.")
    if change.starts_at <= now:
        raise ValidationError("The new start time has passed.")
    going = Participation.objects.filter(
        event=event, status=Participation.Status.GOING
    ).count()
    if change.max_people < 1 + going:
        raise ValidationError(
            f"{going} people are going: max people must be at least {1 + going}."
        )
    change.copy_fields_to(event)
    event.full_clean()
    event.save()
    change.delete()
    waiting_list_move_up(event=event)
    transaction.on_commit(
        partial(
            send_email,
            to=[event.organizer.email],
            template="events/emails/event_changed",
            context={"event": event},
        )
    )
    _email_everyone_on(event, template="events/emails/event_changed")


@transaction.atomic
def event_change_reject(*, event: Event, reason: str) -> None:
    change = EventChange.objects.filter(event=event).first()
    if change is None:
        raise ValidationError("This event has no changes to reject.")
    if not reason.strip():
        raise ValidationError("Write the reason in the review note first.")
    event.review_note = reason
    event.full_clean()
    event.save()
    change.delete()
    transaction.on_commit(
        partial(
            send_email,
            to=[event.organizer.email],
            template="events/emails/event_changes_rejected",
            context={"event": event, "reason": reason},
        )
    )
```

Why each piece is there:

- **`event_update` gets two objects**: `event`, as it is in the database, and `edited`, the copy
  the form filled in (step 4). Approved: the values go into the event's `EventChange`, created
  the first time and overwritten after that. Pending or rejected: they go into the event itself,
  which goes back to `pending`.
- **The approval checks the rules again** (§6.5). Between the edit and the review, more people
  may have joined, or the new start time may have passed. The form's check is not enough.
- **`waiting_list_move_up`** (013) runs after the copy: if the change raised "max people", the
  first people waiting get the new spots, and their own email.
- **`_email_everyone_on` sends one email per person.** One email with everyone in `To:` would show
  every student's address to everyone else.
- **`partial(send_email, ...)` instead of `lambda: send_email(...)`.** A lambda in a loop reads
  the loop variable when it *runs*, after the commit, so every email would go to the last
  person. `partial` fills the arguments in *now*. (Ruff's rule B023 warns about the lambda.)
- **`review_note` keeps the reason** of a rejected change (§6.5). The event stays `approved`, so
  pages don't show it: the organizer reads it in the email (§2 #30).
- **`transaction.atomic`**: the copy, the delete and the waiting list move together, or not at
  all; the emails go out only after the commit.

Four email templates in `events/templates/events/emails/` (005 explains `{% autoescape off %}`;
subjects are one line):

`event_edited_subject.txt` and `event_edited.txt` (to staff):

```django
{% autoescape off %}To review: "{{ event.title }}"{% endautoescape %}
```

```django
{% autoescape off %}{{ event.organizer.full_name }} {% if event.status == "approved" %}proposed changes to{% else %}edited{% endif %} the event "{{ event.title }}".

Review {% if event.status == "approved" %}the changes{% else %}it{% endif %} in the admin:
{{ site_url }}{% url 'admin:events_event_change' event.pk %}
{% endautoescape %}
```

`event_changed_subject.txt` and `event_changed.txt` (to the organizer and everyone on the event):

```django
{% autoescape off %}"{{ event.title }}" has changed{% endautoescape %}
```

```django
{% autoescape off %}Hi,

The event "{{ event.title }}" has new details, approved by AMFI. Check them here:
{{ site_url }}{% url 'event_detail' event.pk %}
{% endautoescape %}
```

`event_changes_rejected_subject.txt` and `event_changes_rejected.txt` (to the organizer):

```django
{% autoescape off %}Your changes to "{{ event.title }}" were not approved{% endautoescape %}
```

```django
{% autoescape off %}Hi {{ event.organizer.full_name }},

AMFI did not approve your changes to "{{ event.title }}", so the event stays as it was.

The reason: {{ reason }}

You can edit it again here:
{{ site_url }}{% url 'event_edit' event.pk %}
{% endautoescape %}
```

- [x] The three services, the two helpers and the six templates.

### 4. The edit page

`events/views.py`:

```python
def event_edit(request: HttpRequest, pk: int) -> HttpResponse:
    user = request.user
    if not isinstance(user, User) or user.is_staff:
        raise Http404
    event = get_object_or_404(
        Event.objects.exclude(status=Event.Status.CANCELLED),
        pk=pk,
        organizer=user,
        starts_at__gt=timezone.now(),
    )
    change = EventChange.objects.filter(event=event).first()
    # The form fills a second copy of the event; event_update decides where the
    # values go. Pre-filled from the pending changes, if there are some.
    edited = Event.objects.get(pk=event.pk)
    if change is not None:
        change.copy_fields_to(edited)
    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=edited)
        if form.is_valid():
            event_update(event=event, edited=edited)
            messages.success(request, "Saved and sent to AMFI for review.")
            return redirect("event_detail", pk=event.pk)
    else:
        form = EventForm(instance=edited)
    return render(
        request,
        "events/event_form.html",
        {"form": form, "event": event, "change": change},
    )
```

and in `events/urls.py`:

```python
path("events/<int:pk>/edit/", views.event_edit, name="event_edit"),
```

Why each piece is there:

- **Who and when, in one query.** Only the organizer, only before the start, never a cancelled
  event; anything else is a 404 (§6.5, AGENTS.md). Staff are a 404 too: they edit in the admin
  (§6.9). The `isinstance` check also tells pyrefly that `user` is our `User` (as in 009).
- **Why a second copy (`edited`)?** `form.is_valid()` writes the submitted values onto the form's
  instance. If that were `event` itself, the object would hold the *new* values while the
  database still has the old ones, and it's easy to save it by mistake. The copy keeps the two
  apart: `event` is the truth, `edited` is the proposal. (It happens even when the form is
  refused: `test_a_refused_edit_does_not_touch_the_event` guards it.)
- **Pre-filled from the change**: an organizer who edits twice sees their last proposal, not the
  public version (§6.5).
- **The photo**: `EventForm`'s photo field (006) is not required to be uploaded again: with no new
  file, Django keeps the current one, so the change gets the same file name.
- **Same template as "create"** (010's form page). Above the form, explain what saving will do
  (§7). For example:

```django
{% if event %}
  <h1>Edit “{{ event.title }}”</h1>
  {% if event.status == "approved" %}
    <p>This event is public. AMFI reviews your changes first; until then everyone sees
      the current version, and people can still join.
      {% if change %}You already sent changes: saving replaces them.{% endif %}</p>
  {% elif event.status == "rejected" %}
    <p>AMFI rejected this event: “{{ event.review_note }}”. Fix it and save: it goes back to review.</p>
  {% else %}
    <p>AMFI is reviewing this event. Saving sends them your new version.</p>
  {% endif %}
{% else %}
  <h1>New event</h1>
{% endif %}
```

Style it with your UI library (003); the form itself doesn't change.

- [x] `event_edit` and its URL; the page explains the three cases.

### 5. "Edit" and "Changes pending" on the pages

On the event page (012/013), the organizer gets a link to the edit page. It's a plain link: it
only *opens* a page; the change itself is the form's POST. 013's view passes `is_open`
(approved and not started), but the organizer may also edit a pending or rejected event, so add
`"started": event.starts_at <= timezone.now()` to `event_detail`'s context.

```django
{% if event.organizer == user and event.status != "cancelled" and not started %}
  <a href="{% url 'event_edit' event.pk %}">Edit</a>
{% endif %}
{% if event.change %}
  <p role="status">Changes pending: AMFI is reviewing changes to this event.</p>
{% endif %}
```

On the card (`{% partialdef event_card %}` in `events/event_list.html`), show the badge instead
of the status:

```django
{% if event.change %}
  <span class="badge">Changes pending</span>
{% elif event.status != "approved" %}
  <span class="badge">{{ event.get_status_display }}</span>
{% endif %}
```

(`badge` is daisyUI's class; use your UI library's badge.)

Each `{% if event.change %}` asks the database for the change. On the list that is one query per
card, unless the view fetches the changes together with the events. In `event_list`, start from
`Event.objects.listed(now=timezone.now()).select_related("change")` (keep whatever 013 added),
and in `event_detail` make it `select_related("organizer", "change")`. A reverse one-to-one
works with `select_related`. The `django_assert_num_queries` tests of 012 and 013 prove it: they
must pass with the same numbers as before.

- [x] The Edit link, the warning line and the badge; the list's query-count tests still pass.

### 6. The admin: the change, read only, and two buttons

In `events/admin.py`:

```python
class EventChangeInline(admin.StackedInline[EventChange, Event]):
    """The organizer's proposed changes, read only: use the buttons below."""

    model = EventChange

    @override
    def has_add_permission(self, request: HttpRequest, obj: Event | None) -> bool:
        return False

    @override
    def has_change_permission(
        self, request: HttpRequest, obj: Event | None = None
    ) -> bool:
        return False

    @override
    def has_delete_permission(
        self, request: HttpRequest, obj: Event | None = None
    ) -> bool:
        return False
```

and on `EventAdmin`:

```python
    list_display = ("title", "organizer", "starts_at", "status", "changes_pending")
    list_select_related = ("organizer", "change")
    inlines = (EventChangeInline,)

    @admin.display(boolean=True)
    def changes_pending(self, obj: Event) -> bool:
        return hasattr(obj, "change")
```

Keep 010's other options (`list_filter`, `readonly_fields`, `formfield_overrides`, …).

- **No add, change or delete permission** makes the inline *view only*: the admin sees the
  proposed values right under the current ones, and can't edit them. Approving or rejecting is
  what the buttons are for (§2 #15, #17).
- **`hasattr(obj, "change")`** is how the Django docs test a reverse one-to-one: it is `False`
  when there is none. `list_select_related` loads the changes with the list, in one query.

The buttons go into 011's template `admin/events/event/change_form.html`, below 011's buttons:

```django
{% if original.status == "approved" and original.change %}
  <div class="submit-row">
    <input type="submit" name="_approve_changes" value="Approve changes">
    <input type="submit" name="_reject_changes" value="Reject changes (write the reason in Review note)">
  </div>
{% endif %}
```

and `EventAdmin.response_change` (011) gets two more branches, next to `_approve` and `_reject`:

```python
            elif "_approve_changes" in request.POST:
                event_change_approve(event=obj, now=timezone.now())
                self.message_user(
                    request, "Changes approved. Everyone on the event was emailed."
                )
            elif "_reject_changes" in request.POST:
                event_change_reject(event=obj, reason=obj.review_note)
                self.message_user(
                    request, "Changes rejected. The organizer was emailed."
                )
```

As in 011: the form is saved first (so `obj.review_note` is what the admin just typed), then the
button calls its service; a `ValidationError` becomes a red message and the admin stays on the
page.

- [x] The inline, the column and the two buttons work in `/admin/`.

### 7. Tests

**First, 011's button tests break**, and that's expected. They post the admin form with
`change_form()`, which lists the event's fields by hand. The page now has an inline too, and the
admin needs the inline's *management form* (hidden inputs such as `change-TOTAL_FORMS` that say
how many inline rows were sent). Without it the admin answers 200 with an error instead of
saving. Rather than adding the inline's inputs by hand (and again for every future inline),
replace `change_form()` with a fixture that reads every field from the page itself, as the
browser does. Add it to `tests/conftest.py` (015 uses it too):

```python
@pytest.fixture
def press_admin_button(admin_client: Client) -> Callable[..., HttpResponseBase]:
    """Posts an event's admin page as the browser would, through one of its buttons."""

    def press(event: Event, button: str, **changes: object) -> HttpResponseBase:
        url = reverse("admin:events_event_change", args=[event.pk])
        context = admin_client.get(url).context
        # The event's form, and each inline's forms with its "management form".
        forms = [context["adminform"].form]
        for inline in context["inline_admin_formsets"]:
            forms += [inline.formset.management_form, *inline.formset.forms]
        data: dict[str, object] = {}
        for form in forms:
            for field in form:
                value = field.value()
                if isinstance(field.field.widget, SplitDateTimeWidget):
                    date, time = field.field.widget.decompress(value)
                    data[f"{field.html_name}_0"] = date
                    data[f"{field.html_name}_1"] = time
                elif not isinstance(field.field, FileField):  # no file: keep it
                    data[field.html_name] = value
        data |= {button: "on", **changes}
        return admin_client.post(
            url, {name: value for name, value in data.items() if value is not None}
        )

    return press
```

(Imports: `FileField` and `SplitDateTimeWidget` from `django.forms`, `HttpResponseBase` from
`django.http`, `Client` from `django.test`, `reverse` from `django.urls`.)

- **`response.context`** is the context the admin's template was rendered with: the event's
  form (`adminform`) and the inlines' formsets.
- **`field.value()`** is what the browser would send back unchanged.
- **The admin shows a date and time as two inputs** (`starts_at_0`, `starts_at_1`), hence the
  `SplitDateTimeWidget` branch. Files are left out: on a change form, "no new file" keeps the
  current one.
- **`**changes`** overrides fields, like the reason typed into "Review note".

Then in 011's `tests/events/test_review.py`, use it and delete `change_form()`:
`admin_client.post(url, change_form(event, _approve="Approve"))` becomes
`press_admin_button(event, "_approve")`;
`change_form(event, review_note="Add the address.", _reject="Reject")` becomes
`press_admin_button(event, "_reject", review_note="Add the address.")`. The fixture doesn't
follow the redirect: to read the message, open `response["Location"]` with `admin_client.get`.

`tests/events/test_event_edit.py`, the edit page:

```python
import io
from collections.abc import Callable
from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from pytest_django import DjangoCaptureOnCommitCallbacks

from accounts.models import User
from events.models import Event, EventChange, Participation

pytestmark = pytest.mark.django_db


def form_data(event: Event, **changes: object) -> dict[str, object]:
    """The edit form as the browser sends it: every field, no new photo."""
    return {
        "title": event.title,
        "description": event.description,
        "city": event.city,
        "place": event.place,
        "starts_at": timezone.localtime(event.starts_at).strftime("%Y-%m-%dT%H:%M"),
        "type": event.type,
        "max_people": event.max_people,
        "language": event.language,
        **changes,
    }


def test_editing_a_pending_event_saves_it_and_emails_staff(
    client: Client,
    make_event: Callable[..., Event],
    make_staff: Callable[..., User],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    staff = make_staff()
    event = make_event(status=Event.Status.PENDING)
    client.force_login(event.organizer)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("event_edit", args=[event.pk]),
            form_data(event, title="Pizza night"),
        )

    assert response.status_code == 302
    event.refresh_from_db()
    assert event.title == "Pizza night"
    assert event.status == Event.Status.PENDING
    assert [message.to for message in mailoutbox] == [[staff.email]]
    assert f"/admin/events/event/{event.pk}/change/" in mailoutbox[0].body


def test_editing_a_rejected_event_sends_it_back_to_review(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.REJECTED, review_note="No place given.")
    client.force_login(event.organizer)

    client.post(
        reverse("event_edit", args=[event.pk]),
        form_data(event, place="Bar Centrale"),
    )

    event.refresh_from_db()
    assert event.status == Event.Status.PENDING
    assert event.place == "Bar Centrale"


def test_editing_an_approved_event_keeps_the_public_version(
    client: Client,
    make_event: Callable[..., Event],
    make_staff: Callable[..., User],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    make_staff()
    event = make_event(status=Event.Status.APPROVED, title="Pizza night")
    client.force_login(event.organizer)

    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            reverse("event_edit", args=[event.pk]),
            form_data(event, title="Pasta night"),
        )

    event.refresh_from_db()
    assert event.title == "Pizza night"
    assert event.status == Event.Status.APPROVED
    assert EventChange.objects.get(event=event).title == "Pasta night"
    assert len(mailoutbox) == 1


def test_editing_again_replaces_the_changes_and_prefills_the_form(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    client.force_login(event.organizer)
    url = reverse("event_edit", args=[event.pk])

    client.post(url, form_data(event, title="Pasta night"))
    page = client.get(url)
    client.post(url, form_data(event, title="Pasta and wine"))

    assert b'value="Pasta night"' in page.content
    assert EventChange.objects.get(event=event).title == "Pasta and wine"


def test_a_photo_that_is_not_uploaded_again_keeps_its_file(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    client.force_login(event.organizer)

    client.post(reverse("event_edit", args=[event.pk]), form_data(event))

    assert EventChange.objects.get(event=event).photo.name == event.photo.name


def test_a_new_photo_goes_into_the_changes(
    client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    public_photo = event.photo.name
    client.force_login(event.organizer)
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), "teal").save(buffer, "JPEG")
    photo = SimpleUploadedFile("new.jpg", buffer.getvalue(), "image/jpeg")

    client.post(reverse("event_edit", args=[event.pk]), form_data(event, photo=photo))

    change = EventChange.objects.get(event=event)
    assert change.photo.name != public_photo
    assert change.photo.storage.exists(change.photo.name)
    event.refresh_from_db()
    assert event.photo.name == public_photo


def test_max_people_cannot_go_below_the_people_going(
    client: Client,
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    event = make_event(status=Event.Status.APPROVED, max_people=5)
    make_participation(event=event)
    make_participation(event=event)
    client.force_login(event.organizer)

    response = client.post(
        reverse("event_edit", args=[event.pk]), form_data(event, max_people=2)
    )

    assert response.status_code == 200
    assert b"at least 3 spots" in response.content
    assert not EventChange.objects.exists()


def test_a_refused_edit_does_not_touch_the_event(
    client: Client,
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    # Bound to `event` itself, the form would write "Pasta night" onto it in
    # is_valid(), even though max_people refuses the edit (worked example 09).
    event = make_event(status=Event.Status.APPROVED, title="Pizza night", max_people=5)
    make_participation(event=event)
    make_participation(event=event)
    client.force_login(event.organizer)

    response = client.post(
        reverse("event_edit", args=[event.pk]),
        form_data(event, title="Pasta night", max_people=2),
    )

    assert response.status_code == 200
    # The event the page shows (its heading, its status text) is still the public one.
    assert response.context["event"].title == "Pizza night"


def test_only_the_organizer_may_edit(
    client: Client,
    make_event: Callable[..., Event],
    make_student: Callable[..., User],
    make_staff: Callable[..., User],
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    url = reverse("event_edit", args=[event.pk])

    client.force_login(make_student())
    assert client.get(url).status_code == 404
    client.force_login(make_staff())
    assert client.get(url).status_code == 404


@pytest.mark.parametrize(
    ("status", "days"),
    [(Event.Status.APPROVED, -1), (Event.Status.CANCELLED, 7)],
    ids=["started", "cancelled"],
)
def test_started_or_cancelled_events_cannot_be_edited(
    client: Client, make_event: Callable[..., Event], status: str, days: int
) -> None:
    event = make_event(status=status, starts_at=timezone.now() + timedelta(days=days))
    client.force_login(event.organizer)

    assert client.get(reverse("event_edit", args=[event.pk])).status_code == 404


def test_the_list_and_the_page_say_changes_pending(
    client: Client, make_event: Callable[..., Event], make_student: Callable[..., User]
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    client.force_login(event.organizer)
    client.post(reverse("event_edit", args=[event.pk]), form_data(event, title="New"))
    client.force_login(make_student())

    assert b"Changes pending" in client.get(reverse("home")).content
    assert (
        b"Changes pending"
        in client.get(reverse("event_detail", args=[event.pk])).content
    )
```

These tests assume `make_participation` (013) makes someone `going` by default. The new-photo
test writes a real file: 006's autouse fixture puts it in a temporary folder.

`tests/events/test_event_changes.py`, the review:

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

from events.models import Event, EventChange, Participation
from events.services import event_change_approve, event_change_reject

pytestmark = pytest.mark.django_db


def make_change(event: Event, **changes: object) -> EventChange:
    change = EventChange(event=event)
    event.copy_fields_to(change)
    for name, value in changes.items():
        setattr(change, name, value)
    change.full_clean()
    change.save()
    return change


def test_approving_copies_the_changes_and_emails_everyone(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(status=Event.Status.APPROVED, title="Pizza night")
    going = make_participation(event=event)
    make_change(event, title="Pasta night", photo="photos/events/pasta.jpg")

    with django_capture_on_commit_callbacks(execute=True):
        event_change_approve(event=event, now=timezone.now())

    event.refresh_from_db()
    assert event.title == "Pasta night"
    assert event.photo.name == "photos/events/pasta.jpg"
    assert not EventChange.objects.exists()
    assert sorted(message.to[0] for message in mailoutbox) == sorted(
        [event.organizer.email, going.user.email]
    )


def test_approving_more_spots_moves_the_waiting_list_up(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    event = make_event(status=Event.Status.APPROVED, max_people=2)
    make_participation(event=event, status=Participation.Status.GOING)
    waiting = make_participation(event=event, status=Participation.Status.WAITING)
    make_change(event, max_people=3)

    event_change_approve(event=event, now=timezone.now())

    waiting.refresh_from_db()
    assert waiting.status == Participation.Status.GOING


def test_approving_refuses_fewer_spots_than_people_going(
    make_event: Callable[..., Event],
    make_participation: Callable[..., Participation],
) -> None:
    event = make_event(status=Event.Status.APPROVED, max_people=4)
    make_change(event, max_people=2)
    make_participation(event=event)
    make_participation(event=event)  # joined while AMFI was reviewing

    with pytest.raises(ValidationError, match="at least 3"):
        event_change_approve(event=event, now=timezone.now())

    event.refresh_from_db()
    assert event.max_people == 4


def test_approving_refuses_a_start_in_the_past(
    make_event: Callable[..., Event],
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    change = make_change(event)

    with pytest.raises(ValidationError, match="passed"):
        event_change_approve(event=event, now=change.starts_at + timedelta(minutes=1))


def test_rejecting_keeps_the_event_and_emails_the_reason(
    make_event: Callable[..., Event],
    mailoutbox: list[mail.EmailMessage],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    event = make_event(status=Event.Status.APPROVED, title="Pizza night")
    make_change(event, title="Pasta night")

    with django_capture_on_commit_callbacks(execute=True):
        event_change_reject(event=event, reason="Say where's the pasta from.")

    event.refresh_from_db()
    assert event.title == "Pizza night"
    assert event.review_note == "Say where's the pasta from."
    assert not EventChange.objects.exists()
    assert [message.to for message in mailoutbox] == [[event.organizer.email]]
    assert "Say where's the pasta from." in mailoutbox[0].body  # not &#x27;


def test_rejecting_needs_a_reason(make_event: Callable[..., Event]) -> None:
    event = make_event(status=Event.Status.APPROVED)
    make_change(event)

    with pytest.raises(ValidationError, match="reason"):
        event_change_reject(event=event, reason=" ")

    assert EventChange.objects.exists()


def test_the_admin_shows_the_buttons_only_with_changes(
    admin_client: Client, make_event: Callable[..., Event]
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    url = reverse("admin:events_event_change", args=[event.pk])

    assert b'name="_approve_changes"' not in admin_client.get(url).content
    make_change(event)
    assert b'name="_approve_changes"' in admin_client.get(url).content


def test_the_admin_approves_changes(
    press_admin_button: Callable[..., HttpResponseBase],
    make_event: Callable[..., Event],
) -> None:
    event = make_event(status=Event.Status.APPROVED, title="Pizza night")
    make_change(event, title="Pasta night")

    response = press_admin_button(event, "_approve_changes")

    assert response.status_code == 302
    event.refresh_from_db()
    assert event.title == "Pasta night"
    assert not EventChange.objects.exists()


def test_the_admin_needs_a_reason_to_reject_changes(
    admin_client: Client,
    press_admin_button: Callable[..., HttpResponseBase],
    make_event: Callable[..., Event],
) -> None:
    event = make_event(status=Event.Status.APPROVED)
    make_change(event)

    response = press_admin_button(event, "_reject_changes")

    assert response.status_code == 302
    assert EventChange.objects.exists()
    page = admin_client.get(response["Location"])
    assert b"Write the reason in the review note" in page.content


def test_the_admin_rejects_changes_with_the_review_note(
    press_admin_button: Callable[..., HttpResponseBase],
    make_event: Callable[..., Event],
) -> None:
    event = make_event(status=Event.Status.APPROVED, title="Pizza night")
    make_change(event, title="Pasta night")

    press_admin_button(event, "_reject_changes", review_note="Keep the pizza.")

    event.refresh_from_db()
    assert event.title == "Pizza night"
    assert event.review_note == "Keep the pizza."
    assert not EventChange.objects.exists()
```

- [x] The tests above pass, and so do 011's, through `press_admin_button`.
      `test_models_and_migrations_agree` and the admin smoke test (every changelist opens) pass
      too.
- [x] `scripts/check.sh` passes.

## Done when

- [x] Editing a pending or rejected event changes it in place and sends it back to `pending`;
      staff are emailed (tests).
- [x] Editing an approved event creates or replaces its `EventChange`; the public version and
      sign-ups don't change; staff are emailed; the form is pre-filled from the change (tests).
- [x] A photo that isn't uploaded again keeps its file name (test).
- [x] Max people below `1 + going` is a form error, and is refused again on approval (tests).
- [x] Others, staff, started and cancelled events get a 404 on the edit page (tests).
- [x] In the admin, the change is read only on the event's page; "Approve changes" copies it,
      moves the waiting list up and emails the organizer and everyone going or waiting;
      "Reject changes" needs a reason, keeps the event and emails the organizer (tests).
- [x] The card shows "Changes pending", the event page one line; the list's query count is
      unchanged (tests).
- [x] `scripts/check.sh` passes.
- [x] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 014-edit-events-and-pending-changes
```

Suggested commits (each one passes `scripts/check.sh`):
1. `Add the EventChange model`
2. `Refuse fewer spots than people going in the event form`
3. `Add the event_update service and the edit page`
4. `Add the services to approve and reject changes`
5. `Show pending changes in the admin, with Approve and Reject buttons`
6. `Show "Changes pending" on the card and the event page`
7. `Close 014 in the issue`

Open a pull request titled "Edit an event, and review the changes in the admin". Add
screenshots of the edit page for an approved event and of the admin page with the inline and the
two buttons. Ask the reviewer to look at `event_change_approve` in particular.

## Watch out

- **Never `event.save()` an event the form has touched while it is approved.** That is why the
  view gives the form a copy. If you "simplify" it to `instance=event`, the public version
  changes before AMFI has looked at it.
- **`{% if event.change %}` costs a query per card** unless the view has `select_related("change")`.
  The query-count test catches it.
- **`event.change` in Python raises `Event.change.RelatedObjectDoesNotExist`** when there is no
  change. Ask with `EventChange.objects.filter(event=event).first()` (or `hasattr`), not with
  `try/except`.
- **Edits in the admin send no emails** (§2 #33). Only the buttons do: they call the services.
- **Lambdas in a loop** (`on_commit(lambda: send_email(to=[p.user.email], ...))`) all send to the
  last person. Use `partial`.
- **The admin's Approve changes saves the form first.** If the admin changed other fields on the
  same page, those are saved, then the change is copied over them.

## Worked example

- [09, `is_valid()` changes the event](../docs/examples/09-modelform-changes-its-instance.md):
  after step 4, see why the edit view gives the form a copy.
- [08, `on_commit` in a loop](../docs/examples/08-on-commit-in-a-loop.md), if you skipped it in
  013: the bug `_email_everyone_on` avoids.

## Further reading

- [Django: Model inheritance](https://docs.djangoproject.com/en/6.1/topics/db/models/#model-inheritance),
  abstract base classes in particular.
- [Django: `OneToOneField`](https://docs.djangoproject.com/en/6.1/ref/models/fields/#onetoonefield)
  and the [one-to-one example](https://docs.djangoproject.com/en/6.1/topics/db/examples/one_to_one/)
  (`hasattr` on a reverse one-to-one).
- [Django: The `save()` method of a ModelForm](https://docs.djangoproject.com/en/6.1/topics/forms/modelforms/#the-save-method)
  (what `is_valid()` does to the instance).
- [Django: InlineModelAdmin objects](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#inlinemodeladmin-objects)
  and [overriding admin templates](https://docs.djangoproject.com/en/6.1/ref/contrib/admin/#overriding-admin-templates).
- [Django: `select_related`](https://docs.djangoproject.com/en/6.1/ref/models/querysets/#select-related).
- [Python: `functools.partial`](https://docs.python.org/3/library/functools.html#functools.partial),
  and [Ruff B023](https://docs.astral.sh/ruff/rules/function-uses-loop-variable/) on why not a
  lambda.
- [Django: Validation on a ModelForm](https://docs.djangoproject.com/en/6.1/topics/forms/modelforms/#validation-on-a-modelform):
  the warning that validating a form changes its instance, which is why the edit view gives the
  form a copy.
- [Adam Johnson: use `partial()` with `transaction.on_commit()`](https://adamj.eu/tech/2022/08/22/use-partial-with-djangos-transaction-on-commit/):
  the loop bug of "everyone going or waiting gets an email", and its fix.
