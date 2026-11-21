"""Django settings, driven by environment variables (SPEC.md §9)."""

from pathlib import Path

import django_stubs_ext
from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, env_list, env_str, load_dotenv

django_stubs_ext.monkeypatch()

BASE_DIR: Path = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

DEBUG: bool = env_bool("DJANGO_DEBUG", default=False)

_secret_key = env_str("DJANGO_SECRET_KEY")
if _secret_key is None:
    if not DEBUG:
        msg = "DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false."
        raise ImproperlyConfigured(msg)
    _secret_key = "django-insecure-local-development-only"
SECRET_KEY: str = _secret_key

ALLOWED_HOSTS: list[str] = env_list(
    "DJANGO_ALLOWED_HOSTS", default=("127.0.0.1", "localhost")
)

# Behind Dokku's nginx, which terminates TLS and sets X-Forwarded-Proto. Without
# trusting that header Django sees plain HTTP, and the login POST fails the CSRF
# origin check.
_https = env_bool("DJANGO_HTTPS", default=False)
SECURE_PROXY_SSL_HEADER: tuple[str, str] | None = (
    ("HTTP_X_FORWARDED_PROTO", "https") if _https else None
)
SESSION_COOKIE_SECURE: bool = _https
CSRF_COOKIE_SECURE: bool = _https
SECURE_HSTS_SECONDS: int = 365 * 24 * 60 * 60 if _https else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS: bool = _https
SILENCED_SYSTEM_CHECKS: list[str] = [
    # SECURE_SSL_REDIRECT: nginx redirects HTTP to HTTPS, and Dokku's healthcheck
    # reaches the container over plain HTTP, so Django must not redirect it.
    "security.W008",
    # SECURE_HSTS_PRELOAD: preloading covers a whole registered domain, not one
    # host name.
    "security.W021",
]

INSTALLED_APPS: list[str] = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_tailwind_cli",
    "django_countries",  # country list for the nationality field
    "accounts",  # users
]

# Use our own User model instead of Django's built-in one.
AUTH_USER_MODEL: str = "accounts.User"

MIDDLEWARE: list[str] = [
    "django.middleware.security.SecurityMiddleware",
    # Serves STATIC_ROOT when DEBUG is off: no web server in front handles /static/.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Every view needs a login, unless it is marked with @login_not_required.
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF: str = "config.urls"

TEMPLATES: list[dict[str, object]] = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION: str = "config.wsgi.application"

_db_path = Path(env_str("DJANGO_DB_PATH", "var/db.sqlite3")).expanduser()
DB_PATH: Path = _db_path if _db_path.is_absolute() else BASE_DIR / _db_path
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASES: dict[str, dict[str, object]] = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DB_PATH,
        "OPTIONS": {
            # WAL lets readers proceed while a write is in progress.
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
        },
    },
}

_VALIDATION = "django.contrib.auth.password_validation"
AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = [
    {"NAME": f"{_VALIDATION}.UserAttributeSimilarityValidator"},
    {"NAME": f"{_VALIDATION}.MinimumLengthValidator"},
    {"NAME": f"{_VALIDATION}.CommonPasswordValidator"},
    {"NAME": f"{_VALIDATION}.NumericPasswordValidator"},
]

LOGIN_URL: str = "login"
LOGIN_REDIRECT_URL: str = "/"
LOGOUT_REDIRECT_URL: str = "login"

LANGUAGE_CODE: str = "en-us"
TIME_ZONE: str = env_str("DJANGO_TIME_ZONE", "Europe/Rome")
USE_I18N: bool = False
USE_TZ: bool = True

STATIC_URL: str = "static/"
# The built stylesheet and the scripts live here; the Tailwind source stays outside the
# static files (assets/css/source.css), so collectstatic never publishes it.
STATICFILES_DIRS: list[Path] = [BASE_DIR / "assets" / "static"]
# collectstatic's output (git-ignored), built into the Docker image.
STATIC_ROOT: Path = BASE_DIR / "staticfiles"
STORAGES: dict[str, dict[str, str]] = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Content-hashed, compressed copies that WhiteNoise serves with far-future caching.
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

# django-tailwind-cli: `manage.py tailwind build` writes the stylesheet to
# STATICFILES_DIRS[0]/css/tailwind.css (git-ignored), and the standalone binary is
# downloaded into .django_tailwind_cli/. With daisyUI it is tailwind-cli-extra
# (Tailwind and daisyUI in one binary), so the version is that project's: 2.10.35
# bundles Tailwind 4.3.4 and daisyUI 5.7. Pinned, so builds are reproducible and need
# no GitHub API lookup.
TAILWIND_CLI_USE_DAISY_UI: bool = True
TAILWIND_CLI_VERSION: str = "2.10.35"
TAILWIND_CLI_SRC_CSS: str = "assets/css/source.css"
TAILWIND_CLI_DIST_CSS: str = "css/tailwind.css"

# Email (verification links, password resets, notifications), set through EMAIL_*
# variables.
# The options depend on the backend; an unknown one raises KeyError.
_EMAIL_BACKEND = env_str("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
_EMAIL_OPTIONS: dict[str, dict[str, object]] = {
    "django.core.mail.backends.smtp.EmailBackend": {
        "host": env_str("EMAIL_HOST", "localhost"),
        "port": int(env_str("EMAIL_PORT", "587")),
        "username": env_str("EMAIL_HOST_USER", ""),
        "password": env_str("EMAIL_HOST_PASSWORD", ""),
        "use_tls": env_bool("EMAIL_USE_TLS", default=True),
        "use_ssl": env_bool("EMAIL_USE_SSL", default=False),
        "timeout": 10,
    },
    # Each email is written to a file here and nothing is sent.
    "django.core.mail.backends.filebased.EmailBackend": {
        "file_path": BASE_DIR / "var" / "mail"
    },
}
MAILERS: dict[str, dict[str, object]] = {
    "default": {"BACKEND": _EMAIL_BACKEND, "OPTIONS": _EMAIL_OPTIONS[_EMAIL_BACKEND]}
}
