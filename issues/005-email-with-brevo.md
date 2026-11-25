# Send email through Brevo

Status: done · Opened: 2026-11-21 · Milestone: M1 · Depends on: — (the production part after 004)

## Why

Almost every feature ends in an email: the verification link when a student registers (008), the
password reset (009), and every notification in SPEC.md §6.6 (approved, rejected, a spot freed
up, an event cancelled). Before the first of them, the app needs three things:

- **A sender address and the site's own address.** An email is read outside the site, so every
  link in it must be a full URL (`https://…/events/5/`). Services send emails without a browser
  request, so they can't ask `request` for the host: the start of every link comes from one
  setting, `SITE_URL` (SPEC.md §2 #35).
- **One small helper** that turns two templates (a subject and a body) into an email, so every
  later email is one function call and looks the same.
- **A real mail service.** A fresh VPS can't deliver mail on its own: providers block or
  distrust it, and the mail lands in spam. Brevo's SMTP relay (SPEC.md §2 #3) delivers it for
  us, and Django's own SMTP backend talks to it: no new dependency.

## What you'll build

- Two settings, `DEFAULT_FROM_EMAIL` and `SITE_URL`, read from environment variables.
- `config/emails.py` with `send_email(...)`, the one function every later email goes through.
- Tests for both.
- A Brevo account with a verified sender, and a test email from your server that really
  arrives in your inbox.

Not in this issue: any real email of the app (the verification email comes in 008, the event
emails in 010–015), and HTML emails (plain text is enough).

## Before you start

Read:
- SPEC.md §2 #3, #28, #35; §6.6 (who gets which email); §9 (the email variables).
- AGENTS.md: Layers (emails go through services) and Django (`transaction.on_commit`).
- `docs/testing/emails.md`: why `mailoutbox` is empty without
  `django_capture_on_commit_callbacks`.
- `docs/deployment/deploy-to-dokku.md`, part 9, the "Email" block.
- `docs/learn/testing-with-pytest-django.md`, if pytest fixtures (`mailoutbox`, `tmp_path`, an
  `autouse` fixture) are new to you.
- [Django: Sending email](https://docs.djangoproject.com/en/6.1/topics/email/), up to
  "Preventing header injection".

Words you'll meet:
- **SMTP**: the protocol mail servers use to hand an email to each other. Django's SMTP backend
  speaks it.
- **SMTP relay**: a service that accepts your app's emails (after a login) and delivers them from
  servers that mailbox providers trust. Brevo is ours.
- **Verified sender**: an address you proved you own (Brevo emails it a code). Brevo only sends
  from verified senders.
- **STARTTLS**: the connection starts plain on port 587 and switches to encryption before the
  login. That is `EMAIL_USE_TLS=true`.
- **Absolute URL**: a link with the scheme and the host (`https://…/verify/…`), as opposed to
  `/verify/…`, which only works inside the site.

## Steps

### 1. Two settings: the sender and the site's address

In `config/settings.py`, below `MAILERS`:

```python
# The sender of every email. In production, an address verified in Brevo.
DEFAULT_FROM_EMAIL: str = env_str("DJANGO_DEFAULT_FROM_EMAIL", "webmaster@localhost")
# The start of every link in emails and the QR code (SPEC.md §2 #35). Emails are sent
# without a browser request, so the app can't guess its own address.
SITE_URL: str = env_str("DJANGO_SITE_URL", "http://127.0.0.1:8000").rstrip("/")
```

- `DEFAULT_FROM_EMAIL` is a Django setting: `send_mail` and Django's own emails (password reset,
  `sendtestemail`) use it when no sender is given.
- `SITE_URL` is ours. `.rstrip("/")` removes a trailing slash, so `https://x.example.com/` and
  `https://x.example.com` both work: templates write `{{ site_url }}{% url 'home' %}`, and
  `{% url %}` already starts with `/`.

Add both to the end of `.env.example`, so a fresh checkout shows them:

```sh
# The sender of every email. In production, an address you verified in Brevo.
DJANGO_DEFAULT_FROM_EMAIL=webmaster@localhost

# The start of every link in emails and the QR code, without a trailing slash.
# In production: https://<your domain>
DJANGO_SITE_URL=http://127.0.0.1:8000
```

Settings are tested in a fresh Python process, so neither pytest nor your `.env` can hide a bug
(the `settings_value` helper is already in `tests/config/test_settings.py`). Add:

```python
def test_site_url_defaults_to_the_dev_server() -> None:
    result = settings_value(
        "s.SITE_URL", DJANGO_DEBUG="true", DJANGO_SECRET_KEY="x", DJANGO_SITE_URL=""
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "http://127.0.0.1:8000"


def test_site_url_loses_its_trailing_slash() -> None:
    result = settings_value(
        "s.SITE_URL",
        DJANGO_DEBUG="true",
        DJANGO_SECRET_KEY="x",
        DJANGO_SITE_URL="https://meetups.example.com/",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "https://meetups.example.com"


def test_default_from_email_comes_from_the_environment() -> None:
    result = settings_value(
        "s.DEFAULT_FROM_EMAIL",
        DJANGO_DEBUG="true",
        DJANGO_SECRET_KEY="x",
        DJANGO_DEFAULT_FROM_EMAIL="meetups@example.com",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "meetups@example.com"
```

- [x] Both settings exist, with the defaults of SPEC.md §9, and are in `.env.example`.
- [x] The three tests pass.

### 2. One function for every email

`config/emails.py`:

```python
from collections.abc import Mapping, Sequence

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


def send_email(
    *, to: Sequence[str], template: str, context: Mapping[str, object] | None = None
) -> None:
    context = {**(context or {}), "site_url": settings.SITE_URL}
    subject = render_to_string(f"{template}_subject.txt", context)
    send_mail(
        # A header must be one line: join the lines and drop extra spaces.
        subject=" ".join(subject.split()),
        message=render_to_string(f"{template}.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=list(to),
    )
```

What it does:
- `template="events/emails/event_approved"` renders two files:
  `events/templates/events/emails/event_approved_subject.txt` and `…/event_approved.txt`
  (SPEC.md §6.6: plain text, a subject line and a link).
- It adds `site_url` to the context, so every template can build links.
- The subject is squeezed into one line. Every template file ends with a newline, and Django
  refuses a header with a newline in it (a `ValueError`), to stop
  [header injection](https://docs.djangoproject.com/en/6.1/topics/email/#preventing-header-injection).
- Keyword-only arguments (the `*`), like the services (AGENTS.md).

This is how the later issues will use it, from a service, after the transaction commits
(AGENTS.md, Django). You don't write this now:

```python
transaction.on_commit(
    lambda: send_email(
        to=[event.organizer.email],
        template="events/emails/event_approved",
        context={"event": event},
    )
)
```

with these two templates. `events/templates/events/emails/event_approved_subject.txt`:

```django
{% autoescape off %}Your event "{{ event.title }}" is approved{% endautoescape %}
```

and `events/templates/events/emails/event_approved.txt`:

```django
{% autoescape off %}Hi {{ event.organizer.full_name }},

AMFI approved your event "{{ event.title }}". Here it is:
{{ site_url }}{% url 'event_detail' event.pk %}
{% endautoescape %}
```

`{% autoescape off %}` matters: Django escapes HTML in every template, `.txt` or not, so without
it "D'Arcy & friends" arrives as `D&#x27;Arcy &amp; friends`. Django's own password reset email
does the same.

- [x] `config/emails.py` as above.

### 3. Test it

There is no real email yet, so the test writes two small templates into a temporary folder and
points Django at it. `mailoutbox` (pytest-django) collects what was sent; no `on_commit` here,
so it fills without `django_capture_on_commit_callbacks`.

`tests/config/test_emails.py`:

```python
from collections.abc import Iterator
from pathlib import Path

import pytest
from django.conf import settings
from django.core.mail import EmailMessage
from django.test import override_settings

from config.emails import send_email


@pytest.fixture(autouse=True)
def _hello_templates(tmp_path: Path) -> Iterator[None]:
    # Two made-up templates in a temporary folder: no real email exists yet.
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
    # Two lines and a final newline in the template, one line in the email.
    assert email.subject == "Hello Student 1"
    assert email.body.startswith("Hi Student 1!")


def test_links_start_with_the_site_url(mailoutbox: list[EmailMessage]) -> None:
    send_email(to=["student1@example.com"], template="tests/emails/hello")

    assert "https://meetups.example.com/my-events/" in mailoutbox[0].body
```

- [x] Both tests pass, and `scripts/check.sh` passes.

### 4. Try it on your laptop

`.env.example` sets the file-based backend: each email becomes a file in `var/mail/`, and
nothing leaves your laptop. Django's `sendtestemail` command sends a test email:

```sh
uv run python manage.py sendtestemail student1@example.com
ls var/mail/                      # one new file; open it
```

- [x] The file shows `From: webmaster@localhost` (or your `.env` value) and the test text.

### 5. Open a Brevo account

1. Sign up at [brevo.com](https://www.brevo.com/). The free plan sends 300 emails a day, plenty
   for this app.
2. **Verify a sender.** In the settings menu, open the senders page and add a sender (name "AMFI
   Meetups", and an email address you can read). Brevo emails a 6-digit code to that address;
   enter it. Menu names change from time to time; Brevo's help article
   [Create a new sender](https://help.brevo.com/hc/en-us/articles/208836149) has the current
   ones.
3. **Get the SMTP login and key.** Open **SMTP & API**, tab **SMTP**. Note the **SMTP server**
   (`smtp-relay.brevo.com`), the **port** (587) and the **login** (it may not be your account
   email). Click **Generate a new SMTP key** and copy it now: Brevo shows it only once.

Keep the key in your password manager, never in git, an issue, a chat or `.env.example`.

- [x] A verified sender, an SMTP login and an SMTP key.

### 6. Send a real email from your server (after 004)

This issue has no migration, so you can deploy the branch to your own server to test it before
the merge, as a team would on a "staging" server. Bring the latest `main` into the branch first
(`git merge main`), so the server doesn't go back to older code:

```sh
git push dokku 005-email-with-brevo:master   # laptop; after the merge, deploy main again
```

Then set the email variables: follow the "Email" block of the deploy guide, part 9, and add
`DJANGO_DEFAULT_FROM_EMAIL=<SENDER_EMAIL>` to the same `config:set` command. `<SENDER_EMAIL>` is
the address you verified in step 5. With a display name it looks like
`DJANGO_DEFAULT_FROM_EMAIL='AMFI Meetups <you@example.com>'`: there the angle brackets are real,
and the single quotes keep the shell from reading them.

Send a test email to yourself:

```sh
ssh -t <SSH_USER>@<VPS_IP> sudo dokku run <APP> python manage.py sendtestemail <YOUR_EMAIL>   # laptop
```

It should arrive within a minute. If not, look in the spam folder, and in Brevo's logs of
transactional emails.

While you are in the guide: its "Email" block doesn't set `DJANGO_DEFAULT_FROM_EMAIL` yet, and
still says "invitations" (from the old plan; it's verification links now). Fix both, so the next
person gets it right.

- [x] The test email from the server arrives in your inbox.
- [x] `docs/deployment/deploy-to-dokku.md` part 9 sets `DJANGO_DEFAULT_FROM_EMAIL`.

## Done when

- [x] `DEFAULT_FROM_EMAIL` and `SITE_URL` come from `DJANGO_DEFAULT_FROM_EMAIL` and
      `DJANGO_SITE_URL`, are in `.env.example`, and are tested (step 1).
- [x] `send_email` renders the subject on one line and the body with `site_url` (tests in
      `tests/config/test_emails.py`).
- [x] `sendtestemail` writes a file in `var/mail/` on your laptop, and delivers a real email from
      your server through Brevo.
- [x] The SMTP key is only in Brevo, your password manager and `dokku config`.
- [x] The deploy guide sets the sender.
- [x] `scripts/check.sh` passes.
- [x] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 005-email-with-brevo
```

Suggested commits (each one passes `scripts/check.sh`):
1. `Add the DEFAULT_FROM_EMAIL and SITE_URL settings`
2. `Add send_email for emails from two templates`
3. `Set the email sender in the deploy guide`
4. `Close 005 in the issue`

Open a pull request titled "Send email through Brevo". In the description, say that the test
email from your server arrived (a screenshot of it in your inbox is fine; hide your address if
you like). Never paste `dokku config:show` output: it prints the SMTP key. `docs/workflow/git.md`
has every step.

## Watch out

- **`535 Authentication failed`**: the login or the key is wrong. The login is Brevo's SMTP login
  (not the server name, and maybe not your account email), and the key is an **SMTP key**, not an
  API key.
- **`525 5.7.1 Unauthorized IP address`**: Brevo can block logins from addresses it doesn't know.
  Add `<VPS_IP>` under Brevo's settings, **Security → Authorized IPs**.
- **The sender isn't verified**: Brevo refuses or drops the email. `DJANGO_DEFAULT_FROM_EMAIL` must
  be exactly the verified address.
- **A free sender address** (Gmail, Outlook, …): Brevo may replace its domain with one of its own
  so that receivers' spam checks pass. The email still arrives. To keep your own address you need
  your own domain, authenticated in Brevo (DNS records).
- **Every email template starts with `{% autoescape off %}`**, the subject too (step 2).
- **Links come from `site_url`, never from `request`** (`request.build_absolute_uri()`): services
  have no request, and behind nginx the request may not know the public address anyway.
- **Emails in tests**: services send in `transaction.on_commit`, so wrap the call in
  `django_capture_on_commit_callbacks(execute=True)` (`docs/testing/emails.md`).
- **Don't put real SMTP values in `.env` and forget them there.** If you try real sending from your
  laptop, remove them afterwards and go back to the file backend.
- **Sending happens during the request.** With no task queue (SPEC.md §3), a slow SMTP server
  makes the page slow; the SMTP `timeout` of 10 s in the settings stops it from hanging forever.

## Further reading

- [Django: Sending email](https://docs.djangoproject.com/en/6.1/topics/email/) (`send_mail`,
  email backends) and the settings
  [`DEFAULT_FROM_EMAIL`](https://docs.djangoproject.com/en/6.1/ref/settings/#default-from-email)
  and [`MAILERS`](https://docs.djangoproject.com/en/6.1/ref/settings/#mailers).
- [Django: `render_to_string`](https://docs.djangoproject.com/en/6.1/topics/templates/#django.template.loader.render_to_string)
  and the [`autoescape` tag](https://docs.djangoproject.com/en/6.1/ref/templates/builtins/#autoescape).
- [Django: `sendtestemail`](https://docs.djangoproject.com/en/6.1/ref/django-admin/#sendtestemail).
- [Django: Performing actions after commit](https://docs.djangoproject.com/en/6.1/topics/db/transactions/#performing-actions-after-commit).
- Brevo: [SMTP relay](https://developers.brevo.com/docs/smtp-integration),
  [Create a new sender](https://help.brevo.com/hc/en-us/articles/208836149),
  [Authorized IPs](https://help.brevo.com/hc/en-us/articles/5740111683858),
  [Troubleshooting SMTP](https://help.brevo.com/hc/en-us/articles/115000188150).
- [mail-tester.com](https://www.mail-tester.com/): send it a test email and see how spammy it
  looks.
- [Django: Email services in tests](https://docs.djangoproject.com/en/6.1/topics/testing/tools/#email-services):
  why tests never send real email, and where `mailoutbox` gets its messages.
- [Gmail: Email sender guidelines](https://support.google.com/mail/answer/81126): what a big mailbox
  provider expects from a sender (SPF or DKIM, reverse DNS, TLS). A fresh VPS has none of it;
  Brevo does.
- [Wikipedia: SMTP transport example](https://en.wikipedia.org/wiki/Simple_Mail_Transfer_Protocol#SMTP_transport_example):
  what an SMTP client and server say to each other, line by line.
