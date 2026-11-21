# Deploy to your own VPS with Dokku

This guide takes you from nothing to a running AMFI Meetups site on your own server. You
order a small VPS, install [Dokku](https://dokku.com/), and deploy with `git push`.

Placeholders used below. Replace them everywhere, without the angle brackets:

| Placeholder | Meaning |
|---|---|
| `<VPS_IP>` | the IPv4 address of your VPS, from the OVHcloud panel |
| `<SSH_USER>` | the login user of the VPS; OVH's Ubuntu image uses `ubuntu` |
| `<APP>` | the app name; use `amfi-meetups` (lowercase letters, digits, hyphens) |
| `<DOMAIN>` | the host name of your site; by default `<APP>.<VPS_IP>.nip.io` |
| `<YOUR_EMAIL>` | your real email address (Let's Encrypt needs it) |

Commands marked "laptop" run on your own computer. All others run on the server, after you
log in with SSH. On Windows, use Git Bash (it comes with Git for Windows) or WSL for the laptop
commands.

Other notes: [backups.md](backups.md).

## 1. Order the VPS

1. Order an OVHcloud VPS with Ubuntu LTS. The smallest plan is enough.
2. Pick a location in the EU: the database holds students' personal data.
3. Make sure the VPS has an IPv4 address. The image build downloads a tool from GitHub, which
   has no IPv6.
4. If the order form asks for an SSH public key, add yours (part 2 shows how to make one).

Check: the OVH panel shows your VPS as running, with an IPv4 address. That is `<VPS_IP>`.

## 2. Make an SSH key and log in

An SSH key is a pair of files: a private key that stays on your laptop, and a public key you
give to servers. The server lets in whoever holds the matching private key. This is safer than a
password.

Skip the first command if you already have `~/.ssh/id_ed25519.pub`.

```sh
ssh-keygen -t ed25519 -C "<YOUR_EMAIL>"   # laptop; press Enter to accept the defaults
cat ~/.ssh/id_ed25519.pub                 # laptop; this is the public key
```

If you did not add the key in the order form, copy it to the server now. It asks for the
password OVH emailed you.

```sh
ssh-copy-id -i ~/.ssh/id_ed25519.pub <SSH_USER>@<VPS_IP>   # laptop
```

Log in:

```sh
ssh <SSH_USER>@<VPS_IP>   # laptop
```

Check: the prompt changes to `<SSH_USER>@vps-...:~$`. The first time, SSH asks if you trust the
host: type `yes`.

Windows note: `ssh-keygen` and `ssh` also work in PowerShell, but `ssh-copy-id` does not. Use
Git Bash or WSL for it.

## 3. Update the server and allow SSH keys only

Bots try passwords on every public server all day. Turn password login off so only your key
works. First update the system and reboot:

```sh
sudo apt update && sudo apt full-upgrade -y && sudo reboot
```

Wait a minute, log in again, then write the SSH setting:

```sh
printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\n' \
  | sudo tee /etc/ssh/sshd_config.d/00-keys-only.conf
sudo sshd -t && sudo systemctl reload ssh
```

The file name starts with `00` on purpose: SSH keeps the first value it reads, and the image
has another file that turns passwords on.

Check: keep this session open. In a second terminal, `ssh <SSH_USER>@<VPS_IP>` still works, and
`ssh -o PubkeyAuthentication=no <SSH_USER>@<VPS_IP>` is refused with `Permission denied`. If
the first fails, fix it from the open session before you close it.

## 4. Firewall

A firewall blocks every port you do not need. You need SSH (22), HTTP (80) and HTTPS (443).

```sh
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw enable
```

Check: `sudo ufw status` lists OpenSSH, 80/tcp and 443/tcp as ALLOW.

## 5. Install Dokku

Dokku is a small platform on your server: it receives a `git push`, builds a Docker image from
your `Dockerfile`, starts it, and puts nginx in front. It has no web interface of its own. The
install script also installs Docker.

Look up the current version on [Dokku's install page](https://dokku.com/docs/getting-started/installation/)
and use it instead of `v0.38.31` if there is a newer one.

```sh
wget -NP . https://dokku.com/install/v0.38.31/bootstrap.sh
sudo DOKKU_TAG=v0.38.31 bash bootstrap.sh
```

This takes a few minutes.

Check: `dokku version` prints a version number.

## 6. Let Dokku know your key

`git push` to Dokku uses SSH too. Dokku needs your public key to accept your pushes.

```sh
cat ~/.ssh/id_ed25519.pub | ssh <SSH_USER>@<VPS_IP> sudo dokku ssh-keys:add admin   # laptop
```

Check: on the server, `sudo dokku ssh-keys:list` shows a key named `admin`.

## 7. Domain and HTTPS plugin

Your site needs a host name. [nip.io](https://nip.io/) is a free service that turns
`anything.<VPS_IP>.nip.io` into `<VPS_IP>`, so you need no DNS setup. Your `<DOMAIN>` is then
`<APP>.<VPS_IP>.nip.io`, for example `amfi-meetups.<VPS_IP>.nip.io`.

Own domain instead? At your DNS provider, add an A record from the name you want (for example
`meetups.example.com`) to `<VPS_IP>`, and use that name as `<DOMAIN>` everywhere below.

Install the Let's Encrypt plugin. It gets a free HTTPS certificate and renews it.

```sh
sudo dokku plugin:install https://github.com/dokku/dokku-letsencrypt.git
sudo dokku letsencrypt:set --global email <YOUR_EMAIL>
sudo dokku letsencrypt:cron-job --add
```

Use a real email address: Let's Encrypt refuses the account otherwise (`invalidContact`). The
cron job renews certificates automatically.

Check: `sudo dokku plugin:list` shows `letsencrypt`.

## 8. Create the app and its storage

```sh
sudo dokku apps:create <APP>
sudo dokku storage:ensure-directory --chown heroku <APP>
sudo dokku storage:mount <APP> /var/lib/dokku/data/storage/<APP>:/app/var
sudo dokku domains:set <APP> <DOMAIN>
sudo dokku nginx:set <APP> client-max-body-size 10m
```

Why:

- `apps:create` comes first: the other commands need the app to exist.
- The container is thrown away on every deploy, and so is everything inside it. The SQLite
  database lives in `var/`, so `storage:mount` maps the server directory
  `/var/lib/dokku/data/storage/<APP>` to `/app/var` in the container. The data survives deploys.
- `--chown heroku` gives that directory to user id 1000, the user the container runs as. Without
  it SQLite cannot create its files and the deploy fails in the `release` step.
- Uploaded photos are stored in `var/media/`, inside the same mount, so they survive deploys
  too. The app serves them itself, to logged-in users only.
- `client-max-body-size 10m`: nginx refuses requests bigger than 1 MB by default, and a phone
  photo is 3–8 MB. Without it, registration fails with `413 Request Entity Too Large`.

Check: `sudo dokku storage:report <APP>` shows the mount, `sudo dokku domains:report <APP>`
shows `<DOMAIN>`, and `sudo dokku nginx:report <APP>` shows `client-max-body-size` `10m`.

## 9. Environment variables

The app reads its settings from environment variables (the full list is in SPEC.md section 9).
On Dokku you set them with `dokku config:set`. They are stored on the server, never in git.

```sh
sudo dokku config:set --no-restart <APP> \
  DJANGO_DEBUG=false DJANGO_HTTPS=true DJANGO_TIME_ZONE=Europe/Rome \
  DJANGO_ALLOWED_HOSTS=<DOMAIN>,localhost DJANGO_SITE_URL=https://<DOMAIN> \
  DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')" >/dev/null
```

Why each one:

- `DJANGO_DEBUG=false`: debug mode shows secrets in error pages. Production must have it off.
- `DJANGO_HTTPS=true`: HTTPS ends at nginx, and nginx talks plain HTTP to your app. This tells
  Django to trust nginx's header, and turns on secure cookies. Without it every login fails
  with a 403 (CSRF check).
- `DJANGO_SITE_URL`: the start of every link in emails and in the registration QR code. Emails
  are sent without a browser request, so the app can't guess its own address.
- `DJANGO_ALLOWED_HOSTS`: the host names Django answers to. `localhost` is for Dokku's
  healthcheck (`app.json`), which sends `Host: localhost`. Without it the check gets a 400 and
  the deploy stops.
- `DJANGO_SECRET_KEY`: Django signs sessions and tokens with it. The command makes a random one
  on the server. `>/dev/null` hides the output, because `config:set` prints every value.
- `DJANGO_DB_PATH`: leave it unset. The default `var/db.sqlite3` is inside the storage mount.
- `--no-restart`: there is nothing to restart yet.

### Email

The app sends verification links, password resets and notifications by email. Production uses Brevo's SMTP relay. Set
the `EMAIL_*` values from your Brevo account (their SMTP page shows the login and the key). Do
not set `EMAIL_BACKEND`: the default sends real mail.

```sh
sudo dokku config:set --no-restart <APP> \
  EMAIL_HOST=smtp-relay.brevo.com EMAIL_PORT=587 EMAIL_USE_TLS=true \
  EMAIL_HOST_USER=<your Brevo SMTP login> EMAIL_HOST_PASSWORD=<your Brevo SMTP key> \
  DJANGO_DEFAULT_FROM_EMAIL='AMFI Meetups <<your verified sender address>>' >/dev/null
```

`DJANGO_DEFAULT_FROM_EMAIL` is the sender of every email. Its address must be verified in Brevo
(Senders), or Brevo drops the mail. Test it with
`sudo dokku run <APP> python manage.py sendtestemail <YOUR_EMAIL>`. Without
`EMAIL_HOST` the app tries an SMTP server on `localhost`, and no mail arrives.

Start the line with a space if it has a password: Ubuntu's bash then keeps it out of the
history. Put a value in single quotes if it has spaces or `$`, `!` or `&`.

Check: `sudo dokku config:keys <APP>` lists the names (not the values) you set.

Later you can change one value with `sudo dokku config:set <APP> KEY=value`. That restarts the
app. `config:show <APP>` prints all values, secrets included, so do not paste its output in
chat or issues.

## 10. First deploy

On your laptop, in your project folder, add the Dokku server as a git remote and push:

```sh
git remote add dokku dokku@<VPS_IP>:<APP>   # laptop; if it exists: git remote set-url dokku ...
git push dokku main:master                  # laptop
```

Dokku deploys its `master` branch, so `main:master` pushes your local `main` to it. Only
committed files are deployed: commit first.

What happens, in order, and you see it in the push output:

1. The image is built from the `Dockerfile` (dependencies, the Tailwind stylesheet,
   `collectstatic`).
2. The `release` line of the `Procfile` runs `python manage.py migrate`. If it fails, the deploy
   stops and the old version keeps running.
3. The `web` line starts gunicorn. Dokku asks `/accounts/login/` for an answer (the healthcheck
   in `app.json`). If it does not answer, the old version keeps running.
4. nginx sends traffic to the new container.

The static files (CSS, JS) are served by the app itself, with WhiteNoise. No extra setup.

Check: the push ends with a line like `http://<DOMAIN>`, and
`sudo dokku ps:report <APP>` shows `Status web 1 ... running`. Opening `http://<DOMAIN>` shows
the login page. Do not log in yet: HTTPS comes next, and logging in over plain HTTP fails.

## 11. HTTPS

```sh
sudo dokku letsencrypt:enable <APP>
```

Let's Encrypt calls your site on port 80 to check that you own the host name. Then Dokku
installs the certificate, and nginx redirects HTTP to HTTPS.

Check (laptop): `curl -sI https://<DOMAIN>/accounts/login/` starts with `HTTP/2 200`, and the
browser shows a lock.

nip.io is shared by many people, and Let's Encrypt allows only 50 new certificates per week for
all of them. If you see `rateLimited`, try again later or use your own domain.

## 12. Create your admin account

```sh
ssh -t <SSH_USER>@<VPS_IP> sudo dokku run <APP> python manage.py createsuperuser   # laptop
```

`dokku run` starts a one-off container of your app, with the same variables and the same
storage mount. `-t` lets you type the answers.

Check: log in at `https://<DOMAIN>/accounts/login/`, then open `/admin/`.

## 13. Redeploy

After you merge a change to `main`, pull a backup first (a bad migration then loses nothing),
then push:

```sh
scripts/pull-backup.sh <VPS_IP> <APP>   # laptop; see backups.md
git push dokku main:master              # laptop
```

Check: the push ends without `remote: ! ...` errors, and the site works. If the `release` or
the healthcheck step fails, the old version keeps serving: read the error above it, fix, push
again.

## 14. Logs and status

```sh
sudo dokku logs <APP> --tail         # live app log; Ctrl+C to stop
sudo dokku logs <APP> -n 100         # the last 100 lines
sudo dokku ps:report <APP>           # is it running?
sudo dokku ps:restart <APP>          # restart without a new build
```

## 15. Optional: limit login attempts

Django does not slow down someone who guesses passwords. This step makes nginx allow 5 login
attempts a minute per address (a burst of 5 more, then HTTP 429). It also turns off nginx's own
HSTS header, so responses carry only Django's.

```sh
ssh <SSH_USER>@<VPS_IP> 'bash -s -- <APP>' < scripts/server/nginx-login-limit.sh   # laptop
```

`bash -s` runs the script that arrives on standard input, so nothing is copied to the server.
Run it after `apps:create`. It is safe to run twice.

Check (laptop): send eight wrong logins quickly. The first ones answer `403` (the CSRF token is
missing, which is fine for this test) and the later ones `429`:

```sh
for i in 1 2 3 4 5 6 7 8; do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST https://<DOMAIN>/accounts/login/
done
```

## 16. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Login fails with 403 (CSRF), or the login page loads but cookies do not stick | `DJANGO_HTTPS` is not `true`, or HTTPS is not enabled yet (part 11). |
| Healthcheck fails with a 400 | `localhost` is missing from `DJANGO_ALLOWED_HOSTS`. |
| Healthcheck fails with `invalid IP` | The container exited at start. Read `sudo dokku logs <APP>`. Check that `Procfile` is committed: the `Dockerfile` has no `CMD`. |
| `release` fails with a database error ("unable to open database file", "readonly") | The storage directory has the wrong owner. Run `sudo dokku storage:ensure-directory --chown heroku <APP>` and deploy again. |
| `domains:set` or `storage:mount` says the app does not exist | Run `sudo dokku apps:create <APP>` first. |
| The app does not start after `config:set`, and you typed a wrong value | Check with `sudo dokku run <APP> python manage.py check --deploy`, fix with `config:set`. |
| `letsencrypt:enable` says `invalidContact` | The global email is not a real address. Run `letsencrypt:set --global email <YOUR_EMAIL>` again. |
| `letsencrypt:enable` says `rateLimited` | nip.io is shared; wait, or use your own domain. |
| No emails arrive | `EMAIL_HOST` and the account are not set, or the sender address is not verified in Brevo. Read the app log for the SMTP error. |
| `git push` asks for a password or says `Permission denied (publickey)` | Part 6 was skipped, or you used the wrong key. Check `sudo dokku ssh-keys:list`. |
| Build fails while downloading the Tailwind CLI | The VPS has no IPv4, or GitHub was unreachable. Push again. |
| `git push` says the remote branch does not exist or nothing is deployed | Push `main:master`, not `main`. |
| Uploading a photo fails with `413 Request Entity Too Large` | The upload limit was not raised: run `sudo dokku nginx:set <APP> client-max-body-size 10m` and `sudo dokku proxy:build-config <APP>`. |
| `nginx -t` fails in part 15 | Another file already defines the same zone name. Use a different `<APP>` per app on one server. |

## References

- Dokku: [installation](https://dokku.com/docs/getting-started/installation/),
  [deployment](https://dokku.com/docs/deployment/application-deployment/),
  [zero-downtime deploys and checks](https://dokku.com/docs/deployment/zero-downtime-deploys/),
  [deployment tasks (`release`)](https://dokku.com/docs/advanced-usage/deployment-tasks/),
  [persistent storage](https://dokku.com/docs/advanced-usage/persistent-storage/),
  [dokku-letsencrypt](https://github.com/dokku/dokku-letsencrypt)
- Django: [deployment checklist](https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/)
