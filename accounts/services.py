from datetime import datetime

from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from accounts.models import RegistrationWindow, User
from config.emails import send_email


def user_register(*, user: User, window: RegistrationWindow, now: datetime) -> None:
    if not window.is_open(now=now):
        raise ValidationError("Registration closed, ask the AMFI staff.")
    user.registration_window = window
    user.full_clean()
    user.save()
    transaction.on_commit(lambda: _send_verification_email(user))


def user_verify(*, uidb64: str, token: str) -> User:
    try:
        user = User.objects.get(
            pk=urlsafe_base64_decode(uidb64).decode(),
            is_active=False,
            deleted_at=None,
        )
    except ValueError, User.DoesNotExist:
        user = None
    if user is None or not default_token_generator.check_token(user, token):
        raise ValidationError("This link was already used, or it is too old.")
    user.is_active = True
    user.full_clean()
    user.save()
    return user


def verification_resend(*, email: str) -> None:
    user = User.objects.filter(email=email, is_active=False, deleted_at=None).first()
    if user is not None:
        transaction.on_commit(lambda: _send_verification_email(user))


def _send_verification_email(user: User) -> None:
    send_email(
        to=[user.email],
        template="accounts/emails/verification",
        context={
            "user": user,
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
    )
