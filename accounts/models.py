from typing import ClassVar, override

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django_countries.fields import CountryField


class UserManager(BaseUserManager["User"]):
    def create_user(
        self, email: str, password: str | None = None, **fields: object
    ) -> User:
        user = self.model(email=email.strip().lower(), **fields)
        user.set_password(password)
        user.full_clean()
        user.save(using=self._db)
        return user

    def create_superuser(
        self, email: str, password: str | None = None, **fields: object
    ) -> User:
        fields.update(is_staff=True, is_superuser=True, is_active=True)
        return self.create_user(email, password, **fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Gender(models.TextChoices):
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        OTHER = "other", "Other"

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=100)
    photo = models.ImageField(upload_to="photos/users/", blank=True)
    nationality = CountryField(blank=True)
    age = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(16), MaxValueValidator(99)]
    )
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = ["full_name"]

    class Meta:
        constraints = (
            models.CheckConstraint(
                condition=Q(is_staff=True)
                | (
                    ~Q(photo="")
                    & ~Q(nationality="")
                    & Q(age__isnull=False)
                    & ~Q(gender="")
                ),
                name="students_have_a_full_profile",
            ),
        )

    @override
    def __str__(self) -> str:
        return self.email
