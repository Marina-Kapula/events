# 07. The last spot: two students press "Join" at the same moment

An event has one free spot, and two students press Join at the same second. You run that for
real with two threads, against the real SQLite database, three times: with issue 013's
`participation_join` as written, without its `transaction.atomic()`, and without SQLite's
`IMMEDIATE` mode. You'll see 4 people on a 3-person event, then "database is locked", and you'll
know why the service looks the way it does.

Do it after issue 013, step 3 (the services exist). Takes 20 minutes. Undo every change at the
end.

## Setup

Your local database (`var/db.sqlite3`) is migrated. Save this script as `race.py` in the project
folder (don't commit it):

```python
# Two students press "Join" at the same moment, on an event with one free spot.
# Run with: uv run python manage.py shell < race.py
import threading
import time
from datetime import timedelta

from django.db import connection
from django.utils import timezone

from accounts.models import User
from events.models import Event, Participation
from events.services import participation_join

PROFILE = {"photo": "photos/users/x.jpg", "nationality": "ES", "age": 22, "gender": "female"}


def student(n: int) -> User:
    email = f"racer{n}@example.com"
    return User.objects.filter(email=email).first() or User.objects.create_user(
        email, "s3cret-pass", full_name=f"Racer {n}", is_active=True, **PROFILE
    )


# Max 3 people: the organizer, one person going, so ONE spot is left.
event = Event.objects.create(
    title="Race night", description="-", photo="photos/events/x.jpg", city="Avezzano",
    place="Piazza", starts_at=timezone.now() + timedelta(days=1), type="food",
    max_people=3, status=Event.Status.APPROVED, organizer=student(1),
)
Participation.objects.create(event=event, user=student(2), status="going")
start = time.monotonic()


def join(user: User) -> None:
    try:
        mine = Event.objects.get(pk=event.pk)  # each request loads its own event
        result = participation_join(event=mine, user=user, now=timezone.now())
        print(f"{time.monotonic() - start:4.1f}s {user.full_name}: {result.status}")
    except Exception as error:
        print(f"{time.monotonic() - start:4.1f}s {user.full_name}: {error!r}")
    finally:
        connection.close()  # each thread has its own database connection


threads = [threading.Thread(target=join, args=(student(n),)) for n in (3, 4)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()

going = Participation.objects.filter(event=event, status="going").count()
print(f"Spots taken: {1 + going} of {event.max_people}")
```

Each thread is one "request": Django gives every thread its own database connection, as
gunicorn's workers have on the server. (The `except Exception` is only for this experiment: it
prints whatever goes wrong.)

## Steps

### 1. Make each request slow

In `participation_join` (`events/services.py`), between the count and the new `Participation`,
add one line (and `import time` at the top):

```python
        going = Participation.objects.filter(
            event=event, status=Participation.Status.GOING
        ).count()
        time.sleep(1)  # TEMPORARY: a slow request, between the count and the insert
        participation = Participation(
```

A real request is rarely this slow, but it makes the timing easy to see.

### 2. Run it as issue 013 wrote it

```sh
uv run python manage.py shell < race.py
```

```text
 1.0s Racer 4: going
 2.0s Racer 3: waiting
Spots taken: 3 of 3
```

### 3. Remove the transaction

The refactor that "looks harmless" (013, Watch out): delete the line
`with transaction.atomic():` in `participation_join` and move its block four spaces to the
left. Keep the sleep. Run again:

```text
 1.0s Racer 4: going
 1.0s Racer 3: going
Spots taken: 4 of 3
```

### 4. Put the transaction back, remove `IMMEDIATE`

Undo step 3. In `config/settings.py`, comment out `"transaction_mode": "IMMEDIATE",` in
`DATABASES`. Run again:

```text
 1.0s Racer 3: going
 1.0s Racer 4: OperationalError('database is locked')
Spots taken: 3 of 3
```

### 5. Undo everything

Put the `transaction_mode` line back, remove the sleep and `import time`, delete `race.py`.
`git diff` shows nothing, and `uv run pytest` passes. (The "Race night" events stay in your
local database; they don't matter.)

## What just happened

- **Step 2, the code as written.** Racer 4's transaction started first and took SQLite's write
  lock at the `with` line (that's `IMMEDIATE`). Racer 3 *waited* at its own `with` line until
  Racer 4 committed, a second later. Then it counted 2 going, saw the event full, and went on
  the waiting list. Look at the times: 1.0 s and **2.0 s**. The requests ran one after the
  other.
- **Step 3, no transaction.** Both counted "1 going" at the same moment, both slept, both
  inserted `going`. Each was right about what it read; it just read before the other one
  wrote. That's the race (`transactions-and-race-conditions.md`). Remove the sleep too and run
  it a few times: on the laptop used for this note it still happened 5 times out of 5, because
  the two threads start within a millisecond.
- **Step 4, a transaction without `IMMEDIATE`.** SQLite's default starts a transaction without
  the lock and takes it at the first write. Both read, then Racer 3 wrote and committed. Racer
  4 then tried to write on top of data that had changed since it read, and SQLite refused:
  "database is locked". Waiting (the `"timeout": 20`) can't help, because what it read is out
  of date. No overbooking, but an error page instead of a waiting list.
- **The tests can't show this.** They call the service one join after the other, so they check
  the rule ("the last spot, then the waiting list"), and the review checks that the count and
  the insert share one transaction.

## Try this

1. Start three racers instead of two (`for n in (3, 4, 5)`), with step 2's code: one going, two
   waiting, about a second apart.
2. Move only the `count()` above the `with transaction.atomic():` line, and the sleep inside it
   just before `participation = Participation(`. You get `1.0s Racer 3: going`,
   `2.0s Racer 4: going`, `Spots taken: 4 of 3`: Racer 4 waited for the lock, and still
   overbooked, because it counted *before* it waited. That is the first point of 013's "Watch
   out".

## Belongs to

- [Issue 013](../../issues/013-join-leave-and-the-waiting-list.md), step 3 ("Joining") and
  "Watch out".
- [Services, transactions and race conditions](../learn/transactions-and-race-conditions.md).
- SPEC.md §6.4 and §9 (the SQLite options).
