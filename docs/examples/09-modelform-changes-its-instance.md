# 09. `is_valid()` changes the event: why issue 014 edits a copy

Issue 014's edit view gives the form a *second copy* of the event (`edited`), not the event
itself, and the reason fits in one sentence that is easy to skim past: `form.is_valid()` writes
the submitted values onto the form's instance. Here you watch it happen in the shell: the
object in memory says "Pasta night" while the database still says "Pizza night", one `save()`
publishes an edit nobody reviewed, and even a value the form *refused* lands on the object.

Do it after issue 014, step 4 (`EventForm` with `clean_max_people`, and the edit page). Takes 10
minutes.

## Setup

An **approved** event called "Pizza night" in your local database, organized by a student: make
it through the Create page and approve it in the admin (or with 011's Approve button). Its `pk`
was 1 in this run. Then `uv run python manage.py shell`.

## Steps

### 1. Bind a form to the real event

```pycon
>>> from events.forms import EventForm
>>> from events.models import Event
>>> event = Event.objects.get(title="Pizza night")
>>> event.pk, event.title, event.status
(1, 'Pizza night', 'approved')
>>> data = {"title": "Pasta night", "type": event.type, "description": event.description, "city": event.city, "place": event.place, "starts_at": timezone.localtime(event.starts_at).strftime("%Y-%m-%dT%H:%M"), "max_people": event.max_people, "language": event.language}
>>> form = EventForm(data, instance=event)
>>> event.title
'Pizza night'
>>> form.is_valid()
True
>>> event.title
'Pasta night'
>>> Event.objects.get(pk=event.pk).title
'Pizza night'
```

`data` is what the browser would send: every field, a new title, no new photo.

### 2. One innocent `save()`

```pycon
>>> event.save()
>>> Event.objects.get(pk=event.pk).title
'Pasta night'
```

The public event is now "Pasta night", and AMFI never saw it. Put it back:
`Event.objects.filter(pk=1).update(title="Pizza night")`.

### 3. A form that says no still changes the event

```pycon
>>> event = Event.objects.get(pk=1)
>>> form = EventForm({**data, "max_people": 1}, instance=event)
>>> form.is_valid()
False
>>> form.errors.as_data()
{'max_people': [ValidationError(['Ensure this value is greater than or equal to 2.'])]}
>>> event.title, event.max_people
('Pasta night', 1)
```

### 4. The copy

```pycon
>>> event = Event.objects.get(pk=1)
>>> edited = Event.objects.get(pk=event.pk)
>>> form = EventForm({**data, "max_people": 8}, instance=edited)
>>> form.is_valid()
True
>>> event.title, edited.title
('Pizza night', 'Pasta night')
>>> event is edited
False
```

### 5. What the student sees with the "simplified" view

In `event_edit`, change `instance=edited` to `instance=event` and `edited=edited` to
`edited=event`. Log in as the organizer, open `/events/1/edit/`, type "Pasta night" as the title
and `1` as max people, and save. The page comes back (status 200) with the error. In the page's
source:

```text
  <h1>Edit “Pasta night”</h1>
    <p>This event is public. AMFI reviews your changes first; until then everyone sees
<ul class="errorlist" id="id_max_people_error"><li>Ensure this value is greater than or equal to 2.</li></ul>
```

With the copy (undo the change), the same POST shows `<h1>Edit “Pizza night”</h1>`: the
heading names the public version, as the explanation under it says.

## What just happened

- **A `ModelForm` validates the model too.** During `is_valid()`, after the form's own checks,
  Django copies the cleaned values onto `form.instance` and runs the model's `full_clean()` on
  it (that's how model validators and unique checks reach the form). The copying happens before
  anyone calls `save()`, and whether or not the form ends up valid.
- **Step 3 is the surprise**: `max_people = 1` was refused, yet it's on the object. The model's
  `MinValueValidator(2)` found the error *after* the value had been copied on.
- **The database is the truth, the object is only a copy of a row.** Nothing changed in the
  database in steps 1 and 3. But any code that later saves that object in the same request (a
  service that saves the event for another reason, a "small fix" next year) publishes the
  unreviewed edit, and nothing fails.
- **`edited` keeps the two apart**: `event` is what everyone sees, `edited` is the proposal, and
  `event_update` decides where the proposal goes (the event itself, or its `EventChange`).
- **014's tests still pass with the "simplified" view** (the run for this note tried it): the
  database never changes in those tests. The copy is protection for the next change, which is
  why the code review must check it (014, "Watch out").

## Try this

1. Repeat step 1, but instead of `form.is_valid()` only look at `form.errors` (a template does
   that when it shows the form). It runs the same validation, and `event.title` is
   `'Pasta night'` all the same.
2. 014's view pre-fills the form with `change.copy_fields_to(edited)`. In the shell, make a
   change (`from events.models import EventChange`, `change = EventChange(event=event)`,
   `event.copy_fields_to(change)`, `change.title = "Pasta night"`) and copy it onto `event`
   instead: `change.copy_fields_to(event)`. Now `event.title` is `'Pasta night'` and the
   database still says `'Pizza night'`: the same trap, without a form.

## Belongs to

- [Issue 014](../../issues/014-edit-events-and-pending-changes.md), step 4 ("Why a second
  copy?") and "Watch out".
- [Django: Validation on a ModelForm](https://docs.djangoproject.com/en/6.1/topics/forms/modelforms/#validation-on-a-modelform):
  the warning about the instance.
- [Hypermedia and forms](../learn/hypermedia-and-forms.md), "A Django form does three jobs".
