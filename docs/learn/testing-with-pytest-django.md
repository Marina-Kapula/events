# Testing with pytest and pytest-django

Every issue ends with tests, and `scripts/check.sh` runs them before each commit. A test is a
small program that sets up a situation, does one thing, and checks the result. It runs in
milliseconds, every time, so a rule you broke by accident shows up before your pull request.

## A test is a function with `assert`

```python
def test_the_organizer_cannot_join(make_event: Callable[..., Event]) -> None:
    event = make_event()

    with pytest.raises(ValidationError, match="You organize this event"):
        participation_join(event=event, user=event.organizer, now=timezone.now())
```

- pytest finds files named `tests/<app>/test_*.py` and functions named `test_*`.
- A plain `assert` is enough: when it fails, pytest prints the values on both sides.
- `pytest.raises` checks that the code raises the exception (and, with `match=`, the message).
- The blank lines split the test into **arrange** (make the data), **act** (the one call you
  test) and **assert**. The name says the rule in plain English.

Running them:

```sh
uv run pytest                                       # everything
uv run pytest tests/events/test_participation.py    # one file
uv run pytest -k waiting                            # tests whose name contains "waiting"
uv run pytest -x --lf                               # stop at the first failure; only last failures
```

## Fixtures: what a test asks for

A test's arguments are **fixtures**: pytest sees the name, builds the value, and passes it in.
pytest-django brings `client`, `admin_client`, `mailoutbox`, `settings`,
`django_capture_on_commit_callbacks` and `django_assert_num_queries`. Ours live in
`tests/conftest.py`, which every test file sees without importing it:

- **`make_student`, `make_staff`, `make_event`, `make_participation`, …** are *factories*: a
  fixture that returns a function, so a test can make as many objects as it needs and set only
  the fields it is about: `make_event(max_people=3)`. They call `full_clean()`, so test data
  follows the same rules as real data, and it is always made up ("Student 1",
  `student1@example.com`: AGENTS.md).
- A fixture in `conftest.py` with the same name as a pytest-django one **replaces** it. That's how
  issue 002 gives `admin_user` a full name.
- `@pytest.fixture(autouse=True)` runs for every test in its file (or, in `conftest.py`, every
  test) without being asked; code after its `yield` runs when the test is over. pytest's own
  `tmp_path` is a new, empty folder for each test.

## The database in tests

- `pytestmark = pytest.mark.django_db` at the top of a file lets its tests use the database.
  Without it: "Database access not allowed".
- The tests get their own empty database, built from the migrations, and every test runs inside
  a transaction that is **rolled back** at the end. So tests never see each other's data, and
  their order doesn't matter.
- The catch: the commit never happens, so `transaction.on_commit` callbacks (our emails) never
  run. Wrap the call in `django_capture_on_commit_callbacks(execute=True)`
  (`docs/testing/emails.md`).

## Testing a page

The test client sends requests through the whole app, middleware and templates included
(`how-a-django-request-works.md`):

```python
def test_staff_get_a_404_on_the_create_page(
    client: Client, make_staff: Callable[..., User]
) -> None:
    client.force_login(make_staff())

    response = client.get("/events/new/")

    assert response.status_code == 404
```

- `client.force_login(user)` logs in without a password; without it you get a 302 to the login
  page.
- `client.post(url, {"field": "value"})` sends a form. `follow=True` follows the redirect, so
  `response.content` is the next page, message included, and `response.redirect_chain` lists
  the redirects.
- `response.content` is bytes: `assert b"You left the event." in response.content`. Django
  escapes HTML, so `You're going` appears as `You&#x27;re going`.
- **Test the forbidden case too**: another student's event, staff, a started event, a GET on a
  POST-only URL. The bug that matters is usually the one that lets the wrong person in.

## Time without waiting

Rules that depend on the time take `now` as an argument (AGENTS.md), so a test picks the moment
instead of waiting for it:

```python
now = timezone.now()
event = make_event(starts_at=now + timedelta(days=1))

with pytest.raises(ValidationError):
    participation_join(event=event, user=make_student(), now=now + timedelta(days=2))
```

## Emails and query counts

```python
with django_capture_on_commit_callbacks(execute=True):
    participation_leave(event=event, user=student, now=now)

assert [m.to for m in mailoutbox] == [[event.organizer.email]]
```

`mailoutbox` lists the emails sent during the test (nothing really leaves). For list pages,
`django_assert_num_queries(n)` fails when the page runs a different number of queries
(`models-migrations-and-querysets.md`, the N+1 problem).

## When a test fails

Read the output from the bottom: the `assert` line and the values pytest shows. `-vv` shows
long values in full, `-s` shows your `print()` output. If a test passes when it shouldn't,
break the code on purpose and check that it fails: a test that can't fail proves nothing.

## Further reading

- [pytest: Get started](https://docs.pytest.org/en/stable/getting-started.html): a first test,
  `assert`, and `pytest.raises`.
- [pytest: How to use fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html), in
  particular "Factories as fixtures" and "Overriding fixtures on various levels";
  [parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html) runs one test with
  several inputs (as `tests/test_smoke.py` does).
- [pytest-django: Database access](https://pytest-django.readthedocs.io/en/latest/database.html)
  and [helpers](https://pytest-django.readthedocs.io/en/latest/helpers.html) (`client`,
  `mailoutbox`, `django_assert_num_queries`, …).
- [Django: The test client](https://docs.djangoproject.com/en/6.1/topics/testing/tools/#the-test-client):
  `get`, `post`, `follow`, `force_login`, and what a response holds.
