# Log in with an email: a custom user model

Status: done · Opened: 2026-11-21 · Milestone: M1 · Depends on: — · Blocks: every issue with a
migration

## Why

Students register with their email address, and every student has a profile: a photo, a
nationality, an age and a gender (SPEC.md §2 #6, #10, #12). Django's built-in `User` logs in with
a *username* and has none of these fields.

Django lets a project replace its user model, but only **at the very start**: once tables point at
the built-in user, switching is painful. The Django docs say it plainly: *"If you're starting a new
project, it's highly recommended to set up a custom user model."* That is why this issue comes
first, and why nothing else with a migration should be merged before it.

## What you'll build

- A new app, `accounts`, with a `User` model that logs in with an email.
- The profile fields on that model, so a student can never exist without them.
- The login page asks for the email, and doesn't care about upper or lower case.
- A "Users" page in the Django admin.
- Tests that prove it.

Nothing new is visible to students yet: registration comes in issue 008.

## Before you start

Read:
- SPEC.md §2 #6, #10, #12, #14, #36; §5 (the `accounts.User` table); §8 (Users).
- AGENTS.md: Typing, and Django.
- `docs/learn/models-migrations-and-querysets.md` (models and migrations) and
  `docs/learn/testing-with-pytest-django.md` (fixtures, for step 7), if they are new to you.
- [Django: Substituting a custom User model](https://docs.djangoproject.com/en/6.1/topics/auth/customizing/#substituting-a-custom-user-model)
  and the [full example](https://docs.djangoproject.com/en/6.1/topics/auth/customizing/#a-full-example)
  on the same page: this issue follows it closely.

Words you'll meet:
- **`AbstractBaseUser`**: the smallest base for a user. It gives you a password, `last_login` and
  the login machinery, and you add every other field yourself.
- **`PermissionsMixin`**: adds `is_superuser`, groups and permissions, which the Django admin needs.
- **Manager**: the `User.objects` object. Ours knows how to create users and superusers by email.
- **`CheckConstraint`**: a rule the *database* enforces, so even buggy code can't break it.

## Steps

### 1. Add the two packages the fields need

A photo is an `ImageField`, which needs [Pillow](https://pillow.readthedocs.io/), and a
nationality is a `CountryField` from [django-countries](https://pypi.org/project/django-countries/)
(SPEC.md §3).

```sh
uv add pillow django-countries
```

- [ ] `pyproject.toml` and `uv.lock` list both packages.

### 2. Create the `accounts` app

```sh
uv run python manage.py startapp accounts
```

Delete the files you won't use yet (`views.py`, `tests.py`: our tests live in `tests/`). Add the
app to `INSTALLED_APPS` in `config/settings.py`, together with `django_countries`, and tell Django
which user model to use:

```python
INSTALLED_APPS: list[str] = [
    # ... Django's apps ...
    "django_tailwind_cli",
    "django_countries",
    "accounts",
]

AUTH_USER_MODEL: str = "accounts.User"
```

- [ ] The app exists and is installed; `AUTH_USER_MODEL` is set.

### 3. Write the model and its manager

`accounts/models.py`:

```python
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
```

Why each piece is there:

- **The profile fields are `blank=True` (and `age` is `null=True`)** because admins have no
  profile. The `CheckConstraint` then says: *either you are staff, or every profile field is
  filled in*. So the "complete your profile" problem from the students' plan can't happen
  (SPEC.md §2 #10).
- **`is_active` defaults to `False`**: a new student can't log in until they click the link in
  the verification email (issue 008).
- **`deleted_at`** is for the soft delete in issue 017. **`registration_window`** from SPEC.md §5
  is *not* here yet: its model doesn't exist until issue 007, which adds the field.
- **The email is lowercased** in `create_user`, because phones capitalise the first letter and
  `Student@x.com` would otherwise be a second account (SPEC.md §2 #36).
- **`REQUIRED_FIELDS` is a `ClassVar[list[str]]`**: Django's type stubs declare it that way, and
  ruff wants mutable class attributes annotated.
- **Why not `AbstractUser` with `username = None`?** It is shorter, but strict pyrefly rejects
  assigning `None` to a field (`bad-assignment`). `AbstractBaseUser` + `PermissionsMixin` is the
  clean way.

- [ ] `accounts/models.py` as above.

### 4. Make the migration on a fresh database

Your local database (`var/db.sqlite3`) was created with Django's built-in user. Throw it away; it
has nothing you need:

```sh
rm var/db.sqlite3*
uv run python manage.py makemigrations accounts
uv run python manage.py migrate
uv run python manage.py createsuperuser     # asks for email, full name and password
```

- [ ] `accounts/migrations/0001_initial.py` exists and `migrate` runs on an empty database.

If you already deployed the skeleton (issue 004 comes *after* this one on purpose), the server's
database has the old user table too: delete it there as well before deploying this
(`/var/lib/dokku/data/storage/<APP>/db.sqlite3*`), then run `createsuperuser` again with
`dokku run`.

### 5. Let the login page take any capitalisation

Django's `LoginView` uses an `AuthenticationForm`, whose field is still called `username` (it
holds whatever `USERNAME_FIELD` is). Lowercase it before Django checks the password.

`accounts/forms.py`:

```python
from typing import override

from django.contrib.auth.forms import AuthenticationForm


class EmailAuthenticationForm(AuthenticationForm):
    """Django's login form, with the email lowercased (SPEC.md §2 #36)."""

    @override
    def clean(self) -> dict[str, object]:
        username = self.cleaned_data.get("username")
        if isinstance(username, str):
            self.cleaned_data["username"] = username.strip().lower()
        return super().clean()
```

In `config/urls.py`, hand it to the login view:

```python
from accounts.forms import EmailAuthenticationForm

path(
    "accounts/login/",
    auth_views.LoginView.as_view(authentication_form=EmailAuthenticationForm),
    name="login",
),
```

The login template already prints the field's label (`{{ form.username.label }}`), so it now says
"Email". Change the input to `type="email"` while you are there.

- [ ] Logging in with `Student1@Example.com` works for `student1@example.com`.

### 6. The Users page in the admin

`accounts/admin.py`:

```python
from typing import override

from django.contrib import admin
from django.http import HttpRequest

from accounts.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin[User]):
    list_display = ("email", "full_name", "nationality", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff")
    search_fields = ("email", "full_name")
    ordering = ("email",)
    fields = (
        "email",
        "full_name",
        "photo",
        "nationality",
        "age",
        "gender",
        "is_active",
        "is_staff",
        "date_joined",
        "deleted_at",
    )
    readonly_fields = ("date_joined", "deleted_at")

    # Students come only through registration, admins from `createsuperuser`.
    @override
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
```

We use a plain `ModelAdmin`, not Django's `UserAdmin`: that one is built around a `username` and
first/last names we don't have. Setting passwords happens through password reset (issue 009).

- [ ] `/admin/accounts/user/` lists users; there is no "Add user" button.

### 7. Tests

Test data comes from small factory fixtures in `tests/conftest.py` (AGENTS.md). Add these below
the existing fixture; every later issue uses them:

```python
import itertools
from collections.abc import Callable

from accounts.models import User

PASSWORD = "s3cret-pass"


@pytest.fixture
def make_student(db: None) -> Callable[..., User]:
    numbers = itertools.count(1)

    def make(email: str | None = None, **overrides: object) -> User:
        n = next(numbers)
        fields: dict[str, object] = {
            "full_name": f"Student {n}",
            # A file name is enough for the model; a test that needs an image makes one.
            "photo": "photos/users/student.jpg",
            "nationality": "ES",
            "age": 22,
            "gender": User.Gender.FEMALE,
            "is_active": True,
            **overrides,
        }
        return User.objects.create_user(
            email or f"student{n}@example.com", PASSWORD, **fields
        )

    return make


@pytest.fixture
def make_staff(db: None) -> Callable[..., User]:
    numbers = itertools.count(1)

    def make(**overrides: object) -> User:
        n = next(numbers)
        fields: dict[str, object] = {"full_name": f"Staff {n}", **overrides}
        return User.objects.create_superuser(
            f"staff{n}@example.com", PASSWORD, **fields
        )

    return make


@pytest.fixture
def admin_user(make_staff: Callable[..., User]) -> User:
    # pytest-django's own admin_user doesn't know our required full_name.
    return make_staff()
```

The last fixture **replaces** pytest-django's `admin_user` (a fixture with the same name in your
`conftest.py` wins). Without it, `admin_client` crashes: pytest-django calls `create_superuser`
without a `full_name`.

Then `tests/accounts/__init__.py` (empty) and `tests/accounts/test_models.py`:

```python
from collections.abc import Callable

import pytest
from django.db import IntegrityError

from accounts.models import User

pytestmark = pytest.mark.django_db


def test_create_user_lowercases_the_email(make_student: Callable[..., User]) -> None:
    user = make_student(email=" Student@Example.COM ")

    assert user.email == "student@example.com"


def test_a_student_needs_a_full_profile() -> None:
    # bulk_create skips full_clean, so only the database constraint can stop it.
    with pytest.raises(IntegrityError):
        User.objects.bulk_create([User(email="x@example.com", full_name="No profile")])


def test_staff_need_no_profile(make_staff: Callable[..., User]) -> None:
    staff = make_staff()

    assert staff.is_staff
    assert staff.is_superuser
    assert staff.is_active
    assert staff.photo == ""
```

Finally, `tests/test_smoke.py` still creates users the old way (`create_user("student1", …)`).
Switch those tests to `make_student`, and log in with the email. Use a capitalised one, so the
test proves step 5:

```python
def test_login_lands_on_home_and_logout_returns_to_login(
    client: Client, make_student: Callable[..., User]
) -> None:
    make_student(email="student1@example.com")

    response = client.post(
        LOGIN_URL, {"username": "Student1@Example.com ", "password": "s3cret-pass"}
    )
    assert response.status_code == 302
    # ... the rest as before, with b"student1@example.com" for the name in the header
```

- [ ] The tests above pass. `test_admin_opens_every_changelist` now opens the Users page too.
- [ ] `scripts/check.sh` passes.

## Done when

- [ ] `AUTH_USER_MODEL = "accounts.User"`, and `accounts/migrations/0001_initial.py` creates it.
- [ ] `createsuperuser` asks for email, full name and password, and the admin can log in.
- [ ] A student without a full profile can't be saved: the database refuses it (test).
- [ ] Emails are stored lowercase, and login ignores case (tests).
- [ ] The admin shows users, without an Add button.
- [ ] `scripts/check.sh` passes.
- [ ] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 002-custom-user-model
```

Suggested commits, one per step (each one passes `scripts/check.sh`):
1. `Add Pillow and django-countries`
2. `Add the accounts app with an email-based User model`
3. `Lowercase the email on the login page`
4. `Show users in the admin`
5. `Add user factories and model tests`
6. `Close 002 in the issue`

Open a pull request titled "Log in with an email: a custom user model". Ask the reviewer to look
at the `CheckConstraint` in particular. `docs/workflow/git.md` has every step.

## Watch out

- **Merge this before any other issue that makes a migration.** Every model that points at a
  user (events, participations, registration windows) must point at `accounts.User` from its
  first migration.
- **`settings.AUTH_USER_MODEL`, not `User`, in other apps' foreign keys**:
  `models.ForeignKey(settings.AUTH_USER_MODEL, ...)`. The Django docs explain why under
  [Referencing the User model](https://docs.djangoproject.com/en/6.1/topics/auth/customizing/#referencing-the-user-model).
- **`full_clean()` in `create_user`** runs the field validators and the `CheckConstraint`
  *before* saving, so you get a clear `ValidationError` instead of a database error.
- **`bulk_create` skips `full_clean`**. That's why the constraint test uses it: it proves the
  database itself refuses the row.

## Worked example

- [01, the custom user in the shell](../docs/examples/01-custom-user-in-the-shell.md): after step
  4, make users by hand and watch `full_clean()`, then the database's `CheckConstraint`, refuse a
  half profile.

## Further reading

- [Django: Customizing authentication](https://docs.djangoproject.com/en/6.1/topics/auth/customizing/),
  the whole page, especially "Specifying a custom user model".
- [Django: Constraints reference](https://docs.djangoproject.com/en/6.1/ref/models/constraints/)
  (`CheckConstraint`, `Q` objects).
- [Django: Managers](https://docs.djangoproject.com/en/6.1/topics/db/managers/).
- [pytest-django: fixtures](https://pytest-django.readthedocs.io/en/latest/helpers.html)
  (`client`, `admin_client`, `django_db`).
- [django-countries README](https://github.com/SmileyChris/django-countries#readme).
- [Django tutorial, part 2](https://docs.djangoproject.com/en/6.1/intro/tutorial02/): models,
  migrations and the admin from scratch, on a small example. Do it first if this issue is a lot
  at once.
- [Django: Migrations](https://docs.djangoproject.com/en/6.1/topics/migrations/): what
  `makemigrations` and `migrate` do, and why the migration file goes into git.
- [Django: Password management](https://docs.djangoproject.com/en/6.1/topics/auth/passwords/):
  `set_password` stores a salted hash, never the password itself.
- [mypy: Type hints cheat sheet](https://mypy.readthedocs.io/en/stable/cheat_sheet_py3.html):
  how to read `str | None`, `ClassVar[list[str]]` and `Callable[..., User]`; pyrefly checks the
  same hints.
- [Adam Johnson: Test for pending migrations](https://adamj.eu/tech/2024/06/23/django-test-pending-migrations/):
  the idea behind `tests/test_migrations.py`, which fails when you forget `makemigrations`.
