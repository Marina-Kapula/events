"""A tiny typed `.env` loader and accessors for settings.

`load_dotenv()` copies `KEY=value` lines from a `.env` file into the environment without
overriding variables that are already set, so real environment variables always win.
The accessors read the environment and treat an empty value as unset.

Supported `.env` syntax: blank lines, `#` comment lines, an optional `export ` prefix,
values in matching single or double quotes (taken literally, up to the first matching
quote), and inline comments: outside quotes, a `#` preceded by whitespace starts one.
Anything else after a closing quote, or a missing closing quote, is an error rather than
a silently wrong value.
"""

import os
import re
from collections.abc import Iterable, Mapping, MutableMapping
from pathlib import Path
from typing import overload

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})
_QUOTES = frozenset({'"', "'"})
_COMMENT = re.compile(r"\s+#")


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse the contents of a `.env` file. Raises `ValueError` for a malformed line."""
    values: dict[str, str] = {}
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key:
            msg = f".env line {number}: expected KEY=value, got {raw_line!r}"
            raise ValueError(msg)
        values[key] = _parse_value(value, f".env line {number} ({key})")
    return values


def _parse_value(raw: str, where: str) -> str:
    """Parse the text after `=`. It is not stripped yet: in `KEY= # c` the `#` must
    still follow whitespace to start a comment."""
    value = raw.strip()
    quote = value[:1]
    if quote in _QUOTES:
        end = value.find(quote, 1)
        if end == -1:
            msg = f"{where}: missing closing {quote}"
            raise ValueError(msg)
        rest = value[end + 1 :]
        if rest and not _COMMENT.match(rest):
            msg = f"{where}: only a ' #' comment may follow the closing {quote}"
            raise ValueError(msg)
        return value[1:end]
    if comment := _COMMENT.search(raw):
        raw = raw[: comment.start()]
    return raw.strip()


def load_dotenv(path: Path, environ: MutableMapping[str, str] = os.environ) -> None:
    """Load `path` into `environ`, keeping variables already set. No file is fine."""
    if not path.is_file():
        return
    for key, value in parse_dotenv(path.read_text(encoding="utf-8")).items():
        environ.setdefault(key, value)


def _lookup(name: str, environ: Mapping[str, str]) -> str | None:
    value = environ.get(name, "").strip()
    return value or None


@overload
def env_str(name: str, default: str, *, environ: Mapping[str, str] = ...) -> str: ...
@overload
def env_str(
    name: str, default: None = None, *, environ: Mapping[str, str] = ...
) -> str | None: ...
def env_str(
    name: str, default: str | None = None, *, environ: Mapping[str, str] = os.environ
) -> str | None:
    """Return the variable, or `default` when it is unset or empty."""
    value = _lookup(name, environ)
    return default if value is None else value


def env_bool(
    name: str, *, default: bool, environ: Mapping[str, str] = os.environ
) -> bool:
    """Return the variable as a bool (true/false, yes/no, on/off, 1/0; any case)."""
    value = _lookup(name, environ)
    if value is None:
        return default
    lowered = value.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    msg = f"{name} must be a boolean (true/false, yes/no, on/off, 1/0), got {value!r}"
    raise ValueError(msg)


def env_list(
    name: str, *, default: Iterable[str], environ: Mapping[str, str] = os.environ
) -> list[str]:
    """Return a comma-separated variable as a list of stripped, non-empty items."""
    value = _lookup(name, environ)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]
