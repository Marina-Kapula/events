# AMFI Meetups — spec

Status: agreed in a planning interview on 2026-11-20/21, starting from the students' plan in
`docs/app-plan.md` and the wireframes next to it. Where they differ, this file wins; §2 says what
changed and why, §13 what was dropped. Rule of the interview: when in doubt, the option that is
easiest to implement. The stack, conventions and quality gate are copied from the teacher's
projects erasmops and erascraper.

## 1. Goal

A Meetup-like web app for Erasmus students hosted by AMFI International (Avezzano). Students
create events in any city (meetups, pizza nights, trips) and join other students' events; an
AMFI admin reviews every event so there are no fakes. Language: English.

It is built by students learning full-stack development, with AI agents allowed: a simple,
idiomatic Django app (server-rendered pages, plain forms, full page loads, little JavaScript).

## 2. Decisions

| # | Decision | Why |
|---|---|---|
| 1 | **Mixed layering.** Reads are custom `QuerySet` methods; plain one-model create/edit uses `ModelForm.save()`; state changes, rules, multi-model writes and emails go through `services.py` functions. Function-based views. | Idiomatic Django a student can explain, with one tested home for the rules where the bugs will be (event states, spots, waiting list). Not chosen: erasmops' strict services/selectors (ceremony for simple forms); plain fat models (rules scattered over `save()` and views). |
| 2 | **No HTMX.** Full page loads, Post/Redirect/Get, `django.contrib.messages`; markup reused with Django's template partials (`{% partialdef %}`). Django's own `LoginRequiredMiddleware`. | Fewer moving parts for students; template partials are enough for reuse. |
| 3 | **Email through Brevo's SMTP relay** (`smtp-relay.brevo.com`, port 587, STARTTLS), using Django's SMTP backend and the `EMAIL_*` variables (§9). | No new dependency. Not chosen: django-anymail's Brevo API backend (a dependency for the same result). |
| 4 | **Each student deploys their own copy** on their own OVHcloud VPS with Dokku, following `docs/deployment/`. | Learning by doing; the teacher's server and notes stay private. |
| 5 | **Registration through an expiring QR code, at the welcome meeting.** At the end of the presentation on the Erasmus rules, the admin generates a QR code that expires after a set time. Attendees scan it and register themselves with their email and details. The email address is confirmed through a verification link before the account works. Replaces the emailed invitations of `docs/app-plan.md` #3–4. | Everyone is in the room with a phone: they sign up on the spot, and the admin types nobody in. The expiry and the verified email keep a forwarded photo of the QR code from being much use. |
| 6 | **Custom user model, email as the login.** `accounts.User` with `USERNAME_FIELD = "email"` and no username, from the first migration. | Students register with their email. Django recommends a custom user model from the start; switching later means rebuilding the migrations. |
| 7 | **A registration window is a database row.** It stores who opened it, when it expires, and whether it was closed early. The QR code holds `/register/<random code>/`. The window is checked when the page opens and again when the form is sent. Each user stores the window they came through. | The admin can close a window early and see who registered at which meeting. Someone who missed the meeting gets a new window, opened in the office. |
| 8 | **The QR image is drawn on the server with `segno`, as inline SVG** (§3). | Pure Python with no dependencies of its own; no JavaScript and no image files. |
| 9 | **The account is inactive until the email link is clicked.** The link carries a token from Django's token generator, as in password reset. The login page offers to resend it. | Stops sign-ups with someone else's address or a typo; no new dependency. |
| 10 | **Registration takes the whole profile in one form**: full name, email, password, photo, nationality, age, gender. All fields are required. On a phone the photo field opens the front camera (`capture="user"`). | Nobody has half a profile, so the "complete your profile first" check of `docs/app-plan.md` #8 isn't needed. Not chosen: account first and profile later (an extra state and a check on every join and create). |
| 11 | **The admin picks how long a window stays open**: 15 min, 30 min (preselected), 1 h or 2 h. Its admin page shows the QR code, when it expires and who has registered; "Close now" is an admin action (§8). The window must still be open when the form is sent; otherwise the student sees "Registration closed, ask the AMFI staff". | The presenter knows how long the meeting runs; closing early cuts off a forwarded QR code. Not chosen: one fixed duration; a personal grace period after scanning (a signed timestamp and one more rule, rarely needed with 30 minutes). |
| 12 | **Profile fields**: full name (one field), age (a number, 16–99), nationality (`django-countries`' `CountryField`), gender (Female / Male / Other). All required for students. | As `docs/app-plan.md` #6. One name field fits international names. Age rather than a birth date: less sensitive, and students can edit it. django-countries is the standard full country list (§3). |
| 13 | **Photos are served by Django to logged-in users only.** They are stored in `var/media/` (inside the storage mount), returned by a login-required view with `FileResponse`, shrunk on upload to at most 1024 px and re-saved as JPEG with Pillow, which drops EXIF data and the GPS location. Uploads over 10 MB are refused with a form error. Same for profile and event photos. | Students' faces stay behind the login (GDPR), and there's no extra server setup. Not chosen: nginx serving `/media/` (public to anyone with the URL); object storage (too much for this size). |
| 14 | **Everything requires a login.** The only public pages are login, password reset, registration (with an open window) and email verification. Events, profiles and photos are for logged-in users only. | A closed community of one host organisation; personal data never reaches search engines. Django's `LoginRequiredMiddleware` already does it; public views are marked `@login_not_required`. |
| 15 | **Admins are staff accounts (`is_staff`), and all admin work happens in Django's admin**: registration windows (the add form asks for the duration; the window's page shows the QR code, when it expires and who registered; closing early is an action), reviews ("Approve" and "Reject" buttons on the event's page, a reason required to reject, both through a service so notifications go out), students (soft delete is an action that calls a service) and any event. No comparison of old and new values. Admins have no student profile; an event they create is approved at once, and they are its organizer. | As simple as possible: the custom UI is only for students, as organizers and attendees. Students learn to configure the admin (`list_display`, `search_fields`, actions, readonly fields). Not chosen: app pages for staff (more templates for the same work). |
| 16 | **Editing an approved event keeps the approved version public until the admin approves the changes; sign-ups stay open meanwhile**, and visitors see that changes are pending. Approve: the public version is updated and everyone going is notified (`docs/app-plan.md` #34). Reject: the event stays as it was, and the organizer gets the reason (#17). | Sign-ups don't stall while AMFI reviews. Replaces #16's "new sign-ups are closed". |
| 17 | **Pending changes are a second model.** The editable fields live in an abstract base model `EventFields`; `Event` and `EventChange` (one-to-one with its event, at most one per event) inherit them. Editing an approved event creates or updates its `EventChange`; events that are pending or rejected are edited directly. In the admin the change is an inline on the event's page. Approve copies the fields over and deletes the change; reject deletes it. Max people can't go below the number already going: checked by the form, and again on approval. | Typed fields and no JSON blob. The admin sees proposed and current values on one page, with no comparison code. |
| 18 | **Pending changes show as a warning only**: a "Changes pending" badge on the event's card and one line on its page. The proposed values are not shown. | Easiest; people going are emailed once the changes are approved. Not chosen: showing the proposed version. |
| 19 | **daisyUI 5 for the UI**, through django-tailwind-cli's `TAILWIND_CLI_USE_DAISY_UI` (the tailwind-cli-extra binary: Tailwind and daisyUI in one file, still no Node). Themes `light` (default) and `dark` (when the device prefers it). | Component classes (`btn`, `card`, `navbar`, `badge`, `dock`) are the easiest way for students to build tidy pages; the students' plan already picked daisyUI. |
| 20 | **No drafts.** Saving a new event sends it to review (`pending`). A rejected event shows its reason to the organizer, who edits it (back to `pending`) or cancels it. | One state and one button fewer. Replaces `docs/app-plan.md` #12, and #15's "back to draft". |
| 21 | **Only approved events are public.** A pending or rejected event is seen only by its organizer (and in the admin). | The list has one kind of card. Replaces #13 (events in review shown to everyone as "not approved"). |
| 22 | **Event types are a fixed list in code** (`TextChoices`): Meetup, Food, Trip, Sport, Party, Culture, Other. | No model, admin page or data migration; a new type is one line of code. Replaces #9's type written by the organizer and #10/#31's admin-managed list. |
| 23 | **"We will speak" is free text**, default "English". | No list to maintain. |
| 24 | **The organizer takes one spot but has no participation row**: spots taken = 1 + people going. The organizer can't join or leave their own event; they cancel it instead. | No special cases in join and leave. As #11. |
| 25 | **A waiting list without the organizer.** When the event is full, "Join" becomes "Join the waiting list". When a spot frees up (someone going leaves, or approved changes raise max people), the first person waiting gets it automatically and is emailed. Anyone can leave the waiting list. | Nobody has to accept anyone. As #25 and #35; replaces #24's organizer accepting or declining. |
| 26 | **Leaving deletes the participation**, allowed until the event starts. The organizer is emailed when someone going leaves. | No "left" state to filter out. As #23 and #33. |
| 27 | **Cancelling an event** (the organizer before it starts, the admin any time) sets it `cancelled` and emails everyone going or waiting. It can't be undone. Participations are kept, so the event stays in everyone's "My events". | As #18 and #34. |
| 28 | **Notifications are emails only** (§6.6), sent from services in `transaction.on_commit`. | No notification model, page or unread badge. Replaces #32's "and to the site". |
| 29 | **The event list** shows approved events that are not cancelled and haven't started, soonest first, without pagination. Filters in one GET form: keyword (title or description contains), city (contains), date (events on that day), type, size (max people: up to 5, 6–10, more than 10). A plain `forms.Form` and QuerySet methods. | As #20–21. Not chosen: django-filter (a dependency for five filters). |
| 30 | **"My events" is one page with two lists**: created by me (every own event, with a status badge and the rejection reason) and joined by me (going and waiting; upcoming first, then past and cancelled). | As #26–27, without tabs. |
| 31 | **Every logged-in user can see every active student's profile**; students edit their own (the registration fields except email and password). Password change and reset are Django's auth views. | As #5 and #7. |
| 32 | **Soft delete is an admin action** (§8): the account becomes inactive and gets a `deleted_at`, the student's upcoming events are cancelled (with emails), and their participations are deleted (the waiting lists move up). Their profile is gone and they can't log in. | As #28. A real erasure, if someone asks for it, is the admin's Delete button. |
| 33 | **Edits in the Django admin send no emails**; only Approve and Reject do. Deleting an event in the admin is a hard delete without emails: to tell people, cancel it instead. | The admin is a correction tool; the rules live in the student pages and the review buttons. |
| 34 | **Events have a start and no end**, in one time zone (Europe/Rome). An event is past once it has started. | As #9 and #21. |

## 3. Stack

As erasmops (its §3), plus the email settings from erascraper.

| Package | Version | Role |
|---|---|---|
| Python | 3.14 | runtime (`.python-version`); uv installs it |
| uv | — | env + deps; everything runs through `uv run` |
| Django | 6.1.x | web framework, auth, admin, ORM (SQLite), email |
| django-stubs-ext | 6.1.x | runtime `monkeypatch()` so `admin.ModelAdmin[Event]` etc. can be subscripted |
| django-tailwind-cli | 4.8.x | Tailwind v4 + daisyUI 5 through the standalone tailwind-cli-extra binary (no Node); `manage.py tailwind runserver` for dev |
| gunicorn | 26.x | WSGI server in the Docker image |
| whitenoise | 6.x | serves static files when `DEBUG` is off |
| Pillow | current | `ImageField`, shrinking and re-saving uploaded photos (§2 #13) |
| django-countries | current | `CountryField` for nationality (§2 #12) |
| segno | current | QR code of a registration window, as inline SVG (§2 #8); added by its issue |
| **dev:** pyrefly | 1.3.x | type checker, strict preset |
| **dev:** django-stubs | 6.1.x | stubs pyrefly uses to model Django |
| **dev:** ruff, pytest, pytest-django | current | lint/format, tests |

No other dependencies without a decision recorded here. In particular: no Node, no HTMX or JS
framework (§2 #2), no Celery/Redis, no django-environ (settings use a small typed env helper), no pre-commit
framework.

## 4. Repository layout

```
config/      settings, env helper, urls, the photo view (§6.8)
accounts/    User, RegistrationWindow; registration, email verification, profiles; their admin
events/      Event, EventChange, Participation; list, event page, create, edit, join, leave,
             cancel, my events; their admin
             each app: models, admin, forms, views, urls, services; emails in
             templates/<app>/emails/
templates/   base.html (navbar, dock, messages), registration/ (Django's auth templates)
assets/      css/source.css (Tailwind + daisyUI), static/
tests/       config/, accounts/, events/ (each with __init__.py); conftest.py with make_* fixtures
docs/        notes for developers and agents; docs/deployment/ is the students' deploy guide
issues/      _kanban.md and NNN-slug.md
scripts/     check.sh, pull-backup.sh, server/nginx-login-limit.sh
```

`events` may import `accounts`; `accounts` never imports `events`, except the soft-delete service
(§6.7), which calls the events services.

## 5. Data model

**accounts.User** (`AbstractUser` without `username`, `first_name`, `last_name`; a manager with
`create_user` and `create_superuser` by email; `USERNAME_FIELD = "email"`)

| Field | Type | Notes |
|---|---|---|
| email | `EmailField`, unique | the login |
| full_name | `CharField(100)` | |
| photo | `ImageField` | `photos/users/`; empty for staff |
| nationality | `CountryField` | empty for staff |
| age | `PositiveSmallIntegerField`, null | 16–99 validators; null for staff |
| gender | `CharField` with `TextChoices` | female, male, other; empty for staff |
| registration_window | FK `RegistrationWindow`, null, `PROTECT` | the window the student came through |
| deleted_at | `DateTimeField`, null | soft delete (§6.7) |

A `CheckConstraint`: staff, or every profile field filled in. `is_active` is false until the email
is verified, and again after a soft delete.

**accounts.RegistrationWindow**: `code` (random, unique, `secrets.token_urlsafe(16)`),
`opened_by` (FK User), `opened_at`, `expires_at`, `closed_at` (null). Open while
`closed_at` is null and `now < expires_at`.

**events.EventFields** (abstract): `title` (`CharField(80)`), `description` (`TextField`), `photo`
(`ImageField`, `photos/events/`), `city` (`CharField(60)`), `place` (`CharField(120)`),
`starts_at` (`DateTimeField`), `type` (`TextChoices`, §2 #22), `max_people`
(`PositiveSmallIntegerField`, 2–100, the organizer included), `language` (`CharField(40)`,
default "English").

**events.Event** (`EventFields`): `organizer` (FK User, `PROTECT`), `status` (`pending`,
`approved`, `rejected`, `cancelled`), `review_note` (`TextField`, blank: the last rejection
reason), `created_at`, `updated_at`.

**events.EventChange** (`EventFields`): `event` (one-to-one `Event`, `CASCADE`), `created_at`.

**events.Participation**: `event` (FK, `CASCADE`), `user` (FK, `CASCADE`), `status` (`going`,
`waiting`), `created_at`. Unique `(event, user)`. The waiting list is ordered by `created_at`.

## 6. Domain rules

### 6.1 Registration (§2 #5–#11)

1. The admin adds a registration window in the admin, choosing 15 min, 30 min, 1 h or 2 h.
2. Its admin page shows the QR code of `https://<host>/register/<code>/`, when it expires and who
   registered through it.
3. `/register/<code>/` (public) shows the form while the window is open; otherwise "Registration
   closed, ask the AMFI staff". An unknown code is a 404.
4. Sending the form checks the window again, creates an inactive user and emails a verification
   link. The page says "Check your email".
5. `/verify/<uidb64>/<token>/` (public) activates the account and logs the student in. A used
   or expired link says so and offers to resend.
6. "Resend the verification email" (public, linked from the login page) asks for the email and
   always answers the same, so it doesn't reveal who is registered. It sends a link only to an
   inactive, not soft-deleted user.
7. An email that is already registered is a form error that points to login and password reset.

### 6.2 Event states

| From | Action | Who | To |
|---|---|---|---|
| — | create (student page) | a student | `pending`; staff are emailed |
| — | create (admin) | staff | `approved`; the admin is the organizer |
| `pending` | approve | staff | `approved`; organizer emailed |
| `pending` | reject with a reason | staff | `rejected`; organizer emailed with the reason |
| `pending`, `rejected` | edit | organizer | `pending` (edited in place); staff emailed |
| `approved` | edit | organizer | stays `approved`; the edit goes to its `EventChange` (§6.5) |
| `pending`, `approved`, `rejected` | cancel | organizer before it starts; staff any time | `cancelled` |

### 6.3 Visibility

- The list (§2 #29) and anyone's event pages: `approved` events, and `cancelled` ones (shown as
  cancelled, without buttons).
- The organizer also sees their own `pending` and `rejected` events, with the rejection reason.
- Everything else is a 404.

### 6.4 Joining, leaving, the waiting list

- Join: the event is `approved` and hasn't started; the user isn't its organizer and isn't on it
  yet. If `1 + going < max_people` they are `going`, otherwise `waiting`. All in one transaction
  (SQLite `IMMEDIATE`), so two people can't take the last spot.
- Leave (going or waiting): before the start; the row is deleted. If they were going, the
  organizer is emailed and the waiting list moves up.
- Moving up: while there is a free spot and someone waiting, the oldest waiting becomes `going`
  and is emailed. Runs after a leave, after approved changes, and after a soft delete.
- The event page shows "Going (n of max)": the organizer first, then everyone going, with photo,
  name, age and nationality (each a link to the profile), and "Waiting: n".

### 6.5 Editing

- `pending` or `rejected`: the form edits the event itself; it goes back to `pending`.
- `approved`: the form saves into the event's `EventChange` (created, or replaced if one exists).
  The public version doesn't change, sign-ups stay open, and the card and page show "Changes
  pending" (§2 #16–#18).
- `max_people` can't be lower than 1 + going, and `starts_at` must be in the future: checked by
  the form, and both again when the admin approves changes.
- Approve changes: copy the fields to the event, delete the change, move the waiting list up,
  email everyone going. Reject: delete the change, keep the reason in `review_note`, email the
  organizer.

### 6.6 Emails

Plain-text templates in `templates/<app>/emails/`, a subject line and a link to the page. Sent
from the services in `transaction.on_commit`.

| When | To |
|---|---|
| registration; resend | the student: the verification link |
| a student creates or edits a pending/rejected event; a student edits an approved event | every active staff user: link to the event's admin page |
| event approved; event rejected (with the reason) | the organizer |
| changes approved | everyone going |
| changes rejected (with the reason) | the organizer |
| someone going leaves | the organizer |
| a waiting person gets a spot | that person |
| event cancelled (by the organizer, staff, or a soft delete) | everyone going or waiting |
| password reset | the student (Django's own email) |

### 6.7 Soft delete (admin action)

In one transaction: `is_active = False`, `deleted_at = now`; their upcoming events cancelled
(§6.2, with emails); their participations deleted, and those waiting lists moved up. Past events
stay as they were. Their profile page is a 404 and they no longer appear in going lists.

### 6.8 Photos (§2 #13)

- A form helper checks the size (10 MB at most) and that Pillow can open the file, then shrinks
  it to at most 1024 px on the long side and saves it as JPEG (quality 85), which drops the EXIF
  data.
- `MEDIA_ROOT = var/media`, `MEDIA_URL = "media/"`. `config/views.py` serves `/media/<path>`
  with `FileResponse` after `safe_join` on `MEDIA_ROOT`; `LoginRequiredMiddleware` keeps it
  for logged-in users.
- Old files are not cleaned up when a photo is replaced.

## 7. Screens

All pages extend `base.html`: daisyUI `navbar` on wide screens and a bottom `dock` on phones
(Events, My events, Create, Profile), as in `docs/wireframe-desktop.svg` and
`docs/wireframe-mobile.svg`. Messages show at the top.

| URL | Who | Page |
|---|---|---|
| `/` | logged in | the event list: filter form, event cards (§2 #29); name `home` |
| `/events/new/` | students | the event form |
| `/events/<id>/` | §6.3 | the event page: photo, details, organizer, going list, buttons by state |
| `/events/<id>/edit/` | organizer | the event form, with the status explained above it |
| `/events/<id>/join/`, `/leave/`, `/cancel/` | §6.4, §6.2 | POST only; redirect to the event page with a message |
| `/my-events/` | students | created by me, joined by me (§2 #30) |
| `/students/<id>/` | logged in | a student's profile |
| `/profile/` | students | edit own profile; links to password change |
| `/register/<code>/`, `/verify/<uidb64>/<token>/`, `/accounts/resend-verification/` | public | §6.1 |
| `/accounts/login/`, `/accounts/logout/`, `/accounts/password_change/`, `/accounts/password_reset/…` | Django's auth views | daisyUI templates in `templates/registration/` |
| `/media/<path>` | logged in | photos (§6.8) |

- The event card is one `{% partialdef event_card %}` in the list template, included from "My
  events" (`{% include "events/event_list.html#event_card" %}`). It shows the photo, type,
  language, date, title, city and place, spots ("5 / 8 spots"), and a badge for the status or
  "Changes pending".
- Buttons on the event page, by state: Join; Join the waiting list; Leave; Leave the waiting
  list; for the organizer, Edit and Cancel event (Cancel asks for confirmation in a `<dialog>`).

## 8. Admin

- `/admin/` is for staff. `admin.site.site_header = "AMFI Meetups"`; `auth.Group` unregistered.
- **Users**: list email, full name, nationality, registration window, active, staff; search email
  and name; filter active, staff, window. Action "Soft delete" calls the service (§6.7). Staff
  accounts come from `createsuperuser` or the admin's add form.
- **Registration windows**: the add form asks only for the duration; `opened_by` is the admin.
  The change page shows the QR code (a readonly field rendering `segno`'s SVG, about 400 px wide
  for the projector), the URL, `expires_at`, open or closed, and the students who registered
  (readonly). Action "Close now" sets `closed_at`.
- **Events**: list title, organizer, start, status, "changes pending"; filter status and type;
  search title and city. The change page shows the `EventChange` as a readonly inline and the
  participations as a readonly inline. "Approve" and "Reject" buttons (an override of the
  `submit_buttons_bottom` block, handled in `response_change`) call the services; Reject requires
  `review_note`. A new event added in the admin is `approved` with the admin as organizer.


## 9. Settings and configuration

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_DEBUG` | `false` | `.env.example` sets `true` for local dev |
| `DJANGO_SECRET_KEY` | none | required when `DEBUG` is false |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | |
| `DJANGO_HTTPS` | `false` | `true` behind an HTTPS proxy (proxy SSL header, secure cookies, HSTS) |
| `DJANGO_DB_PATH` | `var/db.sqlite3` | relative to `BASE_DIR`; the directory is created |
| `DJANGO_TIME_ZONE` | `Europe/Rome` | `USE_TZ = True` |
| `EMAIL_BACKEND` | SMTP | `.env.example` sets the file-based backend (`var/mail/`, nothing sent) |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL` | `localhost`, `587`, empty, empty, `true`, `false` | SMTP only; Brevo's values in production (§2 #3) |
| `DJANGO_DEFAULT_FROM_EMAIL` | `webmaster@localhost` | the sender; must be verified in Brevo. Added by the email issue |

- `settings.py` calls `django_stubs_ext.monkeypatch()` at the top; settings are fully annotated.
- `TEMPLATES[0]["DIRS"] = [BASE_DIR / "templates"]` for `base.html` and the login page; app
  templates stay in the apps.
- Auth: `LOGIN_URL = "login"`, `LOGIN_REDIRECT_URL = "/"`, `LOGOUT_REDIRECT_URL = "login"`;
  logout is a POST form in the header.
- Middleware: Django's `LoginRequiredMiddleware`: every view needs a login unless marked
  `@login_not_required` (login, logout, password reset, registration).
- Email: Django 6.1's `MAILERS["default"]`, built from the `EMAIL_*` variables.
- SQLite: `init_command` sets `journal_mode=WAL` and `synchronous=NORMAL`;
  `transaction_mode = "IMMEDIATE"`; `timeout = 20`.
- Tailwind and daisyUI: `TAILWIND_CLI_USE_DAISY_UI = True`, `TAILWIND_CLI_VERSION = "2.10.35"`
  (tailwind-cli-extra's version, not Tailwind's: it bundles Tailwind 4.3.4 and daisyUI 5.7),
  `TAILWIND_CLI_SRC_CSS = "assets/css/source.css"`, built CSS git-ignored. Each app adds an
  `@source` line to `source.css`.
- Media: `MEDIA_ROOT = BASE_DIR / "var" / "media"`, `MEDIA_URL = "media/"` (added by the photos
  issue, §6.8). On Dokku `var/` is the storage mount; nginx allows 10 MB uploads
  (`docs/deployment/deploy-to-dokku.md`).
- Static files: WhiteNoise with `CompressedManifestStaticFilesStorage`; tests switch to plain
  storage (`docs/testing/static-files.md`).
- HTTPS: `SECURE_SSL_REDIRECT` off (the proxy redirects; a healthcheck may be plain HTTP),
  `security.W008` and `security.W021` silenced.
- `USE_I18N = False`: the app is English only.

## 10. Typing conventions

As erasmops (its §10), verified against Django 6.1 + django-stubs 6.1.1 + pyrefly 1.3.1:

- `[tool.pyrefly] preset = "strict"`, `project-excludes = ["**/migrations/**"]`.
- Django generic bases are parameterised: `admin.ModelAdmin[Event]`, `forms.ModelForm[Event]`.
- Declarative class attributes are tuples, not lists (`Meta.constraints`, `ordering`,
  `list_display`, …).
- Overrides of Django hooks carry `@typing.override`.
- No `.values()` / `.values_list()`. `.annotate()` attributes aren't typed: Python code that
  needs one gets it from a function that returns a dataclass (templates may read them).
- Custom QuerySets: `objects: EventQuerySet = EventQuerySet.as_manager()` with
  `# pyrefly: ignore[bad-assignment]`: pyrefly 1.3 types `as_manager()` and `from_queryset()` as
  a plain `Manager` and loses the custom methods (checked 2026-11-21;
  `docs/typing/custom-querysets.md`).
- View tests go through `django.test.Client`, not `RequestFactory`.
- Not caught by the type checker, so tests cover them: invalid `filter()` keywords, `None` into
  Char fields, arbitrary strings into `TextChoices` fields.
- `# pyrefly: ignore[<code>]` only with the specific code and a one-line reason.

## 11. Quality gate

`scripts/check.sh`: ruff check, ruff format --check, pyrefly, pytest, then
`manage.py check --deploy --fail-level WARNING` with production-like variables
(`DJANGO_DEBUG=false DJANGO_HTTPS=true DJANGO_ALLOWED_HOSTS=example.com`, SMTP email).

- **Pre-commit hook:** `.githooks/pre-commit` calls it; enable with
  `git config core.hooksPath .githooks` (README).
- **Ruff:** `select = ["E", "F", "W", "I", "UP", "B", "DJ", "PT", "SIM", "RUF"]`,
  `extend-exclude = ["**/migrations/**"]`; `[tool.ruff.format] exclude = ["SPEC.md"]`.
- **pytest:** `DJANGO_SETTINGS_MODULE = "config.settings"`, `testpaths = ["tests"]`; one
  top-level `tests/` with a package per app (every directory has an `__init__.py`); module-level
  `pytestmark = pytest.mark.django_db`; test data from `make_*` fixtures in `tests/conftest.py`
  that call `full_clean()`, no factory_boy. No coverage target.
- **Tests that must exist (skeleton):** anonymous requests redirect to login; login and logout;
  `admin_client` opens every changelist of every registered model; models and migrations agree;
  the env helper and the settings it drives.
- **Tests that must exist (features):** each rule in §6 has a test, including its forbidden case
  (someone else's event, a closed window, a started event, a full event); every email in §6.6 is
  checked in `mailoutbox`; the event list and "My events" each have a `django_assert_num_queries`
  test.
- **Line endings:** `.gitattributes` keeps LF on every OS, so the bash scripts also run from a
  Windows checkout.

## 12. Milestones

Each milestone is a set of issues in `issues/`, in order; issues inside a milestone can run in
parallel once their dependencies are merged.

- **M1 Accounts:** the custom user model (first: it must be in the first migration); photos;
  registration windows in the admin; registration and email verification; profiles and
  passwords; email through Brevo.
- **M2 Events:** the event model, create and the admin review; the event list and page; join,
  leave and the waiting list; editing and pending changes; cancelling; My events.
- **M3 Running it:** soft delete; demo data (`manage.py seed_demo`, dev only); the first deploy
  with the guide, including photos in the backup; mobile dock and polish against the wireframes.

## 13. Out of scope

Dropped from `docs/app-plan.md` to keep it simple (§2): drafts; events in review shown to
everyone; types written by organizers and an admin-managed type list; the organizer accepting the
waiting list; on-site notifications; closing sign-ups while changes are reviewed.

Not planned: pagination, maps, comments or chat, end times and recurring events, several time
zones, translations (English only), social login, payments, cleaning up replaced photo files.
