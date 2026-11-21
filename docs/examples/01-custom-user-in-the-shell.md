# 01. The custom user in the shell: the database says no

You make users by hand in Django's shell and watch who refuses them: `full_clean()` in Python,
then the database itself. It is the quickest way to see what issue 002's `CheckConstraint`
really does, and why "a student without a full profile" can't exist, not even through a bug.

Do it after issue 002, step 4 (the migration ran). Takes 10 minutes.

## Setup

Issue 002 is done on your branch, and the database is fresh:

```sh
rm var/db.sqlite3*
uv run python manage.py migrate
uv run python manage.py shell
```

The shell imports your models for you ("12 objects imported automatically"), so `User` is
already there. Type the lines after `>>>`; the output below is from a real run (your password
hash will differ).

## Steps

### 1. A student without a profile

```pycon
>>> User.objects.create_user("Student1@Example.com", "s3cret-pass", full_name="Student 1")
Traceback (most recent call last):
  ...
  File ".../accounts/models.py", line 18, in create_user
    user.full_clean()
django.core.exceptions.ValidationError: {'__all__': ['Constraint “students_have_a_full_profile” is violated.']}
```

### 2. The same student, with a full profile

```pycon
>>> student = User.objects.create_user("Student1@Example.com", "s3cret-pass", full_name="Student 1", photo="photos/users/student1.jpg", nationality="ES", age=22, gender="female")
>>> student.email
'student1@example.com'
>>> student.is_active
False
>>> student.password
'pbkdf2_sha256$1500000$9WSCLXET2AYCGVJIHy3VMA$2Xl6BhgUfws32QkI5X+1gEQmmazrSDkQ+EAKHyaayRk='
>>> student.check_password("s3cret-pass")
True
```

### 3. Try to get around the check

`bulk_create` saves rows without calling `full_clean()`:

```pycon
>>> User.objects.bulk_create([User(email="student2@example.com", full_name="Student 2")])
Traceback (most recent call last):
  ...
sqlite3.IntegrityError: CHECK constraint failed: students_have_a_full_profile

The above exception was the direct cause of the following exception:
  ...
django.db.utils.IntegrityError: CHECK constraint failed: students_have_a_full_profile
```

### 4. Staff need no profile

```pycon
>>> User.objects.create_superuser("staff1@example.com", "s3cret-pass", full_name="Staff 1")
<User: staff1@example.com>
```

### 5. Two more rules

```pycon
>>> User.objects.create_user("STUDENT1@example.com", "s3cret-pass", full_name="Student 1 again", photo="photos/users/x.jpg", nationality="ES", age=22, gender="female")
django.core.exceptions.ValidationError: {'email': ['User with this Email already exists.']}
>>> User.objects.create_user("student3@example.com", "s3cret-pass", full_name="Student 3", photo="photos/users/x.jpg", nationality="ES", age=12, gender="female")
django.core.exceptions.ValidationError: {'age': ['Ensure this value is greater than or equal to 16.']}
>>> User.objects.count()
2
```

### 6. Look at the table itself

Leave the shell (`exit()`) and ask SQLite how it built the table:

```sh
sqlite3 var/db.sqlite3 ".schema accounts_user"
```

```sql
CREATE TABLE "accounts_user" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, ...
  "photo" varchar(100) NOT NULL, "nationality" varchar(2) NOT NULL,
  "age" smallint unsigned NULL CHECK ("age" >= 0), "gender" varchar(10) NOT NULL, ...
  CONSTRAINT "students_have_a_full_profile" CHECK (("is_staff" = 1 OR (NOT ("photo" = '')
  AND NOT ("nationality" = '') AND "age" IS NOT NULL AND NOT ("gender" = '')))));
```

(No `sqlite3` command on your computer? Skip this step, or run
`uv run python manage.py sqlmigrate accounts 0001`, which prints the SQL of the migration.)

## What just happened

- **Step 1** was stopped by Python. `create_user` calls `full_clean()`, which checks the field
  validators *and* the model's constraints before anything is saved. You got a readable
  `ValidationError`, and nothing reached the database.
- **Step 2** shows three things from issue 002: the email was **lowercased** (`Student1@…` became
  `student1@…`), a new user is **inactive** until they verify their email (issue 008), and the
  password is stored as a **salted hash**, never as itself. `check_password` hashes what you give
  it and compares.
- **Step 3** skipped Python's check on purpose, like a buggy script or a hand-written SQL
  `INSERT` would. The **database** refused the row: the rule is written into the table (step 6),
  so no code path can break it. That is why AGENTS.md says "prefer DB constraints for
  invariants", and why issue 002's test uses `bulk_create`.
- **Step 4**: the constraint is "staff, *or* a full profile". Admins pass on the first half.
- **Step 5**: `STUDENT1@example.com` was lowercased first, so it collided with the existing
  `student1@example.com`: one person, one account. Age 12 broke the `MinValueValidator(16)`.

So there are two guards: `full_clean()` gives friendly messages, the constraint is the wall
behind it.

## Try this

1. Start the server (`uv run python manage.py runserver`) and log in at `/accounts/login/` with
   `Student1@Example.com`. It fails with "Please enter a correct email and password": the
   account is inactive. In the shell, `student.is_active = True` then `student.save()`, and log
   in again with the capitalised email. It works: the login form lowercases it (issue 002,
   step 5).
2. Give the staff user a half profile: `User.objects.filter(email="staff1@example.com")
   .update(is_staff=False)`. Which error do you get, and from whom: Python or the database?
3. Change the constraint in `models.py` (drop the `gender` part) and run
   `uv run python manage.py makemigrations --dry-run`: Django sees that the rule changed and
   wants a migration. Undo the change afterwards.

## Belongs to

- [Issue 002](../../issues/002-custom-user-model.md): the model, the manager and the test with
  `bulk_create`.
- [Models, migrations and QuerySets](../learn/models-migrations-and-querysets.md), "Let the
  database do the work".
