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
