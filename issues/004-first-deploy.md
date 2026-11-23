# Deploy your copy to your own VPS

Status: done · Opened: 2026-11-21 · Milestone: M1 · Depends on: 002

## Why

"It works on my laptop" isn't done: the app is for students with phones, on the internet. A real
server brings out the problems a laptop hides (HTTPS, cookies, host names, static files,
environment variables, migrations), and it is much easier to meet them now, while the app is
small, than at the end with every feature at once.

Each of you deploys your own copy on your own VPS (SPEC.md §2 #4). From now on every merged issue
is deployed (`docs/workflow/git.md`, step 5), so you see each feature work where it will be used.
Issue 002 comes first on purpose: the server's database must start with the custom user model.

## What you'll build

- A VPS of your own with Dokku, running the current `main` at `https://<DOMAIN>`, with HTTPS.
- Your admin account on the server.
- A first backup of the server's database on your laptop.
- The **Results** section at the end of this issue, filled in.

Not in this issue: email (005; the variables come then), photos (006).

## Before you start

Read:
- `docs/deployment/deploy-to-dokku.md`, **all of it, once, before you type anything**. This issue
  follows it part by part and doesn't repeat its commands.
- `docs/deployment/backups.md`.
- SPEC.md §2 #4; §9 (the environment variables).
- `docs/learn/how-a-django-request-works.md`: the trip of one request, which the big picture below
  spreads over your laptop, nginx, gunicorn and Django.
- [Django: Deployment checklist](https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/):
  what `manage.py check --deploy` checks, and why.

Words you'll meet:
- **Deploy**: put a version of the code on the server and run it.
- **Placeholder**: `<VPS_IP>`, `<APP>`, `<DOMAIN>`, … in the guide. Replace them with your own
  values, without the angle brackets (the table at the top of the guide).
- **Reverse proxy**: a web server (nginx) that receives the browsers' requests and passes them on
  to your app.
- **Healthcheck**: before Dokku sends visitors to a new version, it asks it for a page; no answer,
  no switch.
- **One-off container**: `dokku run <APP> <command>` starts a copy of your app just to run one
  command (`createsuperuser`, `check --deploy`), with the same settings and data.

### The big picture

```
 your laptop                                your VPS (<VPS_IP>)
+----------------+   git push (over SSH)   +-----------------------------------------------+
| the repo, main | ----------------------> | Dokku: builds a Docker image from Dockerfile, |
+----------------+                         | runs `release` (migrate), starts `web`        |
                                           |                                               |
 a phone or a       HTTPS (port 443)       |  nginx  ---- HTTP ---->  container:           |
 browser       ------------------------->  |  (Let's Encrypt         gunicorn + Django     |
                                           |   certificate)           (+ WhiteNoise: CSS)  |
                                           |                              | /app/var       |
                                           |  /var/lib/dokku/data/storage/<APP>/           |
                                           |  db.sqlite3, media/: survive every deploy     |
                                           +-----------------------------------------------+
```

| Piece | What it is | Guide part |
|---|---|---|
| **VPS** | A virtual computer you rent in a data centre: Ubuntu, always on, with a public IP address. Yours alone. | 1 |
| **SSH** | An encrypted login to the server with a key pair instead of a password. `git push` to Dokku travels over it too. | 2, 3, 6 |
| **Firewall** (`ufw`) | Closes every port except SSH (22), HTTP (80) and HTTPS (443). | 4 |
| **Dokku** | A small "Heroku on your own server": it receives `git push`, builds and runs your app, and sets up nginx for it. | 5 |
| **Docker image and container** | The image is your app with Python and every dependency, built from the `Dockerfile`. A container is a running copy of it. On each deploy the old container is thrown away. | 10 |
| **`Procfile`** | Two lines: `release` runs `migrate` before the new version starts; `web` starts gunicorn, the web server that runs Django in production (`runserver` is for development only). | 10 |
| **nginx** | The reverse proxy in front: it speaks HTTPS with browsers, passes requests to gunicorn, and refuses uploads over the size limit. | 8, 11, 15 |
| **Let's Encrypt** | Free HTTPS certificates, renewed automatically. | 7, 11 |
| **Storage mount** | A folder on the server that appears inside the container as `/app/var`: the SQLite database (and later the photos) live there, so they survive deploys. | 8 |
| **Environment variables** | The settings that differ per server (the secret key, the host name, later the email login). Stored on the server with `dokku config:set`, never in git. | 9 |
| **Healthcheck** | `app.json` tells Dokku to ask for `/accounts/login/` before switching; if it fails, the old version keeps running. | 10 |

## Steps

Each part of the guide ends with a **Check**. Don't go on until it passes; most problems later
come from a skipped check. Keep a private note of your values (`<VPS_IP>`, `<APP>`, `<DOMAIN>`):
not in git.

### 1. The server (guide parts 1–4)

Order the VPS (an EU location, with IPv4), make your SSH key, log in, turn off password logins,
and turn on the firewall.

- [ ] Part 1: the VPS runs and has an IPv4 address.
- [ ] Part 2: `ssh <SSH_USER>@<VPS_IP>` logs you in with your key.
- [ ] Part 3: logging in without the key is refused (keep the first session open while you test).
- [ ] Part 4: `sudo ufw status` shows OpenSSH, 80 and 443.

### 2. Dokku (guide parts 5–7)

Install Dokku, give it your public key, and install the Let's Encrypt plugin. Decide your
`<DOMAIN>` here: `<APP>.<VPS_IP>.nip.io` needs no setup.

- [ ] Part 5: `dokku version` prints a version.
- [ ] Part 6: `sudo dokku ssh-keys:list` shows `admin`.
- [ ] Part 7: `sudo dokku plugin:list` shows `letsencrypt`.

### 3. The app, its storage and its settings (guide parts 8–9)

Create the app, the storage mount and the upload limit, then set the environment variables.
Skip the "Email" block of part 9: it needs a Brevo account, which comes in issue 005.
`DJANGO_SITE_URL` is set already now; the emails use it later.

- [ ] Part 8: `storage:report`, `domains:report` and `nginx:report` show what the guide says.
- [ ] Part 9: `sudo dokku config:keys <APP>` includes `DJANGO_DEBUG`, `DJANGO_HTTPS`,
      `DJANGO_TIME_ZONE`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_SITE_URL` and `DJANGO_SECRET_KEY`.

### 4. First deploy and HTTPS (guide parts 10–11)

Push `main` from your laptop and watch the output: the image build, `release` (the migrations,
including `accounts.0001_initial` from issue 002), the healthcheck. Then turn on HTTPS. Don't log
in before HTTPS works: over plain HTTP the login fails with a 403.

- [ ] Part 10: the push ends without `remote: !` errors, and `http://<DOMAIN>` shows the login
      page.
- [ ] Part 11: `https://<DOMAIN>` shows a lock in the browser, and `http://` redirects to it.

### 5. Your admin account (guide part 12)

Since issue 002, `createsuperuser` asks for an **email**, a **full name** and a password. Use a
strong password: this account can see every student's data.

Then let Django check the production settings from inside the server:

```sh
ssh -t <SSH_USER>@<VPS_IP> sudo dokku run <APP> python manage.py check --deploy   # laptop
```

- [ ] You log in at `https://<DOMAIN>/accounts/login/` with your email, and `/admin/` shows the
      Users page.
- [ ] `check --deploy` says "System check identified no issues (2 silenced)".

### 6. Your first backup (guide part 13, `backups.md`)

From now on you pull a backup before every deploy. Do the first one now, so you know it works
before you need it:

```sh
scripts/pull-backup.sh <VPS_IP> <APP>   # laptop
```

- [ ] `~/dokku-backups/<APP>/` has a database file that isn't empty.

### 7. Optional: limit login attempts (guide part 15)

Worth doing on a public server: it slows down anyone guessing passwords.

- [ ] Eight quick wrong logins: the last ones answer `429`.

### 8. Write down what happened

Fill in **Results** below. Problems you met are the most useful part: the next person (and the
next class) will meet them too. If a step of the guide was wrong or unclear, fix the guide in
this branch.

- [ ] Results filled in.

## Done when

- [ ] `https://<DOMAIN>` shows the login page with a valid certificate, and `http://` redirects
      to it.
- [ ] You can log in with your admin email and open `/admin/`.
- [ ] `sudo dokku ps:report <APP>` shows the app running, and `check --deploy` finds no issues.
- [ ] A backup of the database is on your laptop.
- [ ] Results are filled in, and any fix to the guide is in this branch.
- [ ] This issue's tasks are ticked and its `Status:` line says done.

## Git

You deploy `main` as it is; this branch only holds the Results and any fixes to the guide.

```sh
git switch main && git pull
git switch -c 004-first-deploy
```

Suggested commits:
1. `Fix <what> in the deploy guide` (one per fix, if any)
2. `Close 004 with the deploy results`

Open a pull request titled "Deploy your copy to your own VPS". The reviewer opens your URL and
checks the lock (they can't log in, and don't need to), and reads your problems: did they meet
the same ones? `docs/workflow/git.md` has every step.

## Watch out

- **Never paste secrets**: not in Results, the PR, a chat or a screenshot. `dokku config:show`
  prints every value, the secret key included; `config:keys` prints only the names.
- **`git push dokku main:master`**, not `main`: Dokku deploys its `master` branch.
- **Only committed files are deployed.** A change you didn't commit isn't on the server.
- **Keep an SSH session open** while you change the SSH settings (part 3). If you lock yourself
  out, OVH's panel has a rescue console, but it's slow going.
- **If you deployed the skeleton before issue 002**, the server's database has Django's old user
  table: delete it as issue 002, step 4, says, then deploy again.
- **The server holds personal data** once students register: the EU location, the backups on an
  encrypted disk, and no copies in git (`backups.md`).
- **The VPS costs money every month.** Note when the course ends, and cancel it in the OVH panel
  if you don't keep it.
- **Stuck?** The troubleshooting table at the end of the guide lists the usual errors. Then
  `sudo dokku logs <APP> -n 100` shows what the app said.

## Worked example

- [02, DNS and HTTPS with `dig` and `curl -v`](../docs/examples/02-dns-and-https.md): its steps
  1–2 before you start; step 3 after guide part 7, step 4 after part 10, step 5 after part 11.

## Further reading

- Dokku: [deployment](https://dokku.com/docs/deployment/application-deployment/),
  [persistent storage](https://dokku.com/docs/advanced-usage/persistent-storage/),
  [deployment tasks (`release`)](https://dokku.com/docs/advanced-usage/deployment-tasks/),
  [zero-downtime deploys and checks](https://dokku.com/docs/deployment/zero-downtime-deploys/).
- [Django: Deployment checklist](https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/)
  and [How to deploy static files](https://docs.djangoproject.com/en/6.1/howto/static-files/deployment/).
- [Docker: What is a container?](https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-a-container/)
- [The Twelve-Factor App: Config](https://12factor.net/config): why settings live in environment
  variables.
- [How HTTPS works](https://howhttps.works/), a short illustrated explanation.
- [MDN: What is a domain name?](https://developer.mozilla.org/en-US/docs/Learn_web_development/Howto/Web_mechanics/What_is_a_domain_name):
  how a name like `<DOMAIN>` becomes your VPS's IP address (DNS).
- [nip.io](https://nip.io/): why `<APP>.<VPS_IP>.nip.io` reaches your server without buying a
  domain.
- [Let's Encrypt: How it works](https://letsencrypt.org/how-it-works/): how it checks that the
  domain points at your server before it hands out a certificate.
- [The Missing Semester: Command-line Environment](https://missing.csail.mit.edu/2020/command-line/),
  section "Remote Machines": SSH, key pairs, `ssh-copy-id` and `~/.ssh/config`, for beginners.
- [MDN: What is a web server?](https://developer.mozilla.org/en-US/docs/Learn_web_development/Howto/Web_mechanics/What_is_a_web_server):
  a static web server versus a dynamic one (nginx in front, gunicorn and Django behind).
- Julia Evans: [life of a DNS query](https://wizardzines.com/comics/life-of-a-dns-query/), one
  comic page.

## Results

Fill this in when you are done. No passwords, keys or `config:show` output.

- URL: `https://…`
- Deployed on: YYYY-MM-DD, commit `…` (`git rev-parse --short HEAD`)
- VPS: plan, data centre location
- Time it took, roughly:
- Problems met, and how you solved them:
  1. …
- What you changed in the guide (if anything):
