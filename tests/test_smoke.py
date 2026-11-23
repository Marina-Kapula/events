"""Skeleton smoke tests (SPEC.md §11): auth wiring, login and logout, admin."""

from collections.abc import Callable

import pytest
from django.apps import apps
from django.contrib import admin
from django.contrib.auth.models import Group
from django.db.models import Model
from django.test import Client
from django.urls import reverse

# The URLconf unregisters auth.Group, and collection builds the parameter list below
# before any URL is resolved.
import config.urls  # noqa: F401
from accounts.models import User

pytestmark = pytest.mark.django_db

LOGIN_URL = "/accounts/login/"


@pytest.mark.parametrize(
    ("path", "location"),
    [
        ("/", f"{LOGIN_URL}?next=/"),
        ("/?a=1", f"{LOGIN_URL}?next=/%3Fa%3D1"),
    ],
)
def test_anonymous_request_redirects_to_login(
    client: Client, path: str, location: str
) -> None:
    response = client.get(path)

    assert response.status_code == 302
    assert response["Location"] == location


def test_anonymous_logout_goes_to_login_without_next(client: Client) -> None:
    # Logout is login_not_required, so a stale "Log out" form doesn't add next=.
    response = client.post("/accounts/logout/")

    assert response.status_code == 302
    assert response["Location"] == LOGIN_URL


def test_login_page_is_public(client: Client) -> None:
    response = client.get(LOGIN_URL)

    assert response.status_code == 200
    assert b'name="password"' in response.content


def test_login_lands_on_home_and_logout_returns_to_login(
    client: Client, make_student: Callable[..., User]
) -> None:
    make_student(email="student1@example.com")

    response = client.post(
        LOGIN_URL, {"username": "Student1@Example.com ", "password": "s3cret-pass"}
    )
    assert response.status_code == 302
    assert response["Location"] == "/"

    home = client.get("/")
    assert home.status_code == 200
    assert b"student1@example.com" in home.content
    assert b'aria-current="page"' in home.content
    assert b'<form method="post" action="/accounts/logout/">' in home.content

    response = client.post("/accounts/logout/")
    assert response.status_code == 302
    assert response["Location"] == LOGIN_URL
    assert client.get("/").status_code == 302


def test_logout_by_get_does_not_log_out(
    client: Client, make_student: Callable[..., User]
) -> None:
    make_student(email="student1@example.com")
    client.login(username="student1@example.com", password="s3cret-pass")

    response = client.get("/accounts/logout/")

    assert response.status_code == 405
    assert client.get("/").status_code == 200


def test_group_is_not_in_the_admin() -> None:
    assert not admin.site.is_registered(Group)


@pytest.mark.parametrize(
    "model",
    [model for model in apps.get_models() if admin.site.is_registered(model)],
    ids=lambda model: model._meta.label,
)
def test_admin_opens_every_changelist(admin_client: Client, model: type[Model]) -> None:
    opts = model._meta
    url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")

    assert admin_client.get(url).status_code == 200
