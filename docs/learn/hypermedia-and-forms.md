# Hypermedia and forms: how the app moves

This app is **hypermedia-driven** (SPEC.md §2 #2): the server sends whole HTML pages, and the
links and forms *in* those pages are the only way a user moves on. There is no JSON API and no
JavaScript framework deciding what to show. It is how the web was designed to work, and it
keeps every rule on the server, where it can be tested.

## Two controls: links and forms

HTML has exactly two ways to talk to the server:

- **A link**, `<a href="/events/5/">`: always a GET. For moving around and reading.
- **A form**, `<form method="get|post" action="…">`: sends the fields' values. GET for a search
  or a filter, POST for anything that changes data.

The page itself says what you can do *now*. The event page shows "Join" only if the event is
open and you're not on it yet; the next page is whatever the server sends back. Nobody needs to
know URLs or rules in advance: they follow what the HTML offers.

## GET or POST?

| | GET | POST |
|---|---|---|
| Where the data goes | in the URL: `/?city=roma&type=food` | in the request body |
| Use it for | reading, searching, filtering | creating, joining, leaving, cancelling, editing |
| Reload, bookmark, share | safe | the browser asks "send again?" |
| CSRF token | not needed | required |

**Anything that changes data is a POST** (AGENTS.md). Browsers prefetch links, chat apps open
them to build previews, crawlers follow them: a GET link that cancels an event *will* be
followed by something. A change is a button in a small form:

```django
<form method="post" action="{% url 'event_join' event.pk %}">
  {% csrf_token %}
  <button type="submit">Join</button>
</form>
```

and the view accepts nothing else: `@require_POST` answers a GET with 405.

## CSRF, in one paragraph

You are logged in to AMFI Meetups. Another website contains a hidden form that POSTs to
`https://<DOMAIN>/events/5/cancel/` and submits itself. Your browser would send your session
cookie along, and the event would be cancelled in your name: a **cross-site request forgery**.
Django's `CsrfViewMiddleware` stops it: every POST must carry a secret token that only pages from
our own site contain. `{% csrf_token %}` writes it into the form as a hidden field. Forget it,
and your own form gets a 403.

## A Django form does three jobs

A `forms.Form` (or a `ModelForm`, built from a model's fields):

1. **renders** the inputs, with labels (`{{ form }}`);
2. **validates and cleans** the values the browser sent: `form.is_valid()`, then
   `form.cleaned_data` holds Python values (an `int`, a `datetime`, a `Country`);
3. **shows the errors** next to the fields when something is wrong.

A form built with data (`ProfileForm(request.POST, ...)`) is **bound**; without
(`ProfileForm()`) it is **unbound** and just shows empty or pre-filled inputs.

## The view pattern of every form page

```python
def profile_edit(request: HttpRequest) -> HttpResponse:
    user = ...  # who is asking, checked first (404 for the wrong person)
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile is saved.")
            return redirect("student_detail", pk=user.pk)
    else:
        form = ProfileForm(instance=user)
    return render(request, "accounts/profile_form.html", {"form": form})
```

Three paths through it:

- **GET**: an unbound form, status 200.
- **POST with errors**: the *bound* form is rendered again, status 200, with what the user typed
  and the error messages. Nothing was saved.
- **POST that works**: do the work (here `form.save()`; elsewhere a service), add a message,
  **redirect** (302).

## Post/Redirect/Get

Why redirect instead of rendering a page after a successful POST? Because the page on screen
would be the answer to a POST, and pressing reload would send the POST again: a second event, a
second join. With a redirect the browser makes a fresh GET, and reload repeats only that GET:

```
POST /events/new/      → 302, Location: /
GET  /                 → 200, "Sent to AMFI for review."
```

The message survives the redirect because `django.contrib.messages` stores it until the next
page shows it; `base.html` prints it once.

## When a rule says no

Services raise `ValidationError` when a rule is broken (AGENTS.md). The view shows it:

- on a **button** (join, leave, cancel): `messages.error(...)` and redirect back to the page;
- on a **form page**: add it to the form (`form.add_error(None, error)`) and render the page
  again with status 200.

## Files

A form with a file needs `enctype="multipart/form-data"` on the `<form>` tag, and the view must
pass `request.FILES` to the form. Without either, the photo never arrives and the form says
"This field is required."

## The server decides

A page can be minutes old when its button is pressed: someone else took the last spot, the event
started. So the view and the service check everything again when the POST arrives. The HTML
only *offers* actions; it never *decides* (and neither does JavaScript: AGENTS.md).

## Further reading

- [hypermedia.systems, "Hypermedia: A Reintroduction"](https://hypermedia.systems/hypermedia-a-reintroduction/):
  links and forms as the controls of an app, and where this style fits. Free online.
- [hypermedia.systems, "A Web 1.0 Application"](https://hypermedia.systems/a-web-1-0-application/):
  a small app built exactly this way, with Post/Redirect/Get and flash messages (in Flask, but
  the pattern is ours). The later chapters add htmx, which we don't use.
- [MDN: Sending form data](https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Forms/Sending_and_retrieving_form_data):
  what the browser actually sends for GET, POST and files.
- [Django: Working with forms](https://docs.djangoproject.com/en/6.1/topics/forms/) and
  [Django tutorial, part 4](https://docs.djangoproject.com/en/6.1/intro/tutorial04/) (a first
  form, `{% csrf_token %}`, and why to redirect after a POST).
- [MDN: Django tutorial part 9, Working with forms](https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Server-side/Django/Forms):
  the same pattern with a flowchart. (Its later sections use class-based views; we don't.)
- [MDN: Cross-site request forgery (CSRF)](https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/CSRF)
  and [Django: CSRF protection](https://docs.djangoproject.com/en/6.1/ref/csrf/).
- [MDN: Safe HTTP methods](https://developer.mozilla.org/en-US/docs/Glossary/Safe/HTTP): why a
  GET must never change anything.
