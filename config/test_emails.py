from collections.abc import Iterator
from pathlib import Path

import pytest
from django.conf import settings
from django.core.mail import EmailMessage
from django.test import override_settings

from config.emails import send_email


@pytest.fixture(autouse=True)
def _hello_templates(tmp_path: Path) -> Iterator[None]:
    folder = tmp_path / "tests" / "emails"
    folder.mkdir(parents=True)
    (folder / "hello_subject.txt").write_text("Hello\n{{ name }}\n")
    (folder / "hello.txt").write_text("Hi {{ name }}!\n{{ site_url }}/my-events/\n")
    with override_settings(
        TEMPLATES=[{**settings.TEMPLATES[0], "DIRS": [tmp_path]}],
        SITE_URL="https://meetups.example.com",
        DEFAULT_FROM_EMAIL="AMFI Meetups <meetups@example.com>",
    ):
        yield


def test_send_email_renders_both_templates(mailoutbox: list[EmailMessage]) -> None:
    send_email(
        to=["student1@example.com"],
        template="tests/emails/hello",
        context={"name": "Student 1"},
    )

    assert len(mailoutbox) == 1
    email = mailoutbox[0]
    assert email.to == ["student1@example.com"]
    assert email.from_email == "AMFI Meetups <meetups@example.com>"
    assert email.subject == "Hello Student 1"
    assert email.body.startswith("Hi Student 1!")


def test_links_start_with_the_site_url(mailoutbox: list[EmailMessage]) -> None:
    send_email(to=["student1@example.com"], template="tests/emails/hello")

    assert "https://meetups.example.com/my-events/" in mailoutbox[0].body
    