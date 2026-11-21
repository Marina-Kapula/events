# syntax=docker/dockerfile:1
# One image for Dokku's processes in Procfile: `release` (migrate) and `web` (gunicorn).
# It includes tzdata, the time zone database DJANGO_TIME_ZONE needs.
FROM python:3.14-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /usr/local/bin/uv

# Log lines reach `docker logs` as they happen, and uv uses this image's Python.
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first, so a code change doesn't reinstall them.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

COPY . .

# Settings refuse to load without a secret key when DEBUG is off; this one is only
# used here. The build opens a database too: a throwaway one, as a database in var/
# would stay in the image, under the storage directory Dokku mounts there. The Tailwind
# CLI (its file name has the version and architecture) stays in a build cache, out of
# the image.
RUN --mount=type=cache,target=/app/.django_tailwind_cli \
    export DJANGO_SECRET_KEY=build-only DJANGO_DB_PATH=/tmp/build.sqlite3 \
    && python manage.py tailwind build \
    && python manage.py collectstatic --noinput \
    && rm -f /tmp/build.sqlite3*

# var/ is where Dokku mounts the storage directory: it holds the SQLite database. gunicorn
# puts its control socket in the home directory.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p var \
    && chown app:app var
USER app
