# AMFI Meetups — spec

Status: agreed in a planning interview on 2026-11-20/21, starting from the students' plan in
`docs/app-plan.md` and the wireframes next to it. Where they differ, this file wins; §2 says what
changed and why, §13 what was dropped. Rule of the interview: when in doubt, the option that is
easiest to implement. The stack, conventions and quality gate are copied from the teacher's
reference projects.

## 1. Goal

A Meetup-like web app for Erasmus students hosted by AMFI International (Avezzano). Students
create events in any city (meetups, pizza nights, trips) and join other students' events; an
AMFI admin reviews every event so there are no fakes. Language: English.

It is built by students learning full-stack development, with AI agents allowed: a simple,
idiomatic Django app (server-rendered pages, plain forms, full page loads, little JavaScript).

## 2. Decisions

| # | Decision | Why |
|---|---|---|
| 1 | **Mixed layering.** Reads are custom `QuerySet` methods; plain one-model create/edit uses `ModelForm.save()`; state changes, rules, multi-model writes and emails go through `services.py` functions. Function-based views. | Idiomatic Django a student can explain, with one tested home for the rules where the bugs will be (event states, spots, waiting list). Not chosen: strict services/selectors for every write (ceremony for simple forms); plain fat models (rules scattered over `save()` and views). |
| 2 | **Hypermedia-driven and Django-native, without HTMX.** The server sends HTML; links and forms move the user through the app; every change is a POST that redirects (Post/Redirect/Get) with a `django.contrib.messages` message. Django's own features come first: forms and ModelForms, auth views, messages, the admin, template inheritance and template partials (`{% partialdef %}`), QuerySets. Django's `LoginRequiredMiddleware`. | Fewer moving parts for students, and the web's own model (HTML, links, forms) is what they learn. Template partials are enough for reuse. |
| 3 | **Email through Brevo's SMTP relay** (`smtp-relay.brevo.com`, port 587, STARTTLS), using Django's SMTP backend and the `EMAIL_*` variables (§9). | No new dependency. Not chosen: django-anymail's Brevo API backend (a dependency for the same result). |
| 4 | **Each student deploys their own copy** on their own OVHcloud VPS with Dokku, following `docs/deployment/`. | Learning by doing; the teacher's server and notes stay private. |
| 5 | **Registration through an expiring QR code, at the welcome meeting.** At the end of the presentation on the Erasmus rules, the admin generates a QR code that expires after a set time. Attendees scan it and register themselves with their email and details. The email address is confirmed through a verification link before the account works. Replaces the emailed invitations of `docs/app-plan.md` #3–4. | Everyone is in the room with a phone: they sign up on the spot, and the admin types nobody in. The expiry and the verified email keep a forwarded photo of the QR code from being much use. |
| 6 | **Custom user model, email as the login.** `accounts.User(AbstractBaseUser, PermissionsMixin)` with `USERNAME_FIELD = "email"` and no username, from the first migration (§5). | Students register with their email. Django recommends a custom user model from the start; switching later means rebuilding the migrations. |
| 7 | **A registration window is a database row.** It stores who opened it, when it expires, and whether it was closed early. The QR code holds `/register/<random code>/`. The window is checked when the page opens and again when the form is sent. Each user stores the window they came through. | The admin can close a window early and see who registered at which meeting. Someone who missed the meeting gets a new window, opened in the office. |
| 8 | **The QR image is drawn on the server with `segno`, as inline SVG** (§3). | Pure Python with no dependencies of its own; no JavaScript and no image files. |
| 9 | **The account is inactive until the email link is clicked.** The link carries a token from Django's token generator, as in password reset. The login page offers to resend it. | Stops sign-ups with someone else's address or a typo; no new dependency. |
| 10 | **Registration takes the whole profile in one form**: full name, email, password, photo, nationality, age, gender. All fields are required. On a phone the photo field opens the front camera (`capture="user"`). | Nobody has half a profile, so the "complete your profile first" check of `docs/app-plan.md` #8 isn't needed. Not chosen: account first and profile later (an extra state and a check on every join and create). |
| 11 | **The admin picks how long a window stays open**: 15 min, 30 min (preselected), 1 h or 2 h. Its admin page shows the QR code, when it expires and who has registered; "Close now" is an admin action (§8). The window must still be open when the form is sent; otherwise the student sees "Registration closed, ask the AMFI staff". | The presenter knows how long the meeting runs; closing early cuts off a forwarded QR code. Not chosen: one fixed duration; a personal grace period after scanning (a signed timestamp and one more rule, rarely needed with 30 minutes). |
| 12 | **Profile fields**: full name (one field), age (a number, 16–99), nationality (`django-countries`' `CountryField`), gender (Female / Male / Other). All required for students. | As `docs/app-plan.md` #6. One name field fits international names. Age rather than a birth date: less sensitive, and students can edit it. django-countries is the standard full country list (§3). |
| 13 | **Photos are served by Django to logged-in users only.** They are stored in `var/media/` (inside the storage mount), returned by a login-required view with `FileResponse`, shrunk on upload to at most 1024 px and re-saved as JPEG with Pillow, which drops EXIF data and the GPS location. Uploads over 10 MB are refused with a form error. Same for profile and event photos. | Students' faces stay behind the login (GDPR), and there's no extra server setup. Not chosen: nginx serving `/media/` (public to anyone with the URL); object storage (too much for this size). |
| 14 | **Everything requires a login.** The only public pages are login, password reset, registration (with an open window) and email verification. Events, profiles and photos are for logged-in users only. | A closed community of one host organisation; personal data never reaches search engines. Django's `LoginRequiredMiddleware` already does it; public views are marked `@login_not_required`. |
| 15 | **Admins are superusers (`is_staff` and `is_superuser`), and all admin work happens in Django's admin**: registration windows (the add form asks for the duration; the window's page shows the QR code, when it expires and who registered; closing early is an action), reviews and cancelling (buttons on the event's admin page, shown by state, each calling a service so the emails go out; §8), students (soft delete is an action that calls a service) and any event. No comparison of old and new values. Admins have no student profile and don't use the student pages (§6.9); an event they create is approved at once, and they are its organizer. | As simple as possible: the custom UI is only for students, as organizers and attendees. Students learn to configure the admin (`list_display`, `search_fields`, actions, readonly fields). Not chosen: app pages for staff (more templates for the same work). |
| 16 | **Editing an approved event keeps the approved version public until the admin approves the changes; sign-ups stay open meanwhile**, and visitors see that changes are pending. Approve: the public version is updated and everyone going is notified (`docs/app-plan.md` #34). Reject: the event stays as it was, and the organizer gets the reason (#17). | Sign-ups don't stall while AMFI reviews. Replaces #16's "new sign-ups are closed". |
| 17 | **Pending changes are a second model.** The editable fields live in an abstract base model `EventFields`; `Event` and `EventChange` (one-to-one with its event, at most one per event) inherit them. Editing an approved event creates or updates its `EventChange`; events that are pending or rejected are edited directly. In the admin the change is an inline on the event's page. Approve copies the fields over and deletes the change; reject deletes it. Max people can't go below the number already going: checked by the form, and again on approval. | Typed fields and no JSON blob. The admin sees proposed and current values on one page, with no comparison code. |
| 18 | **Pending changes show as a warning only**: a "Changes pending" badge on the event's card and one line on its page. The proposed values are not shown. | Easiest; people going are emailed once the changes are approved. Not chosen: showing the proposed version. |
| 19 | **The UI library is the students' choice** (issue 003). The skeleton ships a working default: Tailwind + daisyUI through django-tailwind-cli (`TAILWIND_CLI_USE_DAISY_UI`, the tailwind-cli-extra binary, no Node). Keep it or switch (Bootstrap, Pico CSS, Bulma, plain CSS, …); the choice and why go in this row and §3. | Choosing, and writing down why, is part of the learning. |
| 20 | **No drafts.** Saving a new event sends it to review (`pending`). A rejected event shows its reason to the organizer, who edits it (back to `pending`) or cancels it. | One state and one button fewer. Replaces `docs/app-plan.md` #12, and #15's "back to draft". |
| 21 | **Only approved events are public.** A pending or rejected event is seen only by its organizer (and in the admin). | The list has one kind of card. Replaces #13 (events in review shown to everyone as "not approved"). |
| 22 | **Event types are a fixed list in code** (`TextChoices`): Meetup, Food, Trip, Sport, Party, Culture, Other. | No model, admin page or data migration; a new type is one line of code. Replaces #9's type written by the organizer and #10/#31's admin-managed list. |
| 23 | **"We will speak" is free text**, default "English". | No list to maintain. |
| 24 | **The organizer takes one spot but has no participation row**: spots taken = 1 + people going. The organizer can't join or leave their own event; they cancel it instead. | No special cases in join and leave. As #11. |
| 25 | **A waiting list without the organizer.** When the event is full, "Join" becomes "Join the waiting list". When a spot frees up (someone going leaves, or approved changes raise max people), the first person waiting gets it automatically and is emailed. Anyone can leave the waiting list. | Nobody has to accept anyone. As #25 and #35; replaces #24's organizer accepting or declining. |
| 26 | **Leaving deletes the participation**, allowed until the event starts. The organizer is emailed when someone going leaves. | No "left" state to filter out. As #23 and #33. |
| 27 | **Cancelling an event** (the organizer before it starts, the admin any time) sets it `cancelled`, deletes a pending `EventChange`, and emails everyone going or waiting. It can't be undone. Participations are kept, so the event stays in everyone's "My events". | As #34; replaces #18's "at any time" for the organizer (after the start there is nothing to cancel). |
| 28 | **Notifications are emails only** (§6.6), sent from services in `transaction.on_commit`. | No notification model, page or unread badge. Replaces #32's "and to the site". |
| 29 | **The event list** shows approved events that are not cancelled and haven't started, soonest first, without pagination. Filters in one GET form: keyword (title or description contains), city (contains), date (events on that day), type, size (max people: up to 5, 6–10, more than 10). A plain `forms.Form` and QuerySet methods. | As #20–21. Not chosen: django-filter (a dependency for five filters). |
| 30 | **"My events" is one page with two lists**: created by me (every own event, with a status badge, and the reason when it is `rejected`) and joined by me (going and waiting; upcoming first, then past and cancelled). | As #26–27, without tabs. A rejected change's reason goes by email only. |
| 31 | **Every logged-in user can see every active student's profile**; students edit their own (the registration fields except email and password). Password change and reset are Django's auth views. | As #5 and #7. |
| 32 | **Soft delete is an admin action** (§6.7): the account becomes inactive and gets a `deleted_at`, the student's upcoming events are cancelled (with emails), and their participations are deleted (the waiting lists move up). Their profile is gone and they can't log in. | As #28. A real erasure, if someone asks for it: delete the student's events in the admin, then the student (`organizer` is `PROTECT`). |
| 33 | **Edits in the Django admin send no emails**; only Approve and Reject do. Deleting an event in the admin is a hard delete without emails: to tell people, cancel it instead. | The admin is a correction tool; the rules live in the student pages and the review buttons. |
| 34 | **Events have a start and no end**, in one time zone (Europe/Rome). An event is past once it has started. | As #9 and #21. |
| 35 | **Links in emails and the QR code come from `SITE_URL`** (`DJANGO_SITE_URL`, §9), never from `request`. | Services and admin readonly fields have no request (AGENTS.md). |
| 36 | **Emails are lowercased** in the registration, resend and login forms. | Phone keyboards capitalise the first letter; the email is unique and the login compares exactly. |
| 37 | **Git: one feature branch and one pull request per issue** on GitHub, reviewed before merging (`docs/workflow/git.md`). | Students practise the workflow of real teams; `main` always works. |

## 3. Stack

As the teacher's reference projects, plus email settings.

| Package | Version | Role |
|---|---|---|
| Python | 3.14 | runtime (`.python-version`); uv installs it |
| uv | — | env + deps; everything runs through `uv run` |
| Django | 6.1.x | web framework, auth, admin, ORM (SQLite), email |
| django-stubs-ext | 6.1.x | runtime `monkeypatch()` so `admin.ModelAdmin[Event]` etc. can be subscripted |
| django-tailwind-cli | 4.8.x | the skeleton's default UI tooling: Tailwind v4 + daisyUI 5 through the standalone tailwind-cli-extra binary (no Node); issue 003 keeps or replaces it (§2 #19) |
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

**accounts.User** (`AbstractBaseUser` + `PermissionsMixin`; a `BaseUserManager` with `create_user`
and `create_superuser` by email; `USERNAME_FIELD = "email"`, `REQUIRED_FIELDS = ["full_name"]`).
Not `AbstractUser` with `username = None`: strict pyrefly rejects that (`bad-assignment`).

| Field | Type | Notes |
|---|---|---|
| email | `EmailField`, unique | the login; stored lowercase (§2 #36) |
| full_name | `CharField(100)` | |
| photo | `ImageField` | `photos/users/`; empty for staff |
| nationality | `CountryField` | empty for staff |
| age | `PositiveSmallIntegerField`, null | 16–99 validators; null for staff |
| gender | `CharField` with `TextChoices` | female, male, other; empty for staff |
| registration_window | FK `RegistrationWindow`, null, `PROTECT` | the window the student came through |
| is_active | `BooleanField`, default false | true once the email is verified |
| is_staff | `BooleanField`, default false | admins (with `is_superuser` from `PermissionsMixin`) |
| date_joined | `DateTimeField`, default now | |
| deleted_at | `DateTimeField`, null | soft delete (§6.7) |

A `CheckConstraint`: staff, or every profile field filled in. `is_active` is false until the email
is verified, and again after a soft delete. `create_superuser` sets `is_staff`, `is_superuser` and
`is_active`.

**accounts.RegistrationWindow**: `code` (random, unique, `secrets.token_urlsafe(16)`),
`opened_by` (FK User, `PROTECT`), `opened_at`, `expires_at`, `closed_at` (null). Open while
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
2. Its admin page shows the QR code of `<SITE_URL>/register/<code>/`, when it expires and who
   registered through it.
3. `/register/<code>/` (public) shows the form while the window is open; otherwise "Registration
   closed, ask the AMFI staff". An unknown code is a 404.
4. Sending the form checks the window again, creates an inactive user (email lowercased) and
   emails a verification link. The page says "Check your email".
5. `/verify/<uidb64>/<token>/` (public) activates the account and logs the student in. A used
   or expired link says so and offers to resend. A soft-deleted user (`deleted_at` set) is never
   activated: the link answers like an expired one.
6. "Resend the verification email" (public, linked from the login page) asks for the email and
   always answers the same, so it doesn't reveal who is registered. It sends a link only to an
   inactive, not soft-deleted user.
7. An email that is already registered is a form error that links to login, password reset and
   "Resend the verification email", and says "or ask the AMFI staff".
8. The login form lowercases the email before authenticating (a small `AuthenticationForm`
   subclass passed to `LoginView`).

### 6.2 Event states

| From | Action | Who | To |
|---|---|---|---|
| — | create (student page) | a student | `pending`; staff are emailed |
| — | create (admin) | staff | `approved`; the admin is the organizer |
| `pending` | approve | staff | `approved`; organizer emailed |
| `pending` | reject with a reason | staff | `rejected`; organizer emailed with the reason |
| `pending`, `rejected` | edit (not started) | organizer | `pending` (edited in place); staff emailed |
| `approved` | edit (not started) | organizer | stays `approved`; the edit goes to its `EventChange` (§6.5); staff emailed |
| `approved` with an `EventChange` | approve changes / reject changes | staff | §6.5 |
| `pending`, `approved`, `rejected` | cancel | organizer before it starts; staff any time (admin button) | `cancelled`; the `EventChange` deleted; everyone going or waiting emailed |

`status` and `organizer` are readonly in the admin: they change only through these actions. Every
approval (new event or changes) also checks that `starts_at` is in the future; if not, the admin
sees an error and nothing changes.

### 6.3 Visibility

- The list: §2 #29 (approved, not cancelled, not started).
- An event's page: `approved` events for every logged-in user; `cancelled` ones for the organizer
  and the people on it (shown as cancelled, without buttons); `pending` and `rejected` ones for
  the organizer only, with the reason when `rejected`.
- Everything else is a 404.

### 6.4 Joining, leaving, the waiting list

- Join: the event is `approved` and hasn't started; the user isn't its organizer and isn't on it
  yet. If `1 + going < max_people` they are `going`, otherwise `waiting`. All in one transaction
  (SQLite `IMMEDIATE`), so two people can't take the last spot.
- Leave (going or waiting): before the start; the row is deleted. If they were going, the
  organizer is emailed and the waiting list moves up.
- Moving up: while there is a free spot and someone waiting, the oldest waiting becomes `going`
  and is emailed. Runs after a leave, after approved changes, and after a soft delete.
- The event page shows "Going (n of max)", where n = 1 + going: the organizer first, then
  everyone going, with photo, name, age and nationality (each a link to the profile), and
  "Waiting: n".

### 6.5 Editing

- Editing is allowed while the event is `pending`, `rejected`, or `approved` and not started;
  otherwise the edit page is a 404.
- `pending` or `rejected`: the form edits the event itself; it goes back to `pending`.
- `approved`: the form saves into the event's `EventChange` (created, or replaced if one exists).
  The form is pre-filled from the `EventChange` if there is one, else from the event; a photo
  that isn't re-uploaded keeps the same file name. The public version doesn't change, sign-ups
  stay open, and the card and page show "Changes pending" (§2 #16–#18).
- `max_people` can't be lower than 1 + going, and `starts_at` must be in the future: checked by
  the form (on create too), and both again when the admin approves.
- Approve changes (only while the event is `approved`): copy the fields to the event, delete the
  change, move the waiting list up, email the organizer and everyone going or waiting. Reject: delete the change, keep the reason in `review_note`, email the
  organizer.

### 6.6 Emails

Plain-text templates in `templates/<app>/emails/`, a subject line and a link to the page built
from `SITE_URL` (§2 #35). Sent from the services in `transaction.on_commit`.

| When | To |
|---|---|
| registration; resend | the student: the verification link |
| a student creates or edits a pending/rejected event; a student edits an approved event | every active staff user: link to the event's admin page |
| event approved; event rejected (with the reason) | the organizer |
| changes approved | the organizer, and everyone going or waiting |
| changes rejected (with the reason) | the organizer |
| someone going leaves | the organizer |
| a waiting person gets a spot | that person |
| event cancelled (by the organizer, staff, or a soft delete) | everyone going or waiting |
| password reset | the student (Django's own email) |

### 6.7 Soft delete (admin action)

In one transaction: `is_active = False`, `deleted_at = now`; their upcoming events cancelled
(§6.2, with emails); all their participations deleted, and the waiting lists of the events that
haven't started moved up. Past events they organized stay, with the organizer shown as "Deleted
student" (no photo, no link). Their profile page is a 404.

### 6.8 Photos (§2 #13)

- A form helper checks the size (10 MB at most) and that Pillow can open the file, then shrinks
  it to at most 1024 px on the long side and saves it as JPEG (quality 85), which drops the EXIF
  data.
- `MEDIA_ROOT = var/media`, `MEDIA_URL = "media/"`. `config/views.py` serves `/media/<path>`
  with `FileResponse` after `safe_join` on `MEDIA_ROOT`; `LoginRequiredMiddleware` keeps it
  for logged-in users.
- The admin's forms for users and events use the same photo field, so admin uploads are checked
  and shrunk too.
- Old files are not cleaned up when a photo is replaced.

### 6.9 Staff in the student pages

- Staff get a 404 on create, join, leave, the organizer's edit and cancel, "My events" and
  "Edit profile"; the navigation hides those links for staff. They see the list, event pages and
  profiles.
- An event organized by staff shows the organizer as "AMFI" (no photo, no link); staff edit and
  cancel their events in the admin.

### 6.10 Services

The names the issues use (AGENTS.md: `<entity>_<action>`, keyword-only arguments):

| App | Services |
|---|---|
| accounts | `user_register`, `user_verify`, `verification_resend`, `user_soft_delete` |
| events | `event_create`, `event_update`, `event_approve`, `event_reject`, `event_change_approve`, `event_change_reject`, `event_cancel`, `participation_join`, `participation_leave`, `waiting_list_move_up` |

## 7. Screens

All pages extend `base.html`: a top navigation on wide screens and a bottom navigation on phones
(Events, My events, Create, Profile; staff see only Events, §6.9), as in
`docs/wireframe-desktop.svg` and `docs/wireframe-mobile.svg`. Messages show at the top. The look
comes from the UI library of §2 #19.

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
  language, date, title, city and place, spots ("5 / 8 spots", 5 being 1 + going), and a badge
  for the status or "Changes pending".
- Buttons on the event page, by state: Join; Join the waiting list; Leave; Leave the waiting
  list; for the organizer, Edit and Cancel event (Cancel asks for confirmation in a `<dialog>`).

## 8. Admin

- `/admin/` is for staff. `admin.site.site_header = "AMFI Meetups"`; `auth.Group` unregistered.
- **Users**: list email, full name, nationality, registration window, active, staff; search email
  and name; filter active, staff, window. Action "Soft delete" calls the service (§6.7). No Add
  button (`has_add_permission` is false): students come only through registration, admins from
  `createsuperuser` (on the server: `dokku run <APP> python manage.py createsuperuser`), which
  asks for email, full name and password and sets `is_staff`, `is_superuser` and `is_active`.
  Tests override pytest-django's `admin_user` fixture, which doesn't know `full_name`.
- **Registration windows**: the add form asks only for the duration; `opened_by` is the admin.
  The change page shows the QR code (a readonly field rendering `segno`'s SVG, about 400 px wide
  for the projector; `mark_safe` is fine here: the SVG is generated, not user-derived), the URL,
  `expires_at`, open or closed, and the students who registered (readonly). Action "Close now"
  sets `closed_at`.
- **Events**: list title, organizer, start, status, "changes pending"; filter status and type;
  search title and city. `status` and `organizer` are readonly. The change page shows the
  `EventChange` and the participations as readonly inlines, and buttons by state (an override of
  the `submit_buttons_bottom` block, handled in `response_change`), each calling a service:
  - `pending`: Approve, Reject;
  - `approved` with an `EventChange`: Approve changes, Reject changes;
  - not `cancelled`: Cancel event.

  Reject and Reject changes require `review_note`. A new event added in the admin is `approved`
  with the admin as organizer.


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
| `DJANGO_SITE_URL` | `http://127.0.0.1:8000` | `SITE_URL`, the start of every link in emails and the QR code (§2 #35); `https://<domain>` in production. Added by the email issue |

- `settings.py` calls `django_stubs_ext.monkeypatch()` at the top; settings are fully annotated.
- `TEMPLATES[0]["DIRS"] = [BASE_DIR / "templates"]` for `base.html` and the login page; app
  templates stay in the apps.
- Auth: `LOGIN_URL = "login"`, `LOGIN_REDIRECT_URL = "/"`, `LOGOUT_REDIRECT_URL = "login"`;
  logout is a POST form in the header.
- Middleware: Django's `LoginRequiredMiddleware`: every view needs a login unless marked
  `@login_not_required` (login, logout, password reset, registration, verification, resend).
- Email: Django 6.1's `MAILERS["default"]`, built from the `EMAIL_*` variables.
- SQLite: `init_command` sets `journal_mode=WAL` and `synchronous=NORMAL`;
  `transaction_mode = "IMMEDIATE"`; `timeout = 20`.
- Tailwind and daisyUI (the skeleton's default, §2 #19): `TAILWIND_CLI_USE_DAISY_UI = True`,
  `TAILWIND_CLI_VERSION = "2.10.35"`
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

As the teacher's reference projects, verified against Django 6.1 + django-stubs 6.1.1 + pyrefly 1.3.1:

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
  `extend-exclude = ["**/migrations/**"]`; `[tool.ruff.format] exclude = ["SPEC.md", "issues/**",
  "docs/**"]` (partial snippets).
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
- **Emails in tests:** pytest-django's `django_db` wraps each test in a transaction that is rolled
  back, so `transaction.on_commit` callbacks never run and `mailoutbox` stays empty. Wrap the
  call in `django_capture_on_commit_callbacks(execute=True)` (`docs/testing/emails.md`).
- **Line endings:** `.gitattributes` keeps LF on every OS, so the bash scripts also run from a
  Windows checkout.

## 12. Milestones

Each milestone is a set of issues in `issues/`, in order; issues inside a milestone can run in
parallel once their dependencies are merged.

The issues are in `issues/` (board: `issues/_kanban.md`).

- **M1 Foundations and accounts (002–009):** the custom user model (first: it must be in the
  first migration); the UI library; the first deploy; email through Brevo; photos; registration
  windows in the admin; registration and email verification; profiles and passwords.
- **M2 Events (010–016):** create and send to review; the admin review; the list and the event
  page; join, leave and the waiting list; editing and pending changes; cancelling; My events.
- **M3 Running it (017–019):** soft delete; demo data (`manage.py seed_demo`, dev only); photos in
  the backup.

## 13. Out of scope

Dropped from `docs/app-plan.md` to keep it simple (§2): drafts; events in review shown to
everyone; types written by organizers and an admin-managed type list; the organizer accepting the
waiting list, and being emailed when someone joins it (#24, #33); on-site notifications; closing
sign-ups while changes are reviewed.

Not planned: pagination, maps, comments or chat, end times and recurring events, several time
zones, translations (English only), social login, payments, cleaning up replaced photo files.
