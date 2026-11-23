from datetime import datetime
from functools import partial

from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User
from config.emails import send_email
from events.models import Event, EventChange, Participation


def _email_staff(*, event: Event, template: str) -> None:
    staff = User.objects.filter(is_staff=True, is_active=True)
    emails = [user.email for user in staff]
    transaction.on_commit(
        partial(send_email, to=emails, template=template, context={"event": event})
    )


def event_create(*, event: Event, organizer: User) -> None:
    """Save a new event from the student page and send it to review (SPEC §6.2)."""
    event.organizer = organizer
    event.status = Event.Status.PENDING
    event.full_clean()
    event.save()
    _email_staff(event=event, template="events/emails/event_created")


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


@transaction.atomic
def event_update(*, event: Event, edited: Event) -> None:
    """Saves the organizer's edit (SPEC.md §6.5).

    `edited` is a second copy of `event` that holds the form's values.
    """
    if event.status == Event.Status.APPROVED:
        # The public version stays as it is until AMFI approves the changes.
        change = EventChange.objects.filter(event=event).first() or EventChange(
            event=event
        )
        edited.copy_fields_to(change)
        change.full_clean()
        change.save()
    else:
        edited.copy_fields_to(event)
        event.status = Event.Status.PENDING
        event.full_clean()
        event.save()
    _email_staff(event=event, template="events/emails/event_edited")


def _email_everyone_on(event: Event, *, template: str) -> None:
    """One email per person going or waiting: they don't see each other's address."""
    participations = Participation.objects.filter(event=event).select_related("user")
    for participation in participations:
        transaction.on_commit(
            partial(
                send_email,
                to=[participation.user.email],
                template=template,
                context={"event": event},
            )
        )


@transaction.atomic
def event_change_approve(*, event: Event, now: datetime) -> None:
    change = EventChange.objects.filter(event=event).first()
    if event.status != Event.Status.APPROVED or change is None:
        raise ValidationError("This event has no changes to approve.")
    if change.starts_at <= now:
        raise ValidationError("The new start time has passed.")
    going = Participation.objects.filter(
        event=event, status=Participation.Status.GOING
    ).count()
    if change.max_people < 1 + going:
        raise ValidationError(
            f"{going} people are going: max people must be at least {1 + going}."
        )
    change.copy_fields_to(event)
    event.full_clean()
    event.save()
    change.delete()
    waiting_list_move_up(event=event)
    transaction.on_commit(
        partial(
            send_email,
            to=[event.organizer.email],
            template="events/emails/event_changed",
            context={"event": event},
        )
    )
    _email_everyone_on(event, template="events/emails/event_changed")


@transaction.atomic
def event_change_reject(*, event: Event, reason: str) -> None:
    change = EventChange.objects.filter(event=event).first()
    if change is None:
        raise ValidationError("This event has no changes to reject.")
    if not reason.strip():
        raise ValidationError("Write the reason in the review note first.")
    event.review_note = reason
    event.full_clean()
    event.save()
    change.delete()
    transaction.on_commit(
        partial(
            send_email,
            to=[event.organizer.email],
            template="events/emails/event_changes_rejected",
            context={"event": event, "reason": reason},
        )
    )


@transaction.atomic
def event_cancel(*, event: Event, by: User, now: datetime) -> None:
    """Cancels the event for good (SPEC.md §2 #27).

    `by` is who cancels: the organizer (only before the start) or staff (any time).
    """
    if event.status == Event.Status.CANCELLED:
        raise ValidationError("This event is already cancelled.")
    if not by.is_staff and event.starts_at <= now:
        raise ValidationError("This event has already started.")
    EventChange.objects.filter(event=event).delete()
    event.status = Event.Status.CANCELLED
    event.full_clean()
    event.save()
    _email_everyone_on(event, template="events/emails/event_cancelled")
