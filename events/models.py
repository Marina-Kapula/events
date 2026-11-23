from typing import override

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


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


class EventQuerySet(models.QuerySet["Event"]):
    """Reads of events. Issue 012 adds the event list's methods here."""


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
