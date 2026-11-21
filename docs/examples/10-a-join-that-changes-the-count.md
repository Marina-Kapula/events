# 10. A filter that changes the count: `participations__user` vs `Exists`

"My events" shows each card's spots ("4 / 8 spots") on the events a student joined. The obvious
query, `Event.objects.filter(participations__user=me).with_going_count()`, says **1** person is
going when 3 are. Here you see it happen in the shell, see that swapping the two calls "fixes"
it, read the SQL to understand why, and see why issue 016's `joined_by` uses `Exists` instead.

Do it after issue 016, step 1 (`joined_by` exists). Takes 10 minutes.

## Setup

In your local database: an approved event "Pizza night", organized by one student, with three
*other* students going. One of them is `me`. In this run the organizer was
`student1@example.com` and `me` was `student2@example.com`; adapt the emails to yours.
`uv run python manage.py shell`:

```pycon
>>> from events.models import Event, Participation
>>> me = User.objects.get(email="student2@example.com")
>>> pizza = Event.objects.get(title="Pizza night")
>>> for email in ["student2@example.com", "racer3@example.com", "racer4@example.com"]:
...     Participation.objects.create(event=pizza, user=User.objects.get(email=email), status="going")
...
>>> Participation.objects.filter(event=pizza, status="going").count()
3
```

(Reading `going_count` in the shell is fine for looking around; the app's Python code doesn't,
AGENTS.md, Typing.)

## Steps

### 1. The count on its own

```pycon
>>> [(e.title, e.going_count) for e in Event.objects.filter(pk=pizza.pk).with_going_count()]
[('Pizza night', 3)]
```

### 2. "Events I joined", the obvious way

```pycon
>>> [(e.title, e.going_count) for e in Event.objects.filter(participations__user=me).with_going_count()]
[('Pizza night', 1)]
```

### 3. The same two calls, the other way round

```pycon
>>> [(e.title, e.going_count) for e in Event.objects.with_going_count().filter(participations__user=me)]
[('Pizza night', 3)]
```

### 4. Issue 016's `joined_by`, both ways round

```pycon
>>> [(e.title, e.going_count) for e in Event.objects.joined_by(me).with_going_count()]
[('Pizza night', 3)]
>>> [(e.title, e.going_count) for e in Event.objects.with_going_count().joined_by(me)]
[('Pizza night', 3)]
```

### 5. Read the SQL of step 2 and step 4

```pycon
>>> print(Event.objects.filter(participations__user=me).with_going_count().query)
```

```sql
SELECT "events_event".<all columns>,
       COUNT("events_participation"."id") FILTER (WHERE "events_participation"."status" = going) AS "going_count"
FROM "events_event"
LEFT OUTER JOIN "events_participation" ON ("events_event"."id" = "events_participation"."event_id")
WHERE "events_participation"."user_id" = 3
GROUP BY "events_event"."id", ...
```

```pycon
>>> print(Event.objects.joined_by(me).with_going_count().query)
```

```sql
SELECT "events_event".<all columns>,
       EXISTS(SELECT 1 AS "a" FROM "events_participation" "U0" WHERE ("U0"."event_id" = ("events_event"."id") AND "U0"."user_id" = 3 AND "U0"."status" = waiting) LIMIT 1) AS "waiting",
       COUNT("events_participation"."id") FILTER (WHERE "events_participation"."status" = going) AS "going_count"
FROM "events_event"
LEFT OUTER JOIN "events_participation" ON ("events_event"."id" = "events_participation"."event_id")
WHERE EXISTS(SELECT 1 AS "a" FROM "events_participation" "U0" WHERE ("U0"."event_id" = ("events_event"."id") AND "U0"."user_id" = 3) LIMIT 1)
GROUP BY "events_event"."id", ...
```

(Line breaks added; Django prints each query on one line.)

## What just happened

- **A lookup across a relation is a JOIN.** `filter(participations__user=me)` joins each event
  to its participations and keeps the rows where the participation is mine: one row per event,
  *my* row.
- **`Count` reused that same join** (step 2). It counted the rows that were left, and only my
  participation was left: 1. The other two people going were filtered away before the count.
- **The order mattered** (step 3): `annotate()` first, then `filter()`, and Django makes a
  *second* join for the filter, so the count sees every participation again. Correct, but
  fragile: a classmate who "tidies up" the order brings the bug back, and nothing fails.
- **`Exists` is a separate small query** inside `WHERE` ("is there a participation of this user
  for *this* event?"). It adds no join, so the `COUNT` always sees all participations, in any
  order (step 4). That's why 013's `visible_to` and 016's `joined_by` use it.
- **The tests won't tell you.** In the run for this note, 016's tests still passed with a join
  version of `joined_by` (`self.filter(participations__user=user)`, keeping the `waiting`
  annotation), whichever order the view called it in: in those tests `me` is the only person
  on each event, so 1 is the right count. A count bug only shows when *other* people are on the
  event. `Exists` is right by construction, which is the point of 016's step 1.

## Try this

1. A join can also repeat rows. Without a count:
   `[e.title for e in Event.objects.filter(title="Pizza night", participations__status="going")]`
   gives `['Pizza night', 'Pizza night', 'Pizza night']`: one row per person going. `.distinct()`
   hides it; `Exists` never makes it.
2. Add one more person to "Pizza night", with `status="waiting"`, and repeat step 2 with
   *that* student instead of `me`: `going_count` is **0**, while `joined_by` (step 4) still says
   the right number. The join kept only the waiting student's own row, and the count only
   counts `going` rows.

## Belongs to

- [Issue 016](../../issues/016-my-events.md), step 1 (`joined_by` "filters with `Exists`") and
  [013](../../issues/013-join-leave-and-the-waiting-list.md), step 2 (`visible_to`).
- [Models, migrations and QuerySets](../learn/models-migrations-and-querysets.md), "What you
  write inside `filter()`".
- [Django: Order of `annotate()` and `filter()`](https://docs.djangoproject.com/en/6.1/topics/db/aggregation/#order-of-annotate-and-filter-clauses).
