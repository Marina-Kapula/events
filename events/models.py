from datetime import date, datetime
from typing import Self, override

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Case, Count, Exists, OuterRef, Q, When

from accounts.models import User


class EventFields(models.Model):
    """The fields an organizer fills in. Issue 014's EventChange reuses them."""

    class Type(models.TextChoices):
        MEETUP = "meetup", "Meetup"
        FOOD = "food", "Food"
        TRIP = "trip", "Trip"
        SPORT = "sport", "Sport"
        PARTY = "party", "Party"
        CULTURE = "culture", "Culture"
        OTHER = "other", "Other"

    title = models.CharField(max_length=80)
    description = models.TextField()
    photo = models.ImageField(upload_to="photos/events/")
    city = models.CharField(max_length=60)
    place = models.CharField(max_length=120)
    starts_at = models.DateTimeField()
    type = models.CharField(max_length=10, choices=Type.choices)
    max_people = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(2), MaxValueValidator(100)],
        help_text="Including you, the organizer.",
    )
    language = models.CharField(max_length=40, default="English")

    class Meta:
        abstract = True

    def copy_fields_to(self, other: EventFields) -> None:
        """Copies the editable fields (the ones of this class) onto `other`."""
        for field in EventFields._meta.fields:
            setattr(other, field.name, getattr(self, field.name))


class Size(models.TextChoices):
    """The size filter of the event list (SPEC §2 #29)."""

    SMALL = "small", "Up to 5 people"
    MEDIUM = "medium", "6 to 10 people"
    LARGE = "large", "More than 10 people"


class EventQuerySet(models.QuerySet["Event"]):
    def listed(self, *, now: datetime) -> Self:
        """The event list: approved or pending, not started yet, soonest first.

        Pending events are listed too, marked "Not approved yet" (our choice, not SPEC).
        """
        return self.filter(
            status__in=(Event.Status.APPROVED, Event.Status.PENDING), starts_at__gt=now
        ).order_by("starts_at")

    def visible_to(self, user: User) -> Self:
        """The events whose page `user` may open (SPEC §6.3)."""
        is_on_it = Exists(Participation.objects.filter(event=OuterRef("pk"), user=user))
        return self.filter(
            Q(status__in=(Event.Status.APPROVED, Event.Status.PENDING))
            | Q(organizer=user)
            | (Q(status=Event.Status.CANCELLED) & is_on_it)
        )

    def with_going_count(self) -> Self:
        """Adds `going_count`: how many people are going, the organizer not counted."""
        return self.annotate(
            going_count=Count(
                "participations",
                filter=Q(participations__status=Participation.Status.GOING),
            )
        )

    def organized_by(self, user: User) -> Self:
        return self.filter(organizer=user)

    def joined_by(self, user: User) -> Self:
        """Events `user` is going to or waiting for; `waiting` says which."""
        mine = Participation.objects.filter(event=OuterRef("pk"), user=user)
        return self.filter(Exists(mine)).annotate(
            waiting=Exists(mine.filter(status=Participation.Status.WAITING))
        )

    def upcoming_first(self, *, now: datetime) -> Self:
        """Upcoming events first, then the past and cancelled ones; by start."""
        upcoming = Q(starts_at__gt=now) & ~Q(status=Event.Status.CANCELLED)
        return self.order_by(Case(When(upcoming, then=0), default=1), "starts_at")

    def search(self, text: str) -> Self:
        return self.filter(Q(title__icontains=text) | Q(description__icontains=text))

    def in_city(self, text: str) -> Self:
        return self.filter(city__icontains=text)

    def on_date(self, *, day: date) -> Self:
        # The day in the site's time zone (Europe/Rome), not in UTC.
        return self.filter(starts_at__date=day)

    def of_type(self, event_type: str) -> Self:
        return self.filter(type=event_type)

    def of_size(self, size: Size) -> Self:
        match size:
            case Size.SMALL:
                return self.filter(max_people__lte=5)
            case Size.MEDIUM:
                return self.filter(max_people__range=(6, 10))
            case Size.LARGE:
                return self.filter(max_people__gt=10)


class Event(EventFields):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    organizer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # pyrefly sees as_manager() as a plain Manager; the manager proxies the QuerySet's
    # methods (docs/typing/custom-querysets.md).
    objects: EventQuerySet = EventQuerySet.as_manager()  # pyrefly: ignore[bad-assignment]

    @override
    def __str__(self) -> str:
        return self.title


class EventChange(EventFields):
    """An organizer's edit of an approved event, waiting for AMFI (SPEC.md §2 #17)."""

    event = models.OneToOneField(Event, on_delete=models.CASCADE, related_name="change")
    created_at = models.DateTimeField(auto_now_add=True)

    @override
    def __str__(self) -> str:
        return f"Changes to {self.event}"


class Participation(models.Model):
    class Status(models.TextChoices):
        GOING = "going", "Going"
        WAITING = "waiting", "Waiting"

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="participations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="participations",
    )
    status = models.CharField(max_length=10, choices=Status.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("event", "user"), name="one_participation_per_user_and_event"
            ),
        )
        # First come, first served: the waiting list moves up in this order.
        ordering = ("created_at", "id")

    @override
    def __str__(self) -> str:
        return f"{self.user} {self.status} {self.event}"
