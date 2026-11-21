# How a Django request works

Every page of the app is one round trip: the browser sends a **request**, Django answers with a
**response**, and the browser shows it. Knowing the steps in between tells you where to look
when something goes wrong ("why is this a 302?", "why a 403?").

```
browser ─ GET /events/5/ ─▶ nginx, gunicorn ─▶ middleware ─▶ urls.py ─▶ view ─▶ template
browser ◀─ 200 + HTML ───── nginx, gunicorn ◀─ middleware ◀─ HttpResponse ◀────────┘
```

On your laptop `runserver` stands in for nginx and gunicorn; on the server, issue 004's "big
picture" shows them. Everything from "middleware" on is the same in both places.

## 1. The request

A request is a few lines of text. Open your browser's developer tools (F12), tab **Network**,
click a request, and you see something like:

```
POST /events/5/join/ HTTP/1.1
Host: <DOMAIN>
Cookie: sessionid=…; csrftoken=…
Content-Type: application/x-www-form-urlencoded

csrfmiddlewaretoken=…
```

- **The method**: `GET` reads, `POST` changes something (`hypermedia-and-forms.md`).
- **The path**, `/events/5/join/`, plus an optional query string (`/?city=roma`): Django puts
  the query string in `request.GET`.
- **The body**, for a POST: the form's fields land in `request.POST`, uploaded files in
  `request.FILES`.
- **Headers and cookies**: the `sessionid` cookie is how Django knows who you are (below).

## 2. Middleware: what happens before every view

`MIDDLEWARE` in `config/settings.py` is a list of layers every request passes through, top to
bottom, and every response on the way back. Ours, among others:

- `SessionMiddleware` reads the `sessionid` cookie and loads your session.
- `CsrfViewMiddleware` refuses a POST without a valid CSRF token: **403**.
- `AuthenticationMiddleware` turns the session into `request.user`.
- `LoginRequiredMiddleware` sends anonymous visitors to `/accounts/login/?next=…` (a **302**),
  unless the view is marked `@login_not_required`. That's why our views never check "is anyone
  logged in?": they only check *who* it is.
- `MessageMiddleware` makes `messages.success(...)` work.

## 3. `urls.py`: which view?

Django walks `urlpatterns` from the top and calls the view of the **first** pattern that
matches. Nothing matches: **404**.

```python
path("events/<int:pk>/", views.event_detail, name="event_detail"),
```

`<int:pk>` matches digits only and passes them to the view as `pk=5` (an `int`). The `name` is
how the rest of the code builds the URL without typing it: `{% url 'event_detail' event.pk %}`
in a template, `redirect("event_detail", pk=event.pk)` in a view.

## 4. The view: a function from request to response

```python
def event_detail(request: HttpRequest, pk: int) -> HttpResponse:
    user = request.user
    if not isinstance(user, User):
        raise Http404
    event = get_object_or_404(Event.objects.visible_to(user), pk=pk)
    return render(request, "events/event_detail.html", {"event": event})
```

A view has three ways out, and you will write all three:

| Way out | Response | When |
|---|---|---|
| `render(request, template, context)` | 200 and the HTML | show a page (also a form with errors) |
| `redirect("name", ...)` | 302 and a `Location` header | after a successful POST; the browser then GETs that URL |
| `raise Http404` / `get_object_or_404` | 404 | the thing doesn't exist, **or** this user may not see it |

We answer "not yours" with a 404, not a 403 (AGENTS.md): a 403 would confirm the event exists.

## 5. The template

`render()` fills a template with the context. Every page starts with `{% extends "base.html" %}`
and fills `base.html`'s blocks (`title`, `content`), so the navigation and the messages are
written once. Django **escapes** every `{{ value }}`: a name like `<script>` shows as text and
doesn't run. `request`, `user` and `messages` are available in every template.

## 6. The response and its status code

The codes you will meet in this project:

| Code | Meaning here |
|---|---|
| 200 OK | a page; also a form shown again with its errors |
| 302 Found | a redirect: after a POST that worked, or to the login page |
| 400 Bad Request | Django refused suspicious input (a path like `/media/../.env`) |
| 403 Forbidden | the CSRF token is missing or wrong |
| 404 Not Found | no such URL, or something this user may not see |
| 405 Method Not Allowed | a GET to a POST-only view (`@require_POST`) |
| 413 Content Too Large | nginx refused an upload over 10 MB, before Django saw it |
| 500 Server Error | an exception in our code: read the traceback (`runserver`'s console, or `dokku logs`) |

## How the server remembers you: sessions and cookies

HTTP itself forgets everything between two requests. When you log in, Django's `login()` saves
your user id in a **session** (a row in the database) and the response sets a cookie,
`sessionid`, holding only that session's random key. The browser sends the cookie with every
later request, and the middleware turns it back into `request.user`. Logging out deletes the
session. Whoever has the cookie *is* you, which is why the site runs on HTTPS and
`DJANGO_HTTPS=true` marks the cookies "Secure" (sent over HTTPS only).

## The test client makes the same trip

`client.get("/events/5/")` in a test goes through the middleware, `urls.py`, the view and the
template, just without a browser or a server. So a test can check exactly what a browser would
get: `response.status_code`, `response["Location"]`, `response.content`
(`testing-with-pytest-django.md`).

## When something goes wrong

- **404 for a page that should exist**: is the URL in `urls.py`, and is the app's `urls.py`
  included in `config/urls.py`? Or does the view's query (`visible_to`, `organizer=user`) leave
  it out on purpose?
- **302 to the login page in a test**: the test didn't log in (`client.force_login(user)`).
- **403 on a form**: `{% csrf_token %}` is missing inside the `<form>`.
- **405**: a link (`<a href>`, a GET) points at a POST-only view; use a form with a button.
- **500**: read the traceback from the bottom up; the last lines in *your* files are the place.

## Further reading

- [MDN: How the web works](https://developer.mozilla.org/en-US/docs/Learn_web_development/Getting_started/Web_standards/How_the_web_works):
  what happens between typing an address and seeing the page.
- [MDN: An overview of HTTP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Overview):
  requests, responses and headers, with real examples.
- [MDN: HTTP response status codes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status),
  and Julia Evans' one-page comic [status codes](https://wizardzines.com/comics/status-codes/).
- [Django tutorial, part 1](https://docs.djangoproject.com/en/6.1/intro/tutorial01/) and
  [part 3](https://docs.djangoproject.com/en/6.1/intro/tutorial03/): views, URLs, templates and
  404s, built step by step.
- Django: [URL dispatcher](https://docs.djangoproject.com/en/6.1/topics/http/urls/),
  [Writing views](https://docs.djangoproject.com/en/6.1/topics/http/views/),
  [Request and response objects](https://docs.djangoproject.com/en/6.1/ref/request-response/),
  [Middleware](https://docs.djangoproject.com/en/6.1/topics/http/middleware/).
- [MDN: Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies) and
  [Django: How to use sessions](https://docs.djangoproject.com/en/6.1/topics/http/sessions/).
