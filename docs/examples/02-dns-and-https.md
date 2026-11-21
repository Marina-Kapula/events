# 02. From a name to a lock: DNS and HTTPS with `dig` and `curl -v`

Before a browser shows your site, three things happen: a **name** becomes an IP address (DNS),
a **connection** opens to that address, and, for `https://`, the server proves with a
**certificate** that it really is that name. Here you watch each step on its own, so when the
deploy fails you know *which* step failed instead of staring at "This site can't be reached".

Do steps 1–2 now, on your laptop. Do steps 3–5 during issue 004: step 3 after part 7 of the
deploy guide, step 4 after part 10, step 5 after part 11.

## Setup

- `curl` comes with macOS, Linux and Git Bash on Windows.
- `dig` comes with macOS and most Linux systems. On Windows, use `nslookup <name>` instead: it
  prints the same address in a different layout.
- Your values from issue 004: `<APP>`, `<VPS_IP>`, `<DOMAIN>` (`<APP>.<VPS_IP>.nip.io`). They
  stay in your private notes; the examples below use `192.0.2.10`, an address reserved for
  documentation that belongs to nobody.

## Steps

### 1. Learn to read `curl -v` on your own laptop

Start the server (`uv run python manage.py runserver`), then in a second terminal:

```sh
curl -v http://127.0.0.1:8000/
```

```text
* Connected to 127.0.0.1 (127.0.0.1) port 8000
> GET / HTTP/1.1
> Host: 127.0.0.1:8000
> User-Agent: curl/8.7.1
> Accept: */*
>
< HTTP/1.1 302 Found
< Server: WSGIServer/0.2 CPython/3.14.3
< Location: /accounts/login/?next=/
< Content-Length: 0
< Vary: Cookie
...
```

Lines with `*` are curl telling you what it does, `>` is what it **sent**, `<` is what it
**received**. Note the `Host:` line: the browser always says which name it asked for.

Now pretend to be a browser that asked for your server's name:

```sh
curl -i -H "Host: amfi-meetups.192.0.2.10.nip.io" http://127.0.0.1:8000/accounts/login/
```

```text
HTTP/1.1 400 Bad Request
...
Invalid HTTP_HOST header: 'amfi-meetups.192.0.2.10.nip.io'. You may need to add
'amfi-meetups.192.0.2.10.nip.io' to ALLOWED_HOSTS.
```

Django refuses names that aren't in `DJANGO_ALLOWED_HOSTS`. On the server, the same 400 means
`<DOMAIN>` is missing from that variable (guide, part 9).

### 2. DNS: ask what address a name has

```sh
dig app.192.0.2.10.nip.io
```

```text
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 43152
;; QUESTION SECTION:
;app.192.0.2.10.nip.io.		IN	A

;; ANSWER SECTION:
app.192.0.2.10.nip.io.	3381	IN	A	192.0.2.10

;; Query time: 4 msec
;; SERVER: <your router or provider's resolver>#53
```

Short form, and two more tries:

```sh
dig +short app.192.0.2.10.nip.io        # 192.0.2.10
dig +short anything.192.0.2.10.nip.io   # 192.0.2.10: any name in front works
curl -v http://app.192.0.2.nip.io/      # a typo: only three numbers
```

```text
* Could not resolve host: app.192.0.2.nip.io
```

And a name that resolves, but where no server answers (nobody owns `192.0.2.10`):

```sh
curl -v --max-time 5 http://app.192.0.2.10.nip.io/
```

```text
* Host app.192.0.2.10.nip.io:80 was resolved.
* IPv4: 192.0.2.10
*   Trying 192.0.2.10:80...
* Connection timed out after 5010 milliseconds
```

### 3. Your own name (issue 004, after part 7)

```sh
dig +short <APP>.<VPS_IP>.nip.io     # laptop
```

You'll see exactly `<VPS_IP>`. With your own domain, you'll see the IP from your A record; right
after you add it, it can take a few minutes (the `3381` above is the TTL: how many seconds a
resolver may keep the old answer).

### 4. Plain HTTP to your server (after part 10)

```sh
curl -v http://<DOMAIN>/accounts/login/     # laptop
```

You'll see `* Connected to <DOMAIN> (<VPS_IP>) port 80`, then `< HTTP/1.1 200 OK` and
`< Server: nginx`: nginx answered and passed the request to gunicorn. A `Set-Cookie: csrftoken=…;
Secure` line is why logging in over plain HTTP fails: with `DJANGO_HTTPS=true` the cookie is
only sent back over HTTPS.

### 5. HTTPS and the certificate (after part 11)

```sh
curl -v -o /dev/null https://<DOMAIN>/accounts/login/     # laptop
```

You'll see something like this (these lines come from a real site whose certificate is also from
Let's Encrypt; yours shows your name and dates):

```text
* Connected to <DOMAIN> (<VPS_IP>) port 443
* SSL connection using TLSv1.3 / AEAD-CHACHA20-POLY1305-SHA256
* Server certificate:
*  subject: CN=<DOMAIN>
*  start date: Sep 18 18:13:29 2026 GMT
*  expire date: Dec 17 18:13:28 2026 GMT
*  subjectAltName: host "<DOMAIN>" matched cert's "<DOMAIN>"
*  issuer: C=US; O=Let's Encrypt; CN=YE2
*  SSL certificate verify ok.
< HTTP/2 200
```

And the redirect from HTTP: `curl -sI http://<DOMAIN>/` starts with `HTTP/1.1 301`, with a
`Location:` header that points at `https://<DOMAIN>`.

## What just happened

| Step | Question answered | If it fails, you see | Usual cause |
|---|---|---|---|
| DNS | which IP has this name? | `Could not resolve host` | typo in the name; A record missing or not there yet |
| Connect | does anything answer at that IP and port? | `Connection timed out` / `Connection refused` | VPS off, wrong IP, firewall (part 4); refused on 443: HTTPS not enabled yet (part 11) |
| TLS | is the server really this name? | `SSL: no alternative certificate subject name matches` / `certificate verify failed` | certificate for another name; `letsencrypt:enable` not run for this app |
| HTTP | what does the app say? | `400` (Host), `502` (app down), `500` | `DJANGO_ALLOWED_HOSTS`; `dokku logs <APP>` |

nip.io is a DNS server that reads the IP out of the name you ask for, so it needs no setup. Let's
Encrypt only gives a certificate for a name whose DNS points at the server asking for it: it
calls `http://<DOMAIN>/.well-known/…` on port 80 to check. That's why DNS (step 3) and plain HTTP
(step 4) must work before HTTPS (step 5) can. The certificate is short-lived (90 days in the dates
above); the cron job from part 7 renews it.

## Try this

1. `dig +short NS nip.io` shows which servers answer for nip.io (`ns-00.nip.io.`, …).
   `dig @ns-00.nip.io app.192.0.2.10.nip.io` asks one of them directly: the `aa` flag
   ("authoritative answer") says it comes from the source, not from a cache.
2. Read only the certificate:
   `echo | openssl s_client -connect <DOMAIN>:443 -servername <DOMAIN> 2>/dev/null | openssl x509 -noout -subject -issuer -dates`.
3. In the browser, click the lock (or "Connection is secure") and find the same subject, issuer
   and dates.

## Belongs to

- [Issue 004](../../issues/004-first-deploy.md) and the
  [deploy guide](../deployment/deploy-to-dokku.md), parts 7, 9, 10, 11 and 16 (troubleshooting).
- [How a Django request works](../learn/how-a-django-request-works.md): what happens after the
  connection.
