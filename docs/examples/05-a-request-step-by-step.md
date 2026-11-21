# 05. One registration, request by request: POST, 302, GET, and a 403

You register a made-up student and watch every request the browser makes: the POST, the
**302** redirect, the GET that follows, the cookies that log you in, and the message that
survives the redirect. Then you remove `{% csrf_token %}` and get the **403**. After this,
Post/Redirect/Get and CSRF are things you have seen, not rules you were told.

Do it after issue 008, step 4 (the pages exist). Takes 20 minutes. Issue 010's "Create" form
works the same way: repeat part 2 with it (Try this).

## Setup

- `uv run python manage.py runserver` in one terminal.
- `.env` uses the file email backend (it does after `cp .env.example .env`): emails become files
  in `var/mail/`.
- An open registration window: in the admin, "Add registration window", Save, and copy the
  **code** at the end of its link (`/register/<CODE>/`). In the commands below, replace
  `<CODE>` with it.
- A small photo: `uv run python -c "from PIL import Image; Image.new('RGB', (600, 800), 'teal').save('var/selfie.jpg')"`.

The output below is from a real run; your code, tokens, ids and dates will differ.

## Part 1: in the browser

1. Open a private window, then the developer tools (F12, or right-click → Inspect), tab
   **Network**. Tick **Preserve log**, so the list isn't emptied when the page changes.
2. Open `http://127.0.0.1:8000/register/<CODE>/`, fill in the form as "Student 2",
   `student2@example.com`, with `var/selfie.jpg`, and press Register.
3. In the list you'll see two rows: `<CODE>/` with method POST and status **302**, then
   `sent/` with GET and **200**. Click the POST row: under Headers, the response has
   `Location: /register/sent/`; under Payload, the fields you typed and `csrfmiddlewaretoken`.

That is the whole trip. Part 2 does it again with `curl`, where every header is printed.

## Part 2: the same trip with `curl -i`

`-i` prints the response headers, `-c` saves cookies to a file and `-b` sends them back, like a
browser does. This time it is "Student 1", typed with capitals as a phone would.

### 1. GET the form

```sh
curl -s -i -c var/cookies.txt http://127.0.0.1:8000/register/<CODE>/ > var/page.html
head -14 var/page.html
grep -o 'name="csrfmiddlewaretoken" value="[^"]*"' var/page.html
```

```text
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
...
Set-Cookie: csrftoken=7cLXMEwgYMXal64FVvgYG41xwGzpxsmK; expires=Sat, 20 Nov 2027 02:11:05 GMT; Max-Age=31449600; Path=/; SameSite=Lax

name="csrfmiddlewaretoken" value="7p9xcJe5itEK1Xczhb1UcSnXWelz3o7A4rKkOdAb65rKcT642w7IIMekiKKOqGja"
```

### 2. POST it, with the token and the photo

```sh
TOKEN=$(grep -o 'name="csrfmiddlewaretoken" value="[^"]*"' var/page.html | sed 's/.*value="//; s/"$//')
curl -i -b var/cookies.txt -c var/cookies.txt \
  -F csrfmiddlewaretoken=$TOKEN -F full_name="Student 1" -F email=Student1@Example.com \
  -F password1=a-long-pass-123 -F password2=a-long-pass-123 \
  -F photo=@var/selfie.jpg -F nationality=ES -F age=22 -F gender=female \
  http://127.0.0.1:8000/register/<CODE>/
```

```text
HTTP/1.1 302 Found
Content-Type: text/html; charset=utf-8
Location: /register/sent/
Content-Length: 0
```

With `-v` instead of `-i` you also see what curl sent:
`> Cookie: csrftoken=…` and `> Content-Type: multipart/form-data; boundary=…`.

### 3. Follow the redirect, as the browser did

```sh
curl -i -b var/cookies.txt http://127.0.0.1:8000/register/sent/
```

```text
HTTP/1.1 200 OK
...
  <p>Check your email. We sent you a link: open it to activate your account.</p>
```

### 4. The email

```sh
ls -t var/mail/ | head -1                    # the newest file
cat "var/mail/$(ls -t var/mail/ | head -1)"
```

```text
20261121-031111-4467032816.log
Subject: Confirm your email for AMFI Meetups
From: webmaster@localhost
To: student1@example.com
...
Welcome to AMFI Meetups! Open this link to confirm your email and activate yo=
ur
account:

http://127.0.0.1:8000/verify/Mg/didi6n-2d5017b868f0a1c43bfee2beb28e5c37/
```

