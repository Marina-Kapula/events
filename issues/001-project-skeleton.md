# Project skeleton: settings, login, base layout, Tailwind and the quality gate

Status: done · Opened: 2026-11-20 · Done: 2026-11-20 · Depends on: —

## Problem

The repo had a bare `django-admin startproject` (`config/`), a `requirements.txt` and the
students' plan in `docs/`. Every later issue needs a project that starts, a login, a base layout
to extend, a stylesheet and a quality gate that runs before each commit.

## Proposal

Copy the skeleton of the teacher's reference projects, with their later generic
additions (`tests/test_migrations.py`, `Dockerfile`, `Procfile`, `app.json`, `.dockerignore`),
and their email settings. No app exists yet: `INSTALLED_APPS` holds Django's contrib apps
and `django_tailwind_cli`. Their HTMX parts (django-htmx, `HtmxLoginRequiredMiddleware` and
its tests) were removed after the interview chose no HTMX (SPEC §2 #2).

## Tasks

- [x] `pyproject.toml` (SPEC §3) and `uv.lock` from the reference projects' lock, with Django upgraded to the
      latest 6.1 patch; remove `requirements.txt`
- [x] `manage.py`, `config/{env,settings,urls,views,wsgi,asgi}.py`, `.env.example`
- [x] `MAILERS` from the `EMAIL_*` variables; `.env.example` writes emails to `var/mail/`
- [x] `assets/css/source.css`, `assets/static/.gitkeep`; `manage.py tailwind build` works
- [x] `templates/base.html`, `templates/registration/login.html`, `templates/home.html`
      (placeholder at `/`, name `home`; the event list replaces it and keeps the name)
- [x] `scripts/check.sh`, `.githooks/pre-commit`, `.gitattributes`
- [x] `Dockerfile`, `Procfile`, `app.json`, `.dockerignore` (Dokku)
- [x] `AGENTS.md`, `CLAUDE.md`, `README.md`, `SPEC.md` (§1–§3, §9–§11), `docs/index.md`,
      `issues/_kanban.md`, `.claude/skills/grill-me/`
- [x] Student deployment guide: `docs/deployment/`, `scripts/pull-backup.sh`,
      `scripts/server/nginx-login-limit.sh`
- [x] Tests: `tests/test_smoke.py`, `tests/test_migrations.py`, `tests/config/test_env.py`,
      `tests/config/test_settings.py`, `tests/conftest.py`
- [x] `scripts/check.sh` passes

## Decisions

- **Django 6.1.3, not the reference lock's 6.1.1**: the students were already on 6.1.3 (security
  patches). Every other version is the reference projects' verified lock.
- **Email is in the skeleton**: invitations and password resets need it from the first feature
  issue, and it adds no dependency.
- **`.gitattributes` forces LF**: `requirements.txt` came from a Windows machine (UTF-16, CRLF).
  With `core.autocrlf=true` a CRLF `check.sh` fails in bash, so the hook would break there.
- **No HTMX** (SPEC §2 #2): Django's `LoginRequiredMiddleware` replaces the reference projects' HTMX-aware one.
- **A default UI, not a fixed one** (SPEC §2 #19): Tailwind + daisyUI through
  `TAILWIND_CLI_USE_DAISY_UI` (tailwind-cli-extra 2.10.35); the base, login and home templates use
  daisyUI components, and `base.html` shows messages. Issue 003 lets the students keep or replace
  it.
- **The deployment guide is written from the teacher's private notes** with every private value
  replaced by a placeholder (`<VPS_IP>`, `<APP>`): each student deploys their own copy (SPEC §2 #4).
- **Left to the feature issues** (SPEC §12): the user model, Pillow and media files,
  django-countries, segno.

## References

- SPEC §3, §9, §10, §11.
