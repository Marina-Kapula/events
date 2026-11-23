from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User
from config.emails import send_email
from events.models import Event


def event_create(*, event: Event, organizer: User) -> None:
    """Save a new event from the student page and send it to review (SPEC §6.2)."""
    event.organizer = organizer
    event.status = Event.Status.PENDING
    event.full_clean()
    event.save()
    staff = [user.email for user in User.objects.filter(is_staff=True, is_active=True)]
    transaction.on_commit(
        lambda: send_email(
            to=staff, template="events/emails/event_created", context={"event": event}
        )
    )


def event_approve(*, event: Event, now: datetime) -> None:
    if event.status != Event.Status.PENDING:
        raise ValidationError("Only an event waiting for review can be approved.")
    if event.starts_at <= now:
        raise ValidationError("This event has already started: it can't be approved.")
    event.status = Event.Status.APPROVED
    event.full_clean()
    event.save()
    transaction.on_commit(
        lambda: send_email(
            to=[event.organizer.email],
            template="events/emails/event_approved",
            context={"event": event},
        )
    )


def event_reject(*, event: Event, reason: str) -> None:
    if event.status != Event.Status.PENDING:
        raise ValidationError("Only an event waiting for review can be rejected.")
    if not reason.strip():
        raise ValidationError("Write the reason for the organizer in “Review note”.")
    event.status = Event.Status.REJECTED
    event.review_note = reason.strip()
    event.full_clean()
    event.save()
    transaction.on_commit(
        lambda: send_email(
            to=[event.organizer.email],
            template="events/emails/event_rejected",
            context={"event": event},
        )
    )
