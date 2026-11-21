# 04. Two branches, two migrations numbered 0003

Two of you work in parallel, and both add a field to the same app. Each branch gets a migration
`0003_…`, each one works alone, and the second merge breaks: `migrate` refuses to run. You make
it happen on purpose in a scratch copy, read the errors, and fix it with
`makemigrations --merge`, so the first time it happens for real it is a two-minute job.

Do it after issue 007 is merged (`accounts` has migrations 0001 and 0002). Takes 15 minutes. It
happens in a **scratch copy**: your real repo and GitHub are never touched.

## Setup

```sh
cd ..                                     # the folder above your project
git clone --branch main events events-practice   # use your project folder's name
cd events-practice
cp .env.example .env
uv run python manage.py migrate
```

`main` in the clone is a copy of yours; the two branches below play two classmates.

## Steps

### 1. Classmate A adds a bio

```sh
git switch -c practice-bio
```

In `accounts/models.py`, below `deleted_at`: `bio = models.TextField(blank=True)`. Then:

```sh
uv run python manage.py makemigrations accounts
git add accounts && git commit -m "Add a bio to the profile"
```

```text
Migrations for 'accounts':
  accounts/migrations/0003_user_bio.py
    + Add field bio to user
```

### 2. Classmate B, from the same `main`, adds an Instagram name

```sh
git switch main
git switch -c practice-instagram
```

Below `deleted_at` again: `instagram = models.CharField(max_length=30, blank=True)`. Then:

```sh
uv run python manage.py makemigrations accounts
git add accounts && git commit -m "Add an Instagram name to the profile"
```

```text
Migrations for 'accounts':
  accounts/migrations/0003_user_instagram.py
    + Add field instagram to user
```

### 3. A's pull request is merged first

```sh
git switch main
git merge --no-ff practice-bio -m "Merge: add a bio to the profile"
```

### 4. B brings the new `main` into their branch (`docs/workflow/git.md`)

```sh
git switch practice-instagram
git merge main
```

```text
Auto-merging accounts/models.py
CONFLICT (content): Merge conflict in accounts/models.py
Automatic merge failed; fix conflicts and then commit the result.
```

`accounts/models.py` now holds both versions:

```text
<<<<<<< HEAD
    instagram = models.CharField(max_length=30, blank=True)
=======
    bio = models.TextField(blank=True)
>>>>>>> main
```

Keep both lines, delete the three marker lines, then:

```sh
git add accounts/models.py
git commit --no-edit
```

### 5. Git is happy. Django isn't

```sh
ls accounts/migrations/
uv run python manage.py migrate
```

```text
0001_initial.py
0002_registrationwindow_user_registration_window.py
0003_user_bio.py
0003_user_instagram.py

CommandError: Conflicting migrations detected; multiple leaf nodes in the migration graph: (0003_user_bio, 0003_user_instagram in accounts).
To fix them run 'python manage.py makemigrations --merge'
```

`uv run pytest` fails too: every test that uses the database stops with an `ERROR` and the same
`CommandError`, because pytest-django runs the migrations to build the test database. Only the
few tests without a database pass.

### 6. Merge the migrations

```sh
uv run python manage.py makemigrations --merge
```

```text
Merging accounts
  Branch 0003_user_bio
    + Add field bio to user
  Branch 0003_user_instagram
    + Add field instagram to user

Merging will only work if the operations printed above do not conflict
with each other (working on different fields or models)
Should these migration branches be merged? [y/N] y
Created new merge migration .../accounts/migrations/0004_merge_0003_user_bio_0003_user_instagram.py
```

The new file has no operations, only two parents:

```python
class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_user_bio"),
        ("accounts", "0003_user_instagram"),
    ]

    operations = []
```

### 7. Check, and commit

```sh
uv run python manage.py migrate
uv run python manage.py showmigrations accounts
uv run pytest
git add accounts/migrations
git commit -m "Merge the bio and instagram migrations"
```

```text
 [X] 0001_initial
 [X] 0002_registrationwindow_user_registration_window
 [X] 0003_user_instagram
 [X] 0003_user_bio
 [X] 0004_merge_0003_user_bio_0003_user_instagram
```

and pytest passes again.

## What just happened

- **Two conflicts, from two tools.** Git saw the same lines of `models.py` changed twice and asked
  you (step 4). The two migration files have different names, so git merged them without a word;
  only Django noticed (step 5).
- **Migrations form a chain.** Each one names the one before it in `dependencies`. Both 0003s
  said "I come after 0002", so the chain forked into two ends ("leaf nodes"), and Django won't
  guess which runs first.
- **A merge migration joins the two ends.** It depends on both and does nothing else. It is safe
  here because the two branches touch different fields; Django warns you to check that.
- **The numbers are only names.** Order comes from `dependencies`, not from `0003` or `0004`.
- **What is merged to `main` never changes.** A's 0003 may already have run on your servers
  (every deploy runs `migrate`), so B adds a new file instead of editing or renumbering A's
  (AGENTS.md, Django).

## Try this

1. Before step 6, run `uv run python manage.py makemigrations --check --dry-run`: the same
   `CommandError`. It is what `tests/test_migrations.py` runs.
2. If *your* branch isn't merged yet, there is a second way: `git rm` your own `0003_…` and
   commit, merge `main` (fix `models.py` as in step 4), and run `makemigrations` again. You get
   `0004_user_instagram`, after theirs, and no merge migration. (If you already ran `migrate`
   with your old file, start your local database again: `rm var/db.sqlite3*` and `migrate`.)
3. `git log --oneline --graph --all` draws the two branches and both merges.

When you're done: `cd ..` and delete `events-practice`.

## Belongs to

- [Working with git](../workflow/git.md), "When `main` moved on while you worked".
- [Models, migrations and QuerySets](../learn/models-migrations-and-querysets.md), "Migrations:
  the history of your tables".
- Issues that add migrations: [007](../../issues/007-registration-windows.md),
  [010](../../issues/010-create-an-event.md), [013](../../issues/013-join-leave-and-the-waiting-list.md),
  [014](../../issues/014-edit-events-and-pending-changes.md).
