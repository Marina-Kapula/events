from typing import override

from django.core.management.base import BaseCommand

from accounts.models import User
from config.env import env_str


class Command(BaseCommand):
    help = (
        "Creates the AMFI admin from DJANGO_ADMIN_EMAIL and DJANGO_ADMIN_PASSWORD, "
        "once. For hosts with no shell to run createsuperuser, as Render's free plan."
    )

    @override
    def handle(self, *args: object, **options: object) -> None:
        email = env_str("DJANGO_ADMIN_EMAIL", "").strip().lower()
        password = env_str("DJANGO_ADMIN_PASSWORD", "")
        if not email or not password:
            self.stdout.write(
                "DJANGO_ADMIN_EMAIL or DJANGO_ADMIN_PASSWORD unset: skipped."
            )
            return
        if User.objects.filter(email=email).exists():
            # Never resets the password: change it in the admin instead.
            self.stdout.write(f"{email} already exists.")
            return
        User.objects.create_superuser(email, password, full_name="AMFI")
        self.stdout.write(f"Admin {email} created.")
