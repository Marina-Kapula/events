from collections.abc import Iterable
from datetime import datetime
from functools import partial

from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User
from config.emails import send_email
from events.models import Comment, Event, EventChange, Notification, Participation


def _name(user: User) -> str:
    return "AMFI" if user.is_staff else user.full_name


def notify(
    *, users: Iterable[User], event: Event, text: str, actor: User | None = None
) -> None:
    """Puts a line under each user's bell (our choice, not SPEC).

    Only people on `event` get one: its organizer and whoever is going or waiting.

    `actor` is who did it: their face goes next to the line.
    """
    if actor is not None and actor.is_staff:
        actor = None
    Notification.objects.bulk_create(
        Notification(user=user, event=event, text=text[:200], actor=actor)
        for user in {user.pk: user for user in users}.values()
    )


def _people_on(event: Event) -> list[User]:
    return [
        p.user for p in Participation.objects.filter(event=event).select_related("user")
    ]


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
    notify(
        users=[event.organizer],
        event=event,
        text="Approved: it's live! 🎉",
    )
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
    notify(
        users=[event.organizer],
        event=event,
        text="Not approved: see why.",
    )
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
        if participation.status == Participation.Status.GOING:
            text = f"{_name(user)} is going"
        else:
            text = f"{_name(user)} joined the waiting list"
        notify(users=[event.organizer], event=event, text=text, actor=user)
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
            notify(
                users=[event.organizer],
                event=event,
                text=f"{_name(user)} left",
                actor=user,
            )
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
            notify(
                users=[participation.user],
                event=event,
                text="A spot freed up: you're going!",
            )
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
    notify(
        users=_people_on(event),
        event=event,
        text="The details changed: take a look.",
        actor=event.organizer,
    )
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
    notify(
        users=_people_on(event),
        event=event,
        text="Cancelled.",
        actor=by,
    )
    _email_everyone_on(event, template="events/emails/event_cancelled")


@transaction.atomic
def comment_add(*, event: Event, author: User, text: str) -> Comment:
    """Posts a comment and rings the bell of everyone on the event but the author."""
    if event.status in (Event.Status.CANCELLED, Event.Status.REJECTED):
        raise ValidationError("You can't comment on this event.")
    comment = Comment(event=event, author=author, text=text.strip())
    comment.full_clean()
    comment.save()
    short = comment.text if len(comment.text) <= 60 else comment.text[:59] + "…"
    others = [user for user in [event.organizer, *_people_on(event)] if user != author]
    notify(
        users=others,
        event=event,
        text=f"{_name(author)}: {short}",
        actor=author,
    )
    return comment


def notifications_mark_read(*, user: User, now: datetime) -> None:
    Notification.objects.filter(user=user, read_at=None).update(read_at=now)
