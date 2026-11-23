from datetime import datetime
from functools import partial

from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User
from config.emails import send_email
from events.models import Event, Participation


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


def participation_join(*, event: Event, user: User, now: datetime) -> Participation:
    """Put `user` on the event: going if a spot is free, else waiting (SPEC §6.4)."""
    # With SQLite's IMMEDIATE mode the transaction takes the write lock right here: a
    # second join waits until this one commits, then counts the spot we just took.
    with transaction.atomic():
        event.refresh_from_db()
        if event.status != Event.Status.APPROVED or event.starts_at <= now:
            raise ValidationError("This event is not open for sign-ups.")
        if user.is_staff:
            raise ValidationError("Staff don't join events.")
        if event.organizer == user:
            raise ValidationError("You organize this event: you already have a spot.")
        if Participation.objects.filter(event=event, user=user).exists():
            raise ValidationError("You are already on this event.")
        going = Participation.objects.filter(
            event=event, status=Participation.Status.GOING
        ).count()
        participation = Participation(
            event=event,
            user=user,
            status=Participation.Status.GOING
            if 1 + going < event.max_people
            else Participation.Status.WAITING,
        )
        participation.full_clean()
        participation.save()
    return participation


def participation_leave(*, event: Event, user: User, now: datetime) -> None:
    """Take `user` off the event, going or waiting (SPEC §6.4)."""
    with transaction.atomic():
        if event.status != Event.Status.APPROVED or event.starts_at <= now:
            raise ValidationError("You can't leave this event any more.")
        participation = Participation.objects.filter(event=event, user=user).first()
        if participation is None:
            raise ValidationError("You are not on this event.")
        participation.delete()
        if participation.status == Participation.Status.GOING:
            transaction.on_commit(
                lambda: send_email(
                    to=[event.organizer.email],
                    template="events/emails/participant_left",
                    context={"event": event, "participant": user},
                )
            )
            waiting_list_move_up(event=event)


def waiting_list_move_up(*, event: Event) -> None:
    """While a spot is free, give it to whoever has waited longest (SPEC §6.4)."""
    with transaction.atomic():
        going = Participation.objects.filter(
            event=event, status=Participation.Status.GOING
        ).count()
        waiting = Participation.objects.filter(
            event=event, status=Participation.Status.WAITING
        ).select_related("user")
        for participation in waiting:
            if 1 + going >= event.max_people:
                break
            participation.status = Participation.Status.GOING
            participation.full_clean()
            participation.save()
            going += 1
            # partial, not lambda: a lambda would see the loop's last participation.
            transaction.on_commit(
                partial(
                    send_email,
                    to=[participation.user.email],
                    template="events/emails/spot_free",
                    context={"event": event, "student": participation.user},
                )
            )
