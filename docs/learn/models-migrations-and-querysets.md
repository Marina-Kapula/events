# Models, migrations and QuerySets

Django's ORM lets you work with the database in Python. Three ideas cover almost everything the
issues ask: a **model** describes a table, a **migration** changes the real tables to match the
models, and a **QuerySet** is a query you build step by step and run once.

## A model is a table

```python
class Participation(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="participations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=Status.choices)
    created_at = models.DateTimeField(auto_now_add=True)
```

The class is the table (`events_participation`), each field a column, each instance a row. A
`ForeignKey` is a column holding the other row's id (`event_id`); `participation.event` follows
it, and `event.participations` (the `related_name`) goes the other way.

## Migrations: the history of your tables

Changing `models.py` changes nothing in the database by itself. Two commands do:

```sh
uv run python manage.py makemigrations    # compare the models with the migrations: write a new file
uv run python manage.py migrate           # run the files this database hasn't run yet
```

- A migration is a small Python file in `<app>/migrations/` (`0002_participation.py`). Commit
  it **together with** the model change: your classmates and the server need it too.
- Each database remembers which migrations it has run (the `django_migrations` table), so
  `migrate` only runs the new ones. On the server, Dokku runs `migrate` on every deploy
  (`Procfile`, `release`).
- **Never edit a migration that is merged to `main`** (AGENTS.md): other databases have already
  run it and won't run it again. Make a new one.
- Two branches that both add `0003_…` to one app: `makemigrations --merge`
  (`docs/workflow/git.md`).
- Forgot `makemigrations`? `tests/test_migrations.py` fails: it checks that the models and the
  migrations agree.
- Your local database holds nothing precious: when it is in a mess,
  `rm var/db.sqlite3*` and `migrate` again (issue 002 does this).

## A QuerySet is a query you haven't run yet

```python
events = Event.objects.filter(status=Event.Status.APPROVED)   # no SQL yet
events = events.filter(city__icontains="roma")                # still no SQL
events = events.order_by("starts_at")                         # still none
for event in events:                                          # one query, here
    ...
```

Each `filter()` returns a *new* QuerySet that describes a bigger `WHERE`. The database is only
asked when you need the rows: a `for` loop, `list()`, `len()`, `if events:`, or the template
looping over it. `.count()`, `.exists()` and `.first()` run small queries of their own.

What you write inside `filter()`:

- `field=value`, or `field__lookup=value`: `title__icontains="pizza"`, `starts_at__gte=now`,
  `starts_at__date=day`, `max_people__range=(6, 10)`.
- Across relations, with double underscores: `organizer__full_name__icontains="ana"`, and
  backwards through the `related_name`: `Event.objects.filter(participations__user=user)`.
  Each of these is a SQL join. Mixed with a `Count` over the same relation, the join changes
  what is counted; that's why issue 016 uses an `Exists` subquery instead.
- "Or" needs `Q`: `filter(Q(title__icontains=q) | Q(description__icontains=q))`.

In this project the reads get a name, as methods of a custom QuerySet
(`Event.objects.listed(now=now)`, `.visible_to(user)`): AGENTS.md, Layers, and
`docs/typing/custom-querysets.md`. To see the SQL a QuerySet will run, `print(events.query)` in
`uv run python manage.py shell`.

## The N+1 problem

The event list template shows each organizer's name:

```django
{% for event in events %}{{ event.title }} by {{ event.organizer.full_name }}{% endfor %}
```

The events come in one query. But `event.organizer` wasn't loaded, so Django fetches it when the
template asks, **one query per event**: 1 + N queries. Fine with 3 events on your laptop, slow
with 300 on the server, and invisible unless you count. The fixes:

| You loop over… | Load it with | How |
|---|---|---|
| a `ForeignKey` or one-to-one (`event.organizer`, `event.change`) | `select_related("organizer")` | a JOIN in the same query |
| a reverse or many relation (`event.participations.all`) | `prefetch_related("participations")` | one extra query for all of them |
| a number per row ("5 / 8 spots") | `.annotate(going_count=Count(...))` | computed by the database in the same query |

The view adds them, because the view knows what its template loops over (AGENTS.md). Every list
page has a test that pins the number of queries, with more than one row so a loop shows up:

```python
for _ in range(3):
    make_event()
client.force_login(make_student())

with django_assert_num_queries(3):   # the session, the user, the events
    client.get("/")
```

If someone later shows something new on the card without loading it, the test fails and prints
the extra queries.

## Let the database do the work

- Filter in the QuerySet, never in Python (`[e for e in Event.objects.all() if …]` loads every
  row to keep three).
- `.exists()` to ask "is there one?", `.count()` for "how many?": not `len(list(...))`.
- Rules that must *always* hold go into the database as constraints too (`UniqueConstraint`,
  `CheckConstraint`): they stop a bug that skipped every check in Python (issue 002's test proves
  it with `bulk_create`).

## Further reading

- [Django tutorial, part 2](https://docs.djangoproject.com/en/6.1/intro/tutorial02/): models,
  migrations, the shell and the admin, from scratch.
- [Django: Migrations](https://docs.djangoproject.com/en/6.1/topics/migrations/): what the two
  commands do, and why migration files belong in git.
- [Django: Making queries](https://docs.djangoproject.com/en/6.1/topics/db/queries/), especially
  [lookups that span relationships](https://docs.djangoproject.com/en/6.1/topics/db/queries/#lookups-that-span-relationships).
- [Django: Database access optimization](https://docs.djangoproject.com/en/6.1/topics/db/optimization/):
  when QuerySets run, what they cache, and how to load related objects at once.
- [pytest-django: `django_assert_num_queries`](https://pytest-django.readthedocs.io/en/latest/helpers.html#django-assert-num-queries).
