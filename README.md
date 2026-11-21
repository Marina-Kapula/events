# AMFI Meetups

Events for Erasmus students hosted by AMFI International: students create and join meetups, and
an AMFI admin reviews every event. The design is in [SPEC.md](SPEC.md), the rules for
contributors (people and AI agents) in [AGENTS.md](AGENTS.md), notes in
[docs/index.md](docs/index.md), the work in [issues/_kanban.md](issues/_kanban.md).

## Setup

Requires [uv](https://docs.astral.sh/uv/) and git. uv installs Python 3.14 itself. On Windows,
use Git Bash for the commands below.

```sh
uv sync                                     # runtime + dev dependencies into .venv/
git config core.hooksPath .githooks         # once: runs scripts/check.sh before each commit
cp .env.example .env                        # local settings (DJANGO_DEBUG=true)
uv run python manage.py migrate             # creates var/db.sqlite3
uv run python manage.py createsuperuser     # your admin login
```

## Development

```sh
uv run python manage.py tailwind runserver  # dev server on 127.0.0.1:8000 + Tailwind watcher
uv run python manage.py tailwind build      # one-off stylesheet build
```

The UI uses [daisyUI](https://daisyui.com/components/) components on Tailwind. The first
`tailwind` command downloads one standalone binary with both into `.django_tailwind_cli/` (no
Node). The source is `assets/css/source.css`; the built `assets/static/css/tailwind.css` is
git-ignored.

Emails are not sent in development: `.env.example` writes each one to a file in `var/mail/`.
Open the newest file there to follow an invitation or password-reset link.

## Checks

```sh
scripts/check.sh   # ruff, ruff format, pyrefly (strict), pytest, check --deploy
```

The pre-commit hook in `.githooks/` runs the same script; a commit that fails it is refused.

## Deployment

Each student deploys their own copy on their own VPS with [Dokku](https://dokku.com/)
(`Dockerfile`, `Procfile`, `app.json`). Follow
[docs/deployment/deploy-to-dokku.md](docs/deployment/deploy-to-dokku.md) from the start; backups
are in [docs/deployment/backups.md](docs/deployment/backups.md).

```sh
scripts/pull-backup.sh <VPS_IP> <APP>   # before each deploy
git push dokku main:master              # deploy
```

Production sets `DJANGO_DEBUG=false`, `DJANGO_HTTPS=true`, `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS` and the `EMAIL_*` variables for Brevo (SPEC.md §9); without `EMAIL_HOST`
the app tries an SMTP server on localhost and no email arrives.