(`yo=` + `ur`: the file is "quoted-printable", where `=` at the end of a line means "the line
goes on". A mail program joins them.)

### 5. Open the link

```sh
curl -i -b var/cookies.txt -c var/cookies.txt http://127.0.0.1:8000/verify/Mg/didi6n-2d5017b868f0a1c43bfee2beb28e5c37/
```

```text
HTTP/1.1 302 Found
Location: /
Set-Cookie: messages=W1siX19qc29uX21lc3NhZ2UiLDAsMjUsIllvdXIgZW1haWwgaXMgdmVyaWZpZWQuIFdlbGNvbWUgdG8gQU1GSSBNZWV0dXBzISIsIiJdXQ:1xUaZR:T5x4…; HttpOnly; Path=/; SameSite=Lax
Set-Cookie: csrftoken=O81KJVviZaa4ij4LV5OpSsa2cEahXXZ8; ...
Set-Cookie: sessionid=padjtu2xakxj3o4e34n09nn256nedxr1; expires=Sat, 05 Dec 2026 02:11:17 GMT; HttpOnly; Max-Age=1209600; Path=/; SameSite=Lax
```

### 6. The page after the redirect

```sh
curl -i -b var/cookies.txt -c var/cookies.txt http://127.0.0.1:8000/
```

```text
HTTP/1.1 200 OK
Set-Cookie: messages=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/; SameSite=Lax
...
      <span class="text-sm opacity-70">student1@example.com</span>
    <div class="alert alert-success">Your email is verified. Welcome to AMFI Meetups!</div>
```

Run step 5's command again, without `-b` (a stranger, or you after logging out): `200 OK` and
"This link doesn't work. It was already used, or it is too old."

## Part 3: forget `{% csrf_token %}`

Delete the `{% csrf_token %}` line from `accounts/templates/accounts/register.html`. Repeat steps
1 and 2 of part 2 (with a new email; `TOKEN` is now empty: the page has no token to find).

```text
HTTP/1.1 403 Forbidden
...
  <p>CSRF verification failed. Request aborted.</p>
...
    <p>Reason given for failure:</p>
    <pre>
    CSRF token missing.
    </pre>
```

`runserver`'s terminal says `Forbidden (CSRF token missing.): /register/<CODE>/`. In a fresh
private window the reason is `CSRF cookie not set.` instead: the cookie, too, is only set by a
page that uses `{% csrf_token %}`. **Put the line back.**

## What just happened

- **POST → 302 → GET** is Post/Redirect/Get. The POST's answer is empty, with a `Location`; the
  browser then GETs that page on its own. Reloading "Check your email" repeats only the GET, so
  nobody registers twice (`hypermedia-and-forms.md`).
- **`-F` sends `multipart/form-data`**, the encoding a form with `enctype="multipart/form-data"`
  uses. The photo travels in the body as a file; Django puts it in `request.FILES`. The email
  arrived as `student1@example.com`: the form lowercased it.
- **The CSRF token comes twice**: in a cookie (`csrftoken`) and in the form. Django checks that
  they belong together. The form's value is longer and different on every page (it is the
  cookie's secret, masked), and it still matches. Another website can make your browser POST to
  us, but it can't read the token inside our page, so its forged POST gets the 403.
- **`sessionid` is the login.** The verify view called `login()`; Django saved a session in the
  database and gave the browser its key. Every later request sends it back, and the middleware
  turns it into `request.user` (`how-a-django-request-works.md`). Django also changes
  `csrftoken` at login.
- **The message travelled in a cookie.** `messages` holds the text, signed: copy the part
  before the first `:`, add `==`, and `echo 'W1si…XQ==' | base64 -d` prints
  `[["__json_message",0,25,"Your email is verified. Welcome to AMFI Meetups!",""]]`. The next
  page shows it and deletes the cookie (`Max-Age=0`): that's how a message survives exactly one
  redirect.

## Try this

1. After issue 010, do part 2 for `/events/new/` (log in first by POSTing `username`,
   `password` and the token to `/accounts/login/`). The page has a second token, in the
   "Log out" form: add `| head -1` after the `grep`. The POST answers `302`, `Location: /`, and
   the next page says "Sent to AMFI for review."
2. POST the registration form again with a new email and the password `12345678`: no redirect
   this time, but `200 OK` and the same page with "This password is too common." and "This
   password is entirely numeric.": the "errors" path of the view.
3. In the browser, click a POST row and choose "Copy as cURL": your browser's request, as a
   command like the ones above.

## Belongs to

- [Issue 008](../../issues/008-registration-and-verification.md) (registration, verification,
  messages) and [issue 010](../../issues/010-create-an-event.md) (the same pattern for events).
- [How a Django request works](../learn/how-a-django-request-works.md) and
  [Hypermedia and forms](../learn/hypermedia-and-forms.md) (CSRF, Post/Redirect/Get).
