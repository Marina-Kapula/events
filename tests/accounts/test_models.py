from collections.abc import Callable

import pytest
from django.db import IntegrityError

from accounts.models import User

pytestmark = pytest.mark.django_db


def test_create_user_lowercases_the_email(make_student: Callable[..., User]) -> None:
    user = make_student(email=" Student@Example.COM ")

    assert user.email == "student@example.com"


def test_a_student_needs_a_full_profile() -> None:
    with pytest.raises(IntegrityError):
        User.objects.bulk_create([User(email="x@example.com", full_name="No profile")])


def test_staff_need_no_profile(make_staff: Callable[..., User]) -> None:
    staff = make_staff()

    assert staff.is_staff
    assert staff.is_superuser
    assert staff.is_active
    assert staff.photo == ""
