# Notes

Short notes for future developers and agents. Read this index first, then the notes that match
your task.

## Plan (the students' starting point)

- [App plan](app-plan.md): the students' list of requirements, 1–37. SPEC.md supersedes it.
- [Flow diagram](<Untitled (1).png>): organizer → review → event list → meetup, and "My events".
- [Desktop wireframe](wireframe-desktop.svg) and [mobile wireframe](wireframe-mobile.svg): the
  event list with filters, cards, spots and the Join / Join Waiting List / Not approved states.

## Learn (background for beginners)

- [How a Django request works](learn/how-a-django-request-works.md): from the browser through
  middleware, `urls.py`, the view and the template, status codes, sessions and cookies.
- [Hypermedia and forms](learn/hypermedia-and-forms.md): links and forms, GET or POST, CSRF,
  Django forms, the view pattern, Post/Redirect/Get and messages.
- [Models, migrations and QuerySets](learn/models-migrations-and-querysets.md): tables and
  migrations, lazy queries and lookups, the N+1 problem and how to test for it.
- [Services, transactions and race conditions](learn/transactions-and-race-conditions.md): why
  rules live in services, `atomic`, SQLite's write lock, emails in `on_commit`.
- [Testing with pytest and pytest-django](learn/testing-with-pytest-django.md): fixtures and
  `make_*` factories, the test database, the test client, time, emails and query counts.

## Worked examples

Do each once and watch what happens, with real output to compare; each issue says when.

- [01 Custom user in the shell](examples/01-custom-user-in-the-shell.md) (002): the database refuses a half profile.
- [02 DNS and HTTPS](examples/02-dns-and-https.md) (004): `dig` and `curl -v`, from a name to the lock.
- [03 Photo EXIF](examples/03-photo-exif.md) (006): a photo's GPS position, before and after `PhotoField`.
- [04 Two migrations 0003](examples/04-two-migrations-numbered-0003.md) (007, 010): the conflict and `makemigrations --merge`.
- [05 A request step by step](examples/05-a-request-step-by-step.md) (008, 010): POST, 302, GET with `curl -i`; the CSRF 403.
- [06 N+1 queries](examples/06-n-plus-one-queries.md) (012, 013, 016): break the query-count test, fix it.
- [07 The last-spot race](examples/07-the-last-spot-race.md) (013): two threads, with and without `atomic` and `IMMEDIATE`.
- [08 `on_commit` in a loop](examples/08-on-commit-in-a-loop.md) (013–015): a `lambda` emails the wrong person; `partial`.
- [09 `is_valid()` changes the event](examples/09-modelform-changes-its-instance.md) (014): why the edit view uses a copy.
- [10 A filter that changes the count](examples/10-a-join-that-changes-the-count.md) (016): a join vs `Exists`.

## Workflow

- [Working with git](workflow/git.md): one branch and one pull request per issue, small commits,
  review, merging, conflicts, undoing.

## Deployment (your own VPS with Dokku)

- [Deploy to Dokku](deployment/deploy-to-dokku.md): from ordering an OVHcloud VPS to a running
  site with HTTPS, step by step with the why; environment variables, Brevo email, redeploys,
  logs, troubleshooting.
- [Backups](deployment/backups.md): pull a copy of the database with `scripts/pull-backup.sh`,
  restore it.

## Accounts

- [Email verification links](accounts/email-verification.md): the token, why it works once and
  expires, why the resend page always answers the same.

## Typing

- [Custom QuerySets and pyrefly](typing/custom-querysets.md): the one-line `objects` declaration
  that keeps custom QuerySet methods typed.

## Testing

- Static files in tests](testing/static-files.md): why tests use plain static storage, and why
  `assets/static/.gitkeep` exists.
- [Emails in tests](testing/emails.md): why `mailoutbox` is empty without
  `django_capture_on_commit_callbacks(execute=True)`.
