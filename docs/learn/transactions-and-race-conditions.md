# Services, transactions and race conditions

The rules of the app (the last spot, the waiting list, who may cancel) live in `services.py`
functions (AGENTS.md, Layers). This note explains the three tools those functions use:
transactions, the database's write lock, and `transaction.on_commit` for emails.

## Why a service

The same rule is reached from many places: a student's button, an admin button, the demo-data
command, a test. If "is there a free spot?" were checked in the view, the admin and the seed
command would skip it. A service is the one place:

```python
def participation_join(*, event: Event, user: User, now: datetime) -> Participation:
```

It checks the rules, raises `ValidationError` with a sentence the user can read when one is
broken, writes, and schedules the emails. The view only finds out *who* is asking, calls it,
and turns its answer into a message and a redirect.

## Transactions: all or nothing

Cancelling an event sets its status *and* deletes its pending changes. If the code crashed
between the two, the database would hold half a cancel. A transaction prevents that:

```python
with transaction.atomic():
    EventChange.objects.filter(event=event).delete()
    event.status = Event.Status.CANCELLED
    event.full_clean()
    event.save()
```

Leaving the `with` block normally **commits** (everything is saved at once); an exception
**rolls back** (nothing is saved). `@transaction.atomic` above a function does the same for the
whole function (issue 015's `event_cancel`). An `atomic` inside another `atomic` simply becomes
part of the outer one, so services can call each other.

## A race condition, step by step

An event has 8 places: the organizer and 6 people going, so one spot is left. Two students press
"Join" at the same second, and two requests run side by side:

| | Request A (Student 1) | Request B (Student 2) |
|---|---|---|
| 1 | counts: 1 + 6 going < 8, a spot is free | |
| 2 | | counts: 1 + 6 going < 8, a spot is free |
| 3 | saves Student 1 as `going` | |
| 4 | | saves Student 2 as `going`: **9 people for 8 places** |

Each request was right about what it read; it just read before the other one wrote. That is a
**race condition**. Tests that call the service one after the other never see it; forty
students scanning the same QR code at a welcome meeting will.

## The fix: one transaction, and SQLite's write lock

1. **Count and insert inside the same `atomic` block**, and check every rule in there too
   (after `event.refresh_from_db()`, so a cancel that just happened is seen).
2. **SQLite lets one connection write at a time.** With `"transaction_mode": "IMMEDIATE"`
   (already in `config/settings.py`) a transaction takes that write lock when it *starts*. So
   request B stops at the `with` line and waits (up to `"timeout": 20` seconds) until A commits:

| | Request A | Request B |
|---|---|---|
| 1 | starts the transaction, takes the lock | tries to start: waits |
| 2 | counts 6 going, saves `going`, commits | still waiting |
| 3 | | gets the lock, counts **7** going: saves `waiting` |

Without `IMMEDIATE`, both would read at once and B's write would fail with "database is locked":
an error page instead of a place on the waiting list.

Keep transactions short: everyone else waits while one is open. That's another reason emails
are not sent inside them (next section). On PostgreSQL you would lock just the event's row with
`select_for_update()`; SQLite locks the whole database instead, which is fine at our size.

## Side effects after the commit: `on_commit`

An email can't be taken back. If a service emailed "You got a spot!" and the transaction then
rolled back, the student would be told something that never happened. So emails wait until the
data is really saved:

```python
transaction.on_commit(partial(send_email, to=[user.email], template=..., context=...))
```

`on_commit` runs the function after the commit, and drops it on a rollback. Use
`functools.partial` rather than a `lambda`, at least inside a loop: a lambda looks its variables
up when it *runs*, after the loop has finished, so every email would go to the last person.
`partial` stores the values right away (ruff's rule B023 warns about the lambda).

## In tests

pytest-django runs each test inside a transaction that is rolled back at the end, so the commit
never comes and `on_commit` callbacks never run: `mailoutbox` stays empty. Wrap the call in
`django_capture_on_commit_callbacks(execute=True)` (`docs/testing/emails.md`).

A race is hard to reproduce in a test, so the tests check the rule itself ("the last spot, then
the waiting list"), and the review checks that the count and the insert share one transaction.

## Checklist for a new service

- Keyword-only arguments; model instances and plain values, never `request`; `now` passed in.
- `with transaction.atomic():` around anything that reads and then writes, or writes twice.
- Every rule checked inside the transaction; a broken one raises `ValidationError`.
- `full_clean()` before `save()`.
- Emails in `transaction.on_commit`, with `partial`.
- A test for each rule and its forbidden case, and each email checked in `mailoutbox`.

## Further reading

- [Django: Database transactions](https://docs.djangoproject.com/en/6.1/topics/db/transactions/):
  `atomic`, nested blocks, and `on_commit`.
- [Django: SQLite transaction behavior](https://docs.djangoproject.com/en/6.1/ref/databases/#sqlite-transaction-behavior)
  and [SQLite: Write-Ahead Logging](https://www.sqlite.org/wal.html) (readers don't block the
  writer, and there is one writer at a time).
- [Giovanni Collazo: Optimal SQLite settings for Django](https://gcollazo.com/optimal-sqlite-settings-for-django/):
  the settings this project uses (`IMMEDIATE`, WAL, `synchronous=NORMAL`), and why.
- [Adam Johnson: use `partial()` with `transaction.on_commit()`](https://adamj.eu/tech/2022/08/22/use-partial-with-djangos-transaction-on-commit/):
  the late-binding bug, shown in a loop.
- [Django: Validating objects](https://docs.djangoproject.com/en/6.1/ref/models/instances/#validating-objects):
  what `full_clean()` checks, and why `save()` doesn't.
