# Rules for agents and contributors

This is a student project: a small, idiomatic, hypermedia-driven Django app. The server sends
HTML; links and forms move the user through the app, with full page loads and as little
JavaScript as possible (no HTMX). Reach for Django's own features first (forms, auth views,
messages, the admin, template inheritance and partials, QuerySets), and prefer the plain Django
way a student can read and explain over anything clever.

- Run `scripts/check.sh` before calling any code change done; it must pass. On a fresh checkout, run
  `cp .env.example .env` first. On Windows, run it from Git Bash (`bash scripts/check.sh`).
- SPEC.md is the design. Read the sections for your task first; when a decision changes, update
  SPEC.md in the same branch. `docs/app-plan.md` is the students' original plan; SPEC.md wins
  where they differ.
- Personal data: students' photos, nationality, age and gender. Test data, fixtures, examples and
  commit messages are made up ("Student 1", `student1@example.com`); never a real person.
- Typing:
  - strict pyrefly;
  - no `.values()`/`.values_list()`;
  - Python code doesn't read `.annotate()` attributes (they aren't typed; templates may): if it
    must, a function returns a dataclass;
  - Django hook overrides carry `@override`;
  - declarative Django class attributes are tuples;
  - `# pyrefly: ignore[code]` only with a reason.
- Never commit `var/` (database, emails, uploaded photos) or `.env`.
- New dependencies need an explicit decision (update SPEC.md §3).

## Layers
- Reads are custom `QuerySet` methods on the model (`Event.objects.upcoming(now=now)`), declared
  as `objects: EventQuerySet = EventQuerySet.as_manager()` with the ignore explained in
  `docs/typing/custom-querysets.md`. Methods that depend on the time take `now` as a keyword
  argument; tests pass fixed times.
- Plain create or edit of one model, with no rule or side effect beyond its own fields (the
  profile): a `ModelForm`, and the view calls `form.save()` (`commit=False` first to set the
  owner).
- Everything else goes through a function in the app's `services.py`: state changes (create,
  approve, reject, cancel), anything touching several models, rules (spots, the waiting list),
  emails.
  - Plain, type-annotated functions with keyword-only args, named `<entity>_<action>`
    (`event_approve`, `participation_leave`).
  - They take model instances and primitives, never `request`.
  - They call `full_clean()` before `save()`, and raise `ValidationError` for a broken rule; the
    view shows it.
- Not in templates, `save()` overrides or signals.
- Prefer DB constraints (unique, check) for invariants.
- Model properties and methods only for values from the model's own fields.
- Views `select_related`/`prefetch_related` what the template loops over; each list page has a
  test with `django_assert_num_queries`.

## Views and templates
- Function-based views. No generic class-based views or view mixins (Django's auth views for
  login, logout and passwords are fine).
- Views return full HTML pages, never JSON. No HTMX, no `fetch()`.
- Anything that changes data is a POST (a button in a small form), never a GET link.
- On success, redirect (Post/Redirect/Get) and say what happened with `django.contrib.messages`.
  On errors, render the same page again with the bound form, status 200.
- Views check who may do what (the organizer for their own event, the admin for reviews);
  everyone else gets a 404. Tests cover the forbidden case.
- Style with the UI library chosen in SPEC.md §2 #19 (issue 003); prefer its components over
  hand-written CSS.
- Reuse markup with Django's template partials: `{% partialdef name %}` in the page template,
  `{% include "app/page.html#name" %}` from another page. Not separate `_fragment.html` files.
- UI-only state (open/close, focus, Esc, dismiss) uses HTML/CSS first (`<dialog>`, `popover`,
  `commandfor`, `<details>`, `inert`, `:has()`), then plain JS in `assets/static/js/ui.js`, no
  build step, no framework. JS never decides what the server decides: free spots, who may join,
  what an event's state allows.
- `{% csrf_token %}` in every POST form. Never `csrf_exempt`.
- No `|safe` or `mark_safe` on anything user-derived.

## Django
- Never edit or delete a migration merged to main. Data migrations use `apps.get_model`.
- Multi-write services use `transaction.atomic`; emails and other side effects go in
  `transaction.on_commit`.
- Tests: `tests/<app>/test_*.py` through `django.test.Client`; data from the `make_*` fixtures in
  `tests/conftest.py`; emails checked in `mailoutbox`, inside
  `django_capture_on_commit_callbacks(execute=True)` (`docs/testing/emails.md`).
- Links in emails and the QR code start with `settings.SITE_URL`, never `request`.

## Style
- Smallest change that solves the problem, in the fewest files.
- No new abstractions, base classes, or helpers until a pattern repeats.
- No dead code, unused params, or fallback branches.
- No `try/except` without a real fallback; catch specific exceptions; let bad state fail loudly.
- Comments only when the *why* isn't obvious. No docstrings that restate the code.
- No new dependencies or infrastructure (task queue, Redis, cache) without asking first.
- Commits: short subjects like `Fix …`, `Add …`, `Remove …`; one behavioral change each.

## Subagents (for issues and hard tasks)
- For execution of the task use: Sonnet
- After task finished, request a review from subagent: Opus
- If reviewer requests changes, spawn Sonnet subagent for fix.
- Loop until reviewer + typechecker + tests pass.

## Notetaking and Finding (for future devs and agents)
- If something needs to be remembered take notes in the `docs` folder.
- Keep the notes minimal, keep only the important information that can't be guessed or is hard to
  guess.
- Structure the `docs` folder to be easy to navigate; separate the notes by domains and operations.
- On notes, reference files if necessary.
- While reading the notes: read the index (`docs/index.md`) first and find the notes relevant to
  the task you are working on.

## Git (`docs/workflow/git.md`)
- Issues are `issues/NNN-slug.md`, tracked in `issues/_kanban.md`. One feature branch per issue,
  named like the file (`007-registration-windows`), made from an up-to-date `main`.
- Small commits, each one change with a short imperative subject. Never commit to `main` directly.
- Push the branch and open a pull request on GitHub; it is reviewed before it is merged (merge
  commit `Merge NNN: <summary>`), then the branch is deleted.
- The issue's last commit ticks its tasks and sets its `Status:` line to done. Branches don't touch
  `issues/_kanban.md`; whoever merges moves the card on `main`.
- If working on an issue branch, subagents can commit.
- If work needs to be done in parallel, use worktrees.
