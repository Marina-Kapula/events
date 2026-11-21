# 06. N+1 queries: break the query-count test on purpose

One innocent line in a template, `{{ event.organizer.full_name }}`, and the event list runs one
extra database query **per card**. Nothing looks wrong on your laptop with three events. Here you
add that line, watch issue 012's `django_assert_num_queries` test fail and print every query,
then fix it with `select_related`, and (after 013) the same with `prefetch_related`.

Do it after issue 012, step 6 (the list's query-count test passes). Takes 15 minutes. Undo every
change at the end.

## Setup

`tests/events/test_list.py` has 012's last test:

```python
    for _ in range(3):
        make_event()
    client.force_login(make_student())

    # The session, the logged-in user, and the events: however many events there are.
    with django_assert_num_queries(3):
        response = client.get("/")
```

`uv run pytest tests/events/test_list.py -k fixed_number` passes.

## Steps

### 1. Show the organizer on the card

In `events/templates/events/event_list.html`, inside the card, below the city line:

```django
      <p>By {{ event.organizer.full_name }}</p>
```

```sh
uv run pytest tests/events/test_list.py -k fixed_number
```

```text
E   Failed: Expected to perform 3 queries but 6 were done (add -v option to show queries)
FAILED tests/events/test_list.py::test_the_list_page_runs_a_fixed_number_of_queries
```

### 2. Read the queries

```sh
uv run pytest tests/events/test_list.py -k fixed_number -v
```

```text
E   Failed: Expected to perform 3 queries but 6 were done
E   Queries:
E   ========
E   SELECT "django_session"."session_key", ... FROM "django_session" WHERE (... "django_session"."session_key" = 'i7bc6uys…') LIMIT 21
E   SELECT "accounts_user"."id", ... FROM "accounts_user" WHERE "accounts_user"."id" = 4 LIMIT 21
E   SELECT "events_event"."id", "events_event"."title", ... FROM "events_event" WHERE ("events_event"."starts_at" > '2026-11-21 02:14:16.086450' AND "events_event"."status" = 'approved') ORDER BY "events_event"."starts_at" ASC
E   SELECT "accounts_user"."id", ... FROM "accounts_user" WHERE "accounts_user"."id" = 1 LIMIT 21
E   SELECT "accounts_user"."id", ... FROM "accounts_user" WHERE "accounts_user"."id" = 2 LIMIT 21
E   SELECT "accounts_user"."id", ... FROM "accounts_user" WHERE "accounts_user"."id" = 3 LIMIT 21
```

Read them in order: your session, you (user 4), the events, and then **one user per event**: the
three organizers (users 1, 2 and 3), fetched one by one while the template drew each card.

### 3. More events, more queries

Change `range(3)` to `range(10)` (and the `count(b"<article")` line to 10):

```text
E   Failed: Expected to perform 3 queries but 13 were done (add -v option to show queries)
```

That is the "N+1": 1 query for the list, plus N for the organizers (plus the two that every page
pays). With 300 events, 303 queries. Put `range(3)` back.

### 4. The fix: one query with a JOIN

In `events/views.py`, in `event_list`:

```python
    events = Event.objects.listed(now=timezone.now()).select_related("organizer")
```

```sh
uv run pytest tests/events/test_list.py -k fixed_number    # 1 passed
```

To see why, print the SQL in `uv run python manage.py shell`:

```pycon
>>> from events.models import Event
>>> print(Event.objects.listed(now=timezone.now()).select_related("organizer").query)
SELECT "events_event"."id", "events_event"."title", ..., "accounts_user"."id", "accounts_user"."password", ..., "accounts_user"."full_name", ... FROM "events_event" INNER JOIN "accounts_user" ON ("events_event"."organizer_id" = "accounts_user"."id") WHERE (...) ORDER BY "events_event"."starts_at" ASC
```

The organizers now come in the same query as the events.

### 5. Undo

Remove the "By …" line and the `select_related`: the card doesn't show the organizer
(SPEC.md §7), and the test goes back to 3. (Or keep both, if your team decides the card should
show the organizer: then the test still says 3.)

## What just happened

- **Templates run queries.** `event.organizer` was not loaded with the event, only its id
  (`organizer_id`). The first time the template asked for `.full_name`, Django fetched the user,
  one card at a time.
- **The test counted, not timed.** On your laptop the extra queries take microseconds; the
  number is what grows on the server. `django_assert_num_queries` pins the number for any count
  of events, so adding a line to the card without loading its data fails the test right away,
  with the list of queries as the clue.
- **`select_related`** is for a foreign key or one-to-one (one related row per event): a JOIN,
  zero extra queries. For "many per event" you need `prefetch_related` (Try this 1).

## Try this

1. **After issue 013**: show the people going on each card,
   `<p>{% for participation in event.participations.all %}{{ participation.user.full_name }} {% endfor %}</p>`,
   and run 013's `test_the_list_shows_spots_taken_without_extra_queries` (3 events, each with
   one person going and one waiting): `Expected to perform 3 queries but 12 were done` (3, plus
   one participations query per event, plus one user per participation). Add
   `.prefetch_related("participations__user")` to the view's QuerySet: now **5**, and still 5
   with 10 events. The two new ones fetch everything at once:
   `... FROM "events_participation" WHERE "events_participation"."event_id" IN (1, 2, 3) ...` and
   `... FROM "accounts_user" WHERE ("accounts_user"."id") IN ((2), (3), (5), (6), (8), (9))`.
2. Open the list in the browser while `runserver` runs: nothing shows the extra queries. That is
   why the test exists.

## Belongs to

- [Issue 012](../../issues/012-event-list-and-event-page.md) (the list and its query-count
  test), [013](../../issues/013-join-leave-and-the-waiting-list.md) (`with_going_count`, the
  event page's `select_related("user")`), [014](../../issues/014-edit-events-and-pending-changes.md)
  (`select_related("change")`) and [016](../../issues/016-my-events.md) (the same card, a second
  page to keep at 4 queries).
- [Models, migrations and QuerySets](../learn/models-migrations-and-querysets.md), "The N+1
  problem".
