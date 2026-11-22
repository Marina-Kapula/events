from collections.abc import Mapping, Sequence

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


def send_email(
    *, to: Sequence[str], template: str, context: Mapping[str, object] | None = None
) -> None:
    context = {**(context or {}), "site_url": settings.SITE_URL}
    subject = render_to_string(f"{template}_subject.txt", context)
    send_mail(
        subject=" ".join(subject.split()),
        message=render_to_string(f"{template}.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=list(to),
    )