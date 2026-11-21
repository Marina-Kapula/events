"""config/env.py: the typed .env loader and accessors (no Django, no DB)."""

from pathlib import Path

import pytest

from config.env import env_bool, env_list, env_str, load_dotenv, parse_dotenv


def test_parse_dotenv_skips_comments_and_blank_lines() -> None:
    text = "\n# a comment\n   # indented comment\n\nA=1\n  B = two  \n"

    assert parse_dotenv(text) == {"A": "1", "B": "two"}


def test_parse_dotenv_quotes_are_stripped_and_taken_literally() -> None:
    text = "\n".join(
        [
            'DOUBLE="with spaces # not a comment"',
            """SINGLE='say "hi" \\n'""",
            'EMPTY_QUOTES=""',
            'COMMENTED="127.0.0.1,localhost"  # a comment after the quote',
        ]
    )

    assert parse_dotenv(text) == {
        "DOUBLE": "with spaces # not a comment",
        "SINGLE": 'say "hi" \\n',
        "EMPTY_QUOTES": "",
        "COMMENTED": "127.0.0.1,localhost",
    }


def test_parse_dotenv_inline_comments_equals_and_export() -> None:
    text = "\n".join(
        [
            "HOSTS=a,b # trailing comment",
            "SECRET=abc#def=ghi",
            "export EXPORTED=yes",
            "EMPTY=",
            "EMPTY_WITH_COMMENT= # c",
            "TAB=v\t# c",
            "LEADING_HASH=#abc",
        ]
    )

    assert parse_dotenv(text) == {
        "HOSTS": "a,b",
        "SECRET": "abc#def=ghi",
        "EXPORTED": "yes",
        "EMPTY": "",
        "EMPTY_WITH_COMMENT": "",
        "TAB": "v",
        "LEADING_HASH": "#abc",
    }


@pytest.mark.parametrize(
    "line",
    [
        "NO_EQUALS_SIGN",
        "=value",
        "LONE='",
        'UNCLOSED="var/db.sqlite3 # comment',
        "DOUBLED='it''s'",
        'GLUED="var"/db.sqlite3',
        'NO_SPACE="var"# comment',
    ],
)
def test_parse_dotenv_rejects_malformed_lines(line: str) -> None:
    with pytest.raises(ValueError, match="line 2"):
        parse_dotenv(f"OK=1\n{line}\n")


def test_load_dotenv_real_environment_wins(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("DJANGO_DEBUG=true\nDJANGO_TIME_ZONE=Europe/Rome\n")
    environ = {"DJANGO_DEBUG": "false"}

    load_dotenv(dotenv, environ)

    assert environ == {"DJANGO_DEBUG": "false", "DJANGO_TIME_ZONE": "Europe/Rome"}


def test_load_dotenv_without_a_file_changes_nothing(tmp_path: Path) -> None:
    environ = {"A": "1"}

    load_dotenv(tmp_path / "missing.env", environ)

    assert environ == {"A": "1"}


def test_env_str() -> None:
    environ = {"SET": " value ", "EMPTY": "", "BLANK": "   "}

    assert env_str("SET", environ=environ) == "value"
    assert env_str("SET", "default", environ=environ) == "value"
    assert env_str("MISSING", environ=environ) is None
    assert env_str("MISSING", "default", environ=environ) == "default"
    assert env_str("EMPTY", "default", environ=environ) == "default"
    assert env_str("BLANK", environ=environ) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("ON", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
    ],
)
def test_env_bool_values(raw: str, expected: bool) -> None:
    assert env_bool("FLAG", default=not expected, environ={"FLAG": raw}) is expected


def test_env_bool_default_and_invalid_value() -> None:
    assert env_bool("FLAG", default=True, environ={}) is True
    assert env_bool("FLAG", default=False, environ={"FLAG": ""}) is False
    with pytest.raises(ValueError, match="FLAG must be a boolean"):
        env_bool("FLAG", default=False, environ={"FLAG": "maybe"})


def test_env_list() -> None:
    environ = {"HOSTS": " a.example , b.example,, ", "EMPTY": ""}

    assert env_list("HOSTS", default=(), environ=environ) == ["a.example", "b.example"]
    assert env_list("EMPTY", default=("x",), environ=environ) == ["x"]
    assert env_list("MISSING", default=("x", "y"), environ=environ) == ["x", "y"]
