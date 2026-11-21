#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# At least 50 characters, or check --deploy warns about it.
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-check-only-not-a-secret-long-enough-for-check-deploy}"
uv run ruff check && uv run ruff format --check && uv run pyrefly check && uv run pytest \
  && DJANGO_DEBUG=false DJANGO_HTTPS=true DJANGO_ALLOWED_HOSTS=example.com \
    EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend \
    uv run python manage.py check --deploy --fail-level WARNING
