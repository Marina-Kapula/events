# Choose a UI library, and style the base layout

Status: todo · Opened: 2026-11-21 · Milestone: M1 · Depends on: —

## Why

Every page of the app extends `templates/base.html`, so the look you choose now is the look of
every later issue. The skeleton ships Tailwind + daisyUI so the pages aren't bare, but SPEC.md
§2 #19 leaves the choice to you: keep it, or switch to something you prefer.

Choosing a tool by comparing trade-offs, and writing down why, is a real part of the job: the
next person (or you, in three months) will ask "why this one?". Do it now, before the feature
issues write dozens of templates: switching later means restyling all of them.

## What you'll build

- A decision: one UI library (it may be the one already there), recorded with the reasons in
  SPEC.md §2 #19 and §3.
- `templates/base.html` restyled as in the wireframes: the navigation at the top on wide screens
  and at the bottom on phones, messages at the top, a "Skip to content" link.
- The login page and the home placeholder restyled.
- If you switch: the old tooling removed everywhere.

Not in this issue: the pages of later issues (each issue styles its own pages with your choice),
icons, a dark-mode switch (following the device's setting is enough).

## Before you start

Read:
- SPEC.md §2 #2 and #19; §3 (Stack); §7 (Screens).
- `docs/wireframe-desktop.svg` and `docs/wireframe-mobile.svg` (open them in a browser).
- AGENTS.md: Views and templates (partials, and "UI-only state uses HTML/CSS first").
- `docs/testing/static-files.md`.
- [Django: Managing static files](https://docs.djangoproject.com/en/6.1/howto/static-files/) and
  [template partials](https://docs.djangoproject.com/en/6.1/ref/templates/language/#template-partials).

Words you'll meet:
- **Utility classes** (Tailwind): many tiny classes, one CSS property each (`p-4`, `flex`),
  combined in the HTML.
- **Component classes** (daisyUI, Bootstrap, Bulma): one class per piece of UI (`btn`, `card`,
  `navbar`).
- **Classless CSS** (Pico): styles plain HTML elements; you write good semantic HTML and add
  almost no classes.
- **Build step**: a program that produces your CSS before it can be served. Tailwind has one: it
  scans the templates for the classes you used.
- **Vendoring**: copying a library's file into your repo (`assets/static/vendor/`) instead of
  loading it from someone else's server (a CDN).
- **Mobile-first**: write the phone layout first, then add `@media (min-width: …)` rules for
  wider screens.

## Steps

### 1. Compare the options

| Option | How you style | Build step | JavaScript | CSS size (min + gzip) | Dark mode | Strong at | Costs |
|---|---|---|---|---|---|---|---|
| **Tailwind + daisyUI** (the skeleton's default) | utility classes, plus daisyUI components, in the HTML | yes: `tailwind runserver` while you work, `tailwind build` in the Docker image | none | only the classes you use | follows the device (already set up) | already works; daisyUI's `dock` is the phone bottom bar of the wireframe; everything is visible in the template | long `class` lists; a build step (a downloaded binary, no Node); each new app adds an `@source` line; two sets of docs |
| **Pico CSS 2** | plain semantic HTML, a few classes | no | none | ~12 KB | automatic | tiny; readable templates; forms look good with no work | few components (no badges, no card grid): you write some CSS of your own |
| **Bootstrap 5.3** | component and utility classes | no | optional, and we skip it | ~31 KB | `data-bs-theme`; following the device needs a small script | the best-known; examples for everything | several components need its JavaScript (collapse, dropdown, modal, dismissible alerts): use HTML instead; looks "like Bootstrap" |
| **Bulma 1.0** | component and helper classes (`button is-primary`) | no | none, by design | ~66 KB | automatic | readable class names; no JavaScript at all | the biggest file; the navbar's burger menu needs your own JavaScript (the bottom nav avoids it) |
| **Plain CSS** | your own classes in `assets/static/css/app.css` | no | none | what you write | `@media (prefers-color-scheme: dark)`, by you | you learn CSS itself (flexbox, grid, media queries); no dependency | the most work; keeping it consistent is up to you |

Sizes measured in November 2026 (Pico 2.1.1, Bootstrap 5.3.9, Bulma 1.0.4); WhiteNoise sends
them compressed.

None of them is wrong for this app. Questions that help:
- How much CSS do you want to write and learn yourselves?
- Do you prefer reading `class="btn btn-primary"` or plain `<button>`?
- Is the build step a problem for anyone in the team (it runs on Windows, macOS and Linux)?

If you can't decide, try two: restyle only the login page with each, in a throwaway branch, for
half an hour each. Then compare the templates and the result.

- [ ] The team has looked at the options (and tried at least one besides the default, if
      unsure).

### 2. Decide, and write it down

Update SPEC.md in this branch (AGENTS.md: "when a decision changes, update SPEC.md"):

- **§2 #19**: replace "is the students' choice" with the decision, in the table's format:

  ```
  | 19 | **The UI library is <name> <version>, <how it is loaded>.** <How templates use it, one sentence.> | <Why, 2–3 sentences: what mattered to you.> Not chosen: <option> (<reason>), <option> (<reason>). |
  ```

- **§3**: the library's row (name, version, role). If you drop Tailwind, the
  `django-tailwind-cli` row goes.
- If you switch: §4 (the `assets/` line), §7 ("daisyUI templates" in the auth views row) and §9
  (the Tailwind bullet).

- [ ] SPEC.md §2 #19 and §3 say what you chose and why, and what you didn't choose.

### 3. Set it up

**Keeping Tailwind + daisyUI**: nothing to install. Work with
`uv run python manage.py tailwind runserver` (the dev server and a watcher that rebuilds the CSS).
Look up components on [daisyUI](https://daisyui.com/components/) (`navbar`, `dock`, `alert`,
`card`, `btn`, `input`, `badge`). When an issue adds templates in a new app, it adds a line to
`assets/css/source.css`, for example `@source "../../accounts/templates";`, or those classes are
missing from the built CSS.

**Pico, Bootstrap or Bulma: one CSS file, vendored.** Download the minified file into
`assets/static/vendor/`, with the version in the URL so the file matches SPEC.md §3:

```sh
mkdir -p assets/static/vendor
curl -L -o assets/static/vendor/pico.min.css \
  https://cdn.jsdelivr.net/npm/@picocss/pico@<version>/css/pico.min.css
```

| Library | File URL |
|---|---|
| Pico | `https://cdn.jsdelivr.net/npm/@picocss/pico@<version>/css/pico.min.css` |
| Bootstrap | `https://cdn.jsdelivr.net/npm/bootstrap@<version>/dist/css/bootstrap.min.css`, and the same URL with `.map` at the end (see Watch out) |
| Bulma | `https://cdn.jsdelivr.net/npm/bulma@<version>/css/bulma.min.css` |

Then link it in `templates/base.html`, followed by your own small file for what the library
doesn't do (the bottom nav, for example):

```django
{% load static %}
<link rel="stylesheet" href="{% static 'vendor/pico.min.css' %}">
<link rel="stylesheet" href="{% static 'css/app.css' %}">
```

Why vendored rather than a `<link>` to the CDN? The file is served by your own app (WhiteNoise,
with a hashed name and long caching), it works offline, and no third party sees every student's
IP address with each page view (the same privacy reason as SPEC.md §2 #13). A CDN link is shorter
to set up; if you use one, pin the exact version and add the `integrity="sha384-…"` and
`crossorigin="anonymous"` attributes the library's docs give you, so a changed file is refused.

**Plain CSS**: create `assets/static/css/app.css` and link it as above. Start with
`:root { color-scheme: light dark; font-family: system-ui, sans-serif; }` and build up from the
wireframes.

**Leaving Tailwind**: remove it everywhere, so nobody runs a build step for nothing:
- `uv remove django-tailwind-cli`
- `config/settings.py`: `"django_tailwind_cli"` in `INSTALLED_APPS`, the `TAILWIND_CLI_*`
  settings and their comment, and the Tailwind part of the `STATICFILES_DIRS` comment.
- `templates/base.html`: `{% load tailwind_cli %}` and `{% tailwind_css %}`.
- `assets/css/source.css`: delete it.
- `Dockerfile`: the `tailwind build` command and the `.django_tailwind_cli` cache mount; keep
  `collectstatic`, and fix the comment above it.
- `.gitignore` and `.dockerignore`: the Tailwind lines.
- `README.md` (Development), `docs/deployment/deploy-to-dokku.md` (part 10's "the Tailwind
  stylesheet", and the troubleshooting row about the Tailwind CLI), `docs/testing/static-files.md`.
- Locally: `rm -rf .django_tailwind_cli assets/static/css/tailwind.css`.

Check: `git grep -n -i -e tailwind -e daisy` finds only `issues/`, `docs/app-plan.md` (the
students' original plan) and your own "Not chosen" in SPEC.md.

- [ ] The library is set up (or Tailwind is kept), and nothing of an unused one is left.

### 4. Restyle the base layout

What `base.html` must have (SPEC.md §7, the wireframes):
- **A header** with the site name, the navigation, the user's email and a **Log out** button (a
  POST form, AGENTS.md).
- **The navigation at the top on wide screens, at the bottom on phones**, where thumbs reach it.
  For now it has one link, Events; later issues add theirs (Create in 010, Profile in 009, My
  events in 016; staff see only Events, SPEC.md §6.9).
- **Messages** at the top, one per message, styled by `message.level_tag` (`success`, `error`,
  `warning`, `info`).
- **A "Skip to content" link** first in the page, visible when it gets keyboard focus, pointing to
  `<main id="main">` in every page.

The structure, without any library's classes. The links live in one partial, used by both navs:

```django
{% load static %}<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}AMFI Meetups{% endblock %}</title>
  {# your library's stylesheet and your own (step 3) #}
</head>
<body>
  <a href="#main" class="skip-link">Skip to content</a>
  {% block header %}
  <header>
    <a href="{% url 'home' %}">AMFI Meetups</a>
    <nav aria-label="Main" class="nav-top">{% partial nav_links %}</nav>
    <span>{{ user.get_username }}</span>
    <form method="post" action="{% url 'logout' %}">
      {% csrf_token %}
      <button type="submit">Log out</button>
    </form>
  </header>
  <nav aria-label="Main" class="nav-bottom">{% partial nav_links %}</nav>
  {% endblock %}
  {% if messages %}
  <div role="status">
    {% for message in messages %}
    <p class="message message-{{ message.level_tag }}">{{ message }}</p>
    {% endfor %}
  </div>
  {% endif %}
  {% block content %}{% endblock %}
</body>
</html>

{% partialdef nav_links %}
<ul>
  <li><a href="{% url 'home' %}"{% if request.resolver_match.url_name == 'home' %} aria-current="page"{% endif %}>Events</a></li>
</ul>
{% endpartialdef %}
```

- `{% partialdef %}` defines a piece of template once; `{% partial nav_links %}` renders it. It
  can sit at the end of the file, and pages that extend `base.html` get it too.
- Shape the links as your library's navigation expects: Pico and Bootstrap use `<ul><li>`,
  daisyUI's `dock` and Bulma's `navbar` want the `<a>` elements directly. If the two navs need
  different markup, write two partials.
- Both navs are inside `{% block header %}`, so the login page, which empties that block, has
  neither.
- `aria-current="page"` tells screen readers which page this is; style the current link with it
  (`[aria-current="page"]`) rather than with a second class.

Only one nav shows at a time. In plain CSS (works next to any library), mobile-first:

```css
.nav-top { display: none; }
.nav-bottom { position: fixed; inset-inline: 0; bottom: 0; }
body { padding-bottom: 4rem; } /* the bottom nav must not cover the page's end */

@media (min-width: 48rem) {
  .nav-top { display: block; }
  .nav-bottom { display: none; }
  body { padding-bottom: 0; }
}

.skip-link { position: absolute; left: -100vw; }
.skip-link:focus { left: 1rem; top: 1rem; }
```

Or with the library's own classes: Tailwind `hidden md:block` and `md:hidden`; Bootstrap
`d-none d-md-block` and `fixed-bottom d-md-none`; Bulma `is-hidden-mobile` and
`is-hidden-tablet`. The current `base.html` is a working daisyUI example of the header and the
messages.

- [ ] `base.html` has the header, both navs, the messages and the skip link.

### 5. Restyle the login page and the home placeholder

`templates/registration/login.html` is Django's login form, written out by hand. Keep what makes
it work: the field names (`username`, `password`, the hidden `next`), `{% csrf_token %}`, the
`autocomplete` attributes, one `<label for>` per input, and the errors next to their field. Change
only the look.

`templates/home.html` is a placeholder until issue 012: restyle it, and keep its link to the
admin.

- [ ] The login page and the home placeholder use your library.

### 6. Check it like a user

- **Phone and desktop**: in the browser's developer tools, switch to a phone size (about 375 px
  wide). The bottom nav shows, the top one doesn't, nothing scrolls sideways. Then a laptop size.
- **Keyboard only**: press Tab from the top of the page. The skip link appears first, then the
  links and buttons, each with a visible focus outline. Enter on the skip link jumps to the
  content.
- **Contrast**: text against its background at least 4.5:1 (the browser's accessibility
  inspector shows it, or the [WebAIM contrast checker](https://webaim.org/resources/contrastchecker/)).
- **Dark mode**: switch your system to dark, reload; everything is still readable.
- **Static files as in production**: `collectstatic` runs in the Docker image, and it fails on a
  broken CSS reference. Run it once (with Tailwind, `tailwind build` first), then delete the
  output folder (git-ignored anyway):

  ```sh
  uv run python manage.py collectstatic --noinput && rm -rf staticfiles
  ```

- [ ] All five checks pass. Screenshots of phone and desktop are in the PR.

## Done when

- [ ] SPEC.md §2 #19 and §3 name the library, its version, how it is loaded, why it was chosen,
      and what wasn't.
- [ ] `base.html`: top nav on wide screens, bottom nav on phones, messages, skip link.
- [ ] The login page and the home placeholder are restyled.
- [ ] If Tailwind was dropped, nothing of it is left (`git grep`), and `collectstatic` works.
- [ ] Keyboard, contrast and dark mode checked (step 6).
- [ ] `scripts/check.sh` passes: the smoke tests in `tests/test_smoke.py` still find what they
      look for.
- [ ] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 003-choose-a-ui-library
```

Suggested commits (each one passes `scripts/check.sh`):
1. `Record the UI library choice in SPEC.md`
2. If you switch: `Add <library>` and `Remove django-tailwind-cli`
3. `Add a bottom navigation on phones to the base layout`
4. `Restyle the login page and the home placeholder`
5. `Close 003 in the issue`

Open a pull request titled "Choose a UI library, and style the base layout". Put the screenshots
(phone and desktop, light and dark) in the description, and link the SPEC.md row: the reviewer
should be able to agree or disagree with your reasons. `docs/workflow/git.md` has every step.

## Watch out

- **The smoke tests look for exact strings** on the home page: `aria-current="page"`, the user's
  email, the admin link, and `<form method="post" action="/accounts/logout/">` exactly (add a
  class to that tag and the test fails; then change the test on purpose, not by accident).
- **Bootstrap's `bootstrap.min.css` ends with `/*# sourceMappingURL=bootstrap.min.css.map */`.**
  The production static files storage follows that reference, and `collectstatic` (in the Docker
  build) stops with an error if the `.map` file is missing. Download the `.map` too.
- **No JavaScript components.** Bootstrap's collapse, dropdown and modal need its script; use
  `<details>`, `<dialog>` and the bottom nav instead (AGENTS.md, Views and templates).
- **No fonts or icons from other servers** (Google Fonts, icon CDNs): they see every visitor's
  IP address. Use the system fonts, or vendor the files.
- **Issue 002 also changes `login.html`** (`type="email"`). If both branches are open at once,
  expect a merge conflict there; keep both changes (`docs/workflow/git.md`, conflicts).
- **Don't restyle the Django admin.** It has its own look and is for staff only.

## Further reading

- [Django: Managing static files](https://docs.djangoproject.com/en/6.1/howto/static-files/),
  [template partials](https://docs.djangoproject.com/en/6.1/ref/templates/language/#template-partials),
  [`partialdef`](https://docs.djangoproject.com/en/6.1/ref/templates/builtins/#partialdef),
  [the messages framework](https://docs.djangoproject.com/en/6.1/ref/contrib/messages/).
- The libraries: [Tailwind](https://tailwindcss.com/docs), [daisyUI](https://daisyui.com/components/),
  [django-tailwind-cli](https://django-tailwind-cli.rtfd.io/), [Pico](https://picocss.com/docs),
  [Bootstrap](https://getbootstrap.com/docs/5.3/getting-started/introduction/),
  [Bulma](https://bulma.io/documentation/).
- MDN: [Using media queries](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_media_queries/Using_media_queries).
- W3C: [Easy checks, a first review of web accessibility](https://www.w3.org/WAI/test-evaluate/preliminary/).
- [Django: Template inheritance](https://docs.djangoproject.com/en/6.1/ref/templates/language/#template-inheritance):
  how every page fills the blocks of `base.html`, the file you restyle here.
- [MDN: Responsive web design](https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/CSS_layout/Responsive_Design):
  media queries, breakpoints and "mobile first", for the top and bottom navigation.
- [MDN: HTML, a good basis for accessibility](https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Accessibility/HTML):
  real `<button>`, `<nav>`, `<main>` and headings instead of styled `<div>`s, whichever library
  you pick.
- [MDN: `aria-current`](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Attributes/aria-current):
  what the smoke tests' `aria-current="page"` tells a screen reader.
- [MDN: `prefers-color-scheme`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-color-scheme):
  dark mode that follows the device's setting.
