# Static files in tests

- Production settings use WhiteNoise's `CompressedManifestStaticFilesStorage`, which refuses to
  resolve any file until `collectstatic` has run. Tests render pages and never run it, so
  `tests/conftest.py` (`_static_files_without_collectstatic`) switches to plain
  `StaticFilesStorage` and sets `WHITENOISE_AUTOREFRESH=True` (otherwise WhiteNoise warns about the
  missing `STATIC_ROOT`). The switch is in the tests, not in settings, so `check --deploy` sees
  the production settings.
- `assets/static/.gitkeep` keeps the directory in git. `STATICFILES_DIRS` points at it, the built
  stylesheet (`css/tailwind.css`) is git-ignored, and on a fresh checkout Django would warn
  `staticfiles.W004` about the missing directory, which fails `check --deploy --fail-level
  WARNING` (the gate in `scripts/check.sh`).
