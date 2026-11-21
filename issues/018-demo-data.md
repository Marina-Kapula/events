# Demo data for development

Status: todo · Opened: 2026-11-21 · Milestone: M3 · Depends on: 013, 014, 015

## Why

To work on a page you need data in every state: a full event with a waiting list, a rejected one
with its reason, pending changes, a cancelled event, a past one. Making all that by hand, with
several browsers to log in as several students, takes half an hour, and a fresh database (or a
classmate's laptop) starts from zero again.

`manage.py seed_demo` fills your *local* database in a second. It goes **through the services**,
so the data follows the same rules as real data, and it is a small test of the services too. It
refuses to run with `DEBUG` off: every demo account has the same, public password, and that must
never reach your server (SPEC.md §12, M3).

## What you'll build

- A management command `seed_demo` in the `events` app.
- 8 demo students with generated photos (a coloured square with their initials), and a demo admin.
- Events in every state: pending, approved (one full, with a waiting list), approved with
  pending changes, rejected, cancelled, and one in the past.
- `--reset` to throw the demo data away and make it again.
- Tests: it runs, it refuses a second run without `--reset`, and it refuses with `DEBUG` off.

## Before you start

Read:
- SPEC.md §6.2, §6.4, §9 (`DJANGO_DEBUG`); §12 (M3).
- AGENTS.md: the personal data rule (test data is made up: "Student 1",
  `student1@example.com`), Layers.
- [Django: How to create custom django-admin commands](https://docs.djangoproject.com/en/6.1/howto/custom-management-commands/).
- [Pillow: `ImageDraw`](https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html).

What you use from earlier issues: `User.objects.create_user` and `create_superuser` (002); the
services `event_create` (010), `event_approve` and `event_reject` (011), `participation_join`
(013), `event_update` (014) and `event_cancel` (015).

Words you'll meet:
- **Management command**: a `manage.py` subcommand you write yourself, like Django's own
  `migrate` or `createsuperuser`.
- **Seed data**: data put into an empty database so there is something to look at.
- **Idempotent**: safe to run twice. Ours isn't on purpose: a second run stops and asks for
  `--reset`.

## Steps

### 1. Where the command lives

Django finds commands in `<app>/management/commands/<name>.py`. Both folders need an empty
`__init__.py`:

```
events/management/__init__.py
events/management/commands/__init__.py
events/management/commands/seed_demo.py
```

It goes in `events`: it creates users *and* events, and `events` may import `accounts`, not the
other way round (SPEC.md §4).

- [ ] The two packages exist.

### 2. The command

`events/management/commands/seed_demo.py`:

```python
import io
from datetime import timedelta
from typing import override

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from accounts.models import User
from events.models import Event, Participation
from events.services import (
    event_approve,
    event_cancel,
    event_create,
    event_reject,
    event_update,
    participation_join,
)

PASSWORD = "demo-password"
STAFF_EMAIL = "staff@example.com"
STUDENT_EMAILS = tuple(f"student{n}@example.com" for n in range(1, 9))
NATIONALITIES = ("ES", "FR", "DE", "PL", "PT", "NL", "GR", "TR")
GENDERS = (User.Gender.FEMALE, User.Gender.MALE, User.Gender.OTHER)
COLOURS = ("#e76f51", "#2a9d8f", "#e9c46a", "#264653", "#f4a261", "#6d597a")


def placeholder_photo(text: str, number: int) -> ContentFile[bytes]:
    """A coloured square with a few letters on it, as a JPEG."""
    image = Image.new("RGB", (400, 400), COLOURS[number % len(COLOURS)])
    font = ImageFont.load_default(size=150)
    ImageDraw.Draw(image).text((200, 200), text, fill="white", font=font, anchor="mm")
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=85)
    return ContentFile(buffer.getvalue(), name=f"{text.lower()}.jpg")


class Command(BaseCommand):
    help = "Fills the local database with demo students and events (DEBUG only)."

    @override
    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--reset", action="store_true", help="Delete the demo data first."
        )

    @override
    def handle(self, *args: object, **options: object) -> None:
        if not settings.DEBUG:
            msg = "seed_demo runs only with DJANGO_DEBUG=true: its password is public."
            raise CommandError(msg)
        demo_users = User.objects.filter(email__in=(STAFF_EMAIL, *STUDENT_EMAILS))
        if demo_users.exists() and not options["reset"]:
            msg = "The demo data is already there. Run with --reset to start over."
            raise CommandError(msg)

        with transaction.atomic():
            # The old demo data, if any. Events first: their organizer is PROTECT.
            Event.objects.filter(organizer__in=demo_users).delete()
            demo_users.delete()
            self.seed()

        self.stdout.write(self.style.SUCCESS("Demo data is ready."))
        self.stdout.write(f"Every account's password: {PASSWORD}")
        self.stdout.write(f"  {STAFF_EMAIL} (admin)")
        self.stdout.write(f"  {STUDENT_EMAILS[0]} … {STUDENT_EMAILS[-1]} (students)")

    def seed(self) -> None:
        now = timezone.now()
        User.objects.create_superuser(STAFF_EMAIL, PASSWORD, full_name="AMFI Staff")
        students = [
            User.objects.create_user(
                email,
                PASSWORD,
                full_name=f"Student {n}",
                photo=placeholder_photo(f"S{n}", n),
                nationality=NATIONALITIES[n - 1],
                age=19 + n,
                gender=GENDERS[n % len(GENDERS)],
                is_active=True,
            )
            for n, email in enumerate(STUDENT_EMAILS, start=1)
        ]
        first, second, third, fourth, fifth = students[:5]

        def create(
            organizer: User, title: str, kind: str, days: int, max_people: int = 6
        ) -> Event:
            starts_at = timezone.localtime(now + timedelta(days=days))
            event = Event(
                title=title,
                description=f"{title}: come along, everyone is welcome.",
                photo=placeholder_photo(title[:2].upper(), days),
                city="Avezzano",
                place="Piazza Risorgimento",
                starts_at=starts_at.replace(hour=19, minute=0, second=0, microsecond=0),
                type=kind,
                max_people=max_people,
            )
            event_create(event=event, organizer=organizer)
            return event

        # Full, with a waiting list: the organizer and 3 going take the 4 spots,
        # so the last 2 of the 5 who join are waiting.
        pizza = create(first, "Pizza night", Event.Type.FOOD, 3, max_people=4)
        event_approve(event=pizza, now=now)
        for student in students[1:6]:
            participation_join(event=pizza, user=student, now=now)

        # Approved, then edited by the organizer: changes pending.
        hike = create(second, "Hike to Monte Velino", Event.Type.TRIP, 10)
        event_approve(event=hike, now=now)
        participation_join(event=hike, user=first, now=now)
        edited = Event.objects.get(pk=hike.pk)
        edited.place = "Rifugio Sebastiani"
        event_update(event=hike, edited=edited)

        create(third, "Board games", Event.Type.PARTY, 5)  # stays pending

        beach = create(fourth, "Beach day", Event.Type.SPORT, 6)
        event_reject(event=beach, reason="Say which beach, and how people get there.")

        museum = create(fifth, "Museum visit", Event.Type.CULTURE, 4)
        event_approve(event=museum, now=now)
        participation_join(event=museum, user=third, now=now)
        event_cancel(event=museum, by=fifth, now=now)

        # The services refuse the past (rightly), so this one is written directly.
        past = Event(
            title="Welcome aperitivo",
            description="The first evening of the semester.",
            photo=placeholder_photo("WA", 0),
            city="Avezzano",
            place="Bar Centrale",
            starts_at=now - timedelta(days=7),
            type=Event.Type.FOOD,
            max_people=20,
            organizer=first,
            status=Event.Status.APPROVED,
        )
        past.full_clean()
        past.save()
        for student in (second, third, fourth):
            participation = Participation(
                event=past, user=student, status=Participation.Status.GOING
            )
            participation.full_clean()
            participation.save()
```

Why each piece is there:

- **`if not settings.DEBUG`**: your server runs with `DEBUG` off (004), your laptop with it on
  (`.env`). So the command can't create accounts with a public password in production, even if
  someone runs it there by mistake with `dokku run`.
- **Demo accounts have fixed emails**, `student1@example.com` … `student8@example.com` and
  `staff@example.com`. That is how the command finds its own data again, and why it never touches
  your real admin account. `example.com` is reserved for examples: no email can ever reach a real
  person there (AGENTS.md: made-up data only).
- **A second run stops** unless you pass `--reset`, which deletes the old demo users and their
  events first (events first: `organizer` is `PROTECT`; participations and pending changes go with
  their event, `CASCADE`). All of it is in one transaction: if anything fails, your database is as
  it was.
- **Through the services**: `event_create`, `event_approve`, `participation_join`, … check the
  rules and set the states exactly as the app does. If you change a rule later and the seed
  breaks, that is the test telling you something.
- **Except the past event.** Every service refuses to approve or join an event that has started,
  rightly. So that one event and its participations are saved directly, with `full_clean()`
  first, as the fixtures do.
- **`placeholder_photo`** draws a coloured square with a few letters, with Pillow. No real faces:
  the demo data is made up, photos included. `ImageFont.load_default(size=150)` is a font that
  comes with Pillow, so it works on every laptop. `anchor="mm"` puts the middle of the text on
  the middle of the image.
- **`ContentFile(..., name=...)`** is a file in memory. Given to `photo=`, Django saves it under
  `MEDIA_ROOT` (`var/media/photos/...`) when the row is saved, as for an upload.
- **`timezone.localtime(...).replace(hour=19, ...)`**: events at 19:00 Rome time, a few days from
  now, so the list looks real whatever the day.
- **`*args: object, **options: object`**: `options["reset"]` is `True` or `False`, but Django
  hands options over untyped; an `if` is all we do with it.

- [ ] `seed_demo` as above.

### 3. Try it

```sh
uv run python manage.py migrate
uv run python manage.py seed_demo
```

then start the development server as the README says. The command prints the logins:

```
Demo data is ready.
Every account's password: demo-password
  staff@example.com (admin)
  student1@example.com … student8@example.com (students)
```

Log in as `student1@example.com`: "My events" shows a full pizza night, a past aperitivo, and
the hike you joined (with "Changes pending"). Log in as `staff@example.com` and open the admin:
the hike's page has Approve changes and Reject changes. A private browser window lets you be two
people at once.

The services sent emails while seeding (staff were told about new events, organizers about
approvals, …). With the `.env.example` settings they are files in `var/mail/`, and nothing is
sent. Keep it that way while you seed: the addresses are fake.

Run it again: it stops and asks for `--reset`. `seed_demo --reset` makes everything fresh.

- [ ] The command runs on an empty database and prints the logins; the pages show every state.

### 4. Tests

`tests/events/test_seed_demo.py`:

```python
import io

import pytest
from django.core.management import CommandError, call_command
from pytest_django import Settings

from accounts.models import User
from events.models import Event, EventChange, Participation

pytestmark = pytest.mark.django_db


@pytest.fixture
def debug(settings: Settings) -> None:
    settings.DEBUG = True  # pytest-django runs tests with DEBUG off


@pytest.mark.usefixtures("debug")
def test_seed_demo_makes_students_and_events_in_every_state() -> None:
    out = io.StringIO()

    call_command("seed_demo", stdout=out)

    assert User.objects.filter(is_staff=False, is_active=True).count() == 8
    assert {event.status for event in Event.objects.all()} == set(Event.Status)
    assert EventChange.objects.count() == 1
    assert Participation.objects.filter(status=Participation.Status.WAITING).exists()
    assert "student1@example.com" in out.getvalue()


@pytest.mark.usefixtures("debug")
def test_seed_demo_runs_again_only_with_reset() -> None:
    call_command("seed_demo", stdout=io.StringIO())

    with pytest.raises(CommandError, match="--reset"):
        call_command("seed_demo", stdout=io.StringIO())
    call_command("seed_demo", "--reset", stdout=io.StringIO())

    assert User.objects.filter(email="student1@example.com").count() == 1


def test_seed_demo_refuses_without_debug() -> None:
    with pytest.raises(CommandError, match="DJANGO_DEBUG"):
        call_command("seed_demo", stdout=io.StringIO())

    assert not User.objects.exists()
```

- **`settings.DEBUG = True`**: pytest-django runs every test with `DEBUG` off, so without it the
  command would refuse. The `settings` fixture puts the old value back after the test.
- **The photos** go to a temporary folder: 006's autouse fixture sets `MEDIA_ROOT` for every
  test.
- **`call_command`** runs a management command from Python, as `manage.py` would.
  `stdout=io.StringIO()` catches what it prints, so the test can read it (and pytest's output
  stays clean).
- **`set(Event.Status)`** is every status there is: if someone adds a status later, this test
  reminds them to seed it too.

- [ ] The tests above pass.
- [ ] `scripts/check.sh` passes.

## Done when

- [ ] `manage.py seed_demo` creates 8 students with photos, a demo admin, and events in every
      status, with a full event and a waiting list, pending changes, and a past event (test).
- [ ] Every event and sign-up that can be made through a service is (code review).
- [ ] A second run stops unless `--reset` is given; `--reset` starts over (test).
- [ ] With `DEBUG` off it refuses and creates nothing (test).
- [ ] The README's "Development" section mentions `seed_demo` in one line.
- [ ] `scripts/check.sh` passes.
- [ ] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 018-demo-data
```

Suggested commits:
1. `Add the seed_demo command`
2. `Mention seed_demo in the README`
3. `Close 018 in the issue`

Open a pull request titled "Demo data for development". Paste the command's output in the
description, and a screenshot of the event list after seeding.

## Watch out

- **Never run it on the server**, and never set `DJANGO_DEBUG=true` there to make it run. The
  `DEBUG` check is there to stop exactly that.
- **When you add a model field**, the seed may need a value for it: the test fails, and tells you.
- **When a service's signature changes**, update the seed in the same branch. That is the point
  of going through the services.
- **`--reset` deletes the demo users' events** and the sign-ups of anyone on them, your own test
  accounts included. It fails with a `ProtectedError` if the demo admin opened a registration
  window (007: `opened_by` is `PROTECT`): delete that window in the admin first.
- **Old photo files stay** in `var/media/` after a reset (SPEC.md §6.8: files aren't cleaned up).
  Delete the folder if it bothers you; it is git-ignored anyway.

## Further reading

- [Django: How to create custom django-admin commands](https://docs.djangoproject.com/en/6.1/howto/custom-management-commands/)
  (`add_arguments`, `CommandError`, `self.stdout`, `self.style`).
- [Django: `call_command`](https://docs.djangoproject.com/en/6.1/ref/django-admin/#running-management-commands-from-your-code).
- [Django: `ContentFile`](https://docs.djangoproject.com/en/6.1/ref/files/file/#the-contentfile-class).
- [Pillow: `ImageDraw.text`](https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html#PIL.ImageDraw.ImageDraw.text)
  and [text anchors](https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html).
- [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606): why `example.com` is safe for made-up
  addresses.
- [Python: Argparse tutorial](https://docs.python.org/3/howto/argparse.html): `add_arguments`
  hands you an argparse parser, and `--reset` is a `store_true` flag.
- [Pillow: `Image.new`](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.new):
  the coloured square behind each demo photo.
- [Django: The `DEBUG` setting](https://docs.djangoproject.com/en/6.1/ref/settings/#debug): what
  `DEBUG` exposes, and why it is never on in production, which makes it our "is this a laptop?"
  check.
- [Django: How to provide initial data for models](https://docs.djangoproject.com/en/6.1/howto/initial-data/):
  fixtures and data migrations, the usual ways to fill a database. They write rows directly and
  skip the services, which is why we don't use them here.
