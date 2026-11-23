from django.http import HttpRequest

from accounts.models import User
from events.models import Notification


def unread_notifications(request: HttpRequest) -> dict[str, int]:
    """The red number on the bell, on every page."""
    user = getattr(request, "user", None)
    if not isinstance(user, User):
        return {}
    count = Notification.objects.filter(user=user, read_at=None).count()
    return {"unread_notifications": count}
