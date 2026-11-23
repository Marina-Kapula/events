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
