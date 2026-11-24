"""Sends email through Brevo's HTTPS API instead of SMTP.

Render's free plan blocks the SMTP ports (25, 465, 587); HTTPS on 443 is open. Set
EMAIL_BACKEND=config.brevo.BrevoEmailBackend and BREVO_API_KEY on the host only.
API: https://developers.brevo.com/reference/sendtransacemail
"""

import json
import urllib.request
from collections.abc import Sequence
from email.utils import parseaddr
from typing import Any, override

from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.core.mail.backends.base import BaseEmailBackend

API_URL = "https://api.brevo.com/v3/smtp/email"


def _contacts(addresses: Sequence[str]) -> list[dict[str, str]]:
    contacts: list[dict[str, str]] = []
    for address in addresses:
        name, email = parseaddr(address)
        contacts.append({"email": email, **({"name": name} if name else {})})
    return contacts


def payload(message: EmailMessage) -> dict[str, object]:
    """The JSON Brevo expects for one message."""
    data: dict[str, object] = {
        "sender": _contacts([message.from_email])[0],
        "to": _contacts(message.to),
        "subject": message.subject,
        "textContent": message.body,
    }
    if message.cc:
        data["cc"] = _contacts(message.cc)
    if message.bcc:
        data["bcc"] = _contacts(message.bcc)
    if message.reply_to:
        data["replyTo"] = _contacts(message.reply_to)[0]
    if isinstance(message, EmailMultiAlternatives):
        for content, mimetype in message.alternatives:
            if mimetype == "text/html":
                data["htmlContent"] = content
    return data


class BrevoEmailBackend(BaseEmailBackend):
    def __init__(
        self, *, api_key: str = "", fail_silently: bool = False, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self.fail_silently = fail_silently
        if not api_key:
            msg = "BREVO_API_KEY must be set to send email through Brevo."
            raise ImproperlyConfigured(msg)
        self.api_key = api_key

    @override
    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        sent = 0
        for message in email_messages:
            if not message.recipients():
                continue
            request = urllib.request.Request(
                API_URL,
                data=json.dumps(payload(message)).encode(),
                headers={
                    "api-key": self.api_key,
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=10):
                    pass
            except OSError:
                if not self.fail_silently:
                    raise
            else:
                sent += 1
        return sent
