# 08. `on_commit` in a loop: every email goes to the wrong person

`waiting_list_move_up` gives free spots to the people waiting, and emails each of them after the
commit. Issue 013 writes that email with `functools.partial`, not with a `lambda`, and says why
in one sentence. Here you swap in the `lambda`, watch ruff warn, and watch the tests catch every
"You got a spot!" going to the **one student who didn't get a spot**.

Do it after issue 013, step 6 (the participation tests pass). Takes 10 minutes. Issues 014 and
015 loop over people the same way (`_email_everyone_on`).

## Setup

`tests/events/test_participation.py` from issue 013 passes. No other setup.

## Steps

### 1. The bug in plain Python

`uv run python manage.py shell` (or plain `python`):

```pycon
>>> from functools import partial
>>> callbacks = []
>>> for name in ["Student 1", "Student 2", "Student 3"]:
...     callbacks.append(lambda: print("Email to", name))
...
>>> for callback in callbacks:
...     callback()
...
Email to Student 3
Email to Student 3
Email to Student 3
>>> callbacks = []
>>> for name in ["Student 1", "Student 2", "Student 3"]:
...     callbacks.append(partial(print, "Email to", name))
...
>>> for callback in callbacks:
...     callback()
...
Email to Student 1
Email to Student 2
Email to Student 3
```

### 2. The same bug in the service

In `events/services.py`, in `waiting_list_move_up`, replace the `partial(...)` with the version
that "reads better":

```python
            transaction.on_commit(
                lambda: send_email(
                    to=[participation.user.email],
                    template="events/emails/spot_free",
                    context={"event": event, "student": participation.user},
                )
            )
```

### 3. Ruff sees it

```sh
uv run ruff check
```

```text
B023 Function definition does not bind loop variable `participation`
  --> events/services.py:93:25
   |
91 |             transaction.on_commit(
92 |                 lambda: send_email(
93 |                     to=[participation.user.email],
   |                         ^^^^^^^^^^^^^
...
Found 3 errors.
```

(The third error is `F401`: `partial` is now imported but unused.)

### 4. The tests see it

```sh
uv run pytest tests/events/test_participation.py -vv
```

```text
FAILED tests/events/test_participation.py::test_leaving_frees_the_spot_for_the_first_one_waiting
FAILED tests/events/test_participation.py::test_move_up_fills_every_free_spot_oldest_first
```

The second one, in full:

```text
E   AssertionError: assert [['student5@example.com'], ['student5@example.com']] == [['student3@example.com'], ['student4@example.com']]
```

In that test, student 2 is going and students 3, 4 and 5 are waiting; two spots open up.
Students 3 and 4 get the spots. Both emails went to **student 5**, who is still waiting.

### 5. Undo

Put `partial(...)` back (`git restore events/services.py`), and check that `uv run ruff check`
and the tests pass.

## What just happened

- **A lambda doesn't keep values, it keeps names.** `lambda: send_email(to=[participation.user.email], ...)`
  means "when you are called, look up whatever `participation` is *then*". `on_commit` calls it
  after the commit, when the loop has finished.
- **What is `participation` when the loop is over?** The last one the loop looked at. Here the
  loop stopped with `break` at student 5 ("no more spots"), so `participation` was student 5's,
  and both emails used it. Without the `break`, it would be the last person waiting: wrong
  either way.
- **`partial(send_email, to=[participation.user.email], ...)` evaluates its arguments right
  away**, on that pass through the loop, and stores them. When `on_commit` runs it later, each
  call has its own student.
- **Outside a loop a lambda is fine.** `participation_leave` and issue 011's services use one:
  `event` and `user` don't change before the commit. The rule only bites when the variable
  moves, which is why ruff's B023 only fires inside loops.
- **The tests needed `django_capture_on_commit_callbacks(execute=True)`** to run the callbacks at
  all; without it `mailoutbox` would be empty and the bug invisible (`docs/testing/emails.md`).

## Try this

1. Fix the lambda without `partial`: `lambda participation=participation: send_email(...)`. A
   default value is evaluated when the lambda is made, so each lambda keeps its own. Ruff and
   the tests pass. (`partial` is still clearer; it's what the issues use.)
2. In step 1, print `name` after the first loop: it's `'Student 3'`. The loop variable lives on
   after the loop, and that's the value every lambda found.

## Belongs to

- [Issue 013](../../issues/013-join-leave-and-the-waiting-list.md) (`waiting_list_move_up`,
  "Watch out"), [014](../../issues/014-edit-events-and-pending-changes.md) and
  [015](../../issues/015-cancel-an-event.md) (`_email_everyone_on`).
- [Services, transactions and race conditions](../learn/transactions-and-race-conditions.md),
  "Side effects after the commit".
- [Emails in tests](../testing/emails.md).
