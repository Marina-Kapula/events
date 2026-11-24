# Deploy to Render (free plan)

A free way to show the site online. The course's main deploy is Dokku on a server
(`deploy-to-dokku.md`); this is the quick alternative.

Render's free plan has three limits, and the project works around each:

| Limit on the free plan | What we do |
|---|---|
| The disk is wiped on each restart and deploy | The data lives in Render's free **Postgres** (`DATABASE_URL`), and the photos too, in the database (`DJANGO_MEDIA_IN_DB=true`, `files/storage.py`). |
| The SMTP ports (25, 465, 587) are blocked | Email goes through **Brevo's HTTPS API** (`EMAIL_BACKEND=config.brevo.BrevoEmailBackend`, `BREVO_API_KEY`). |
| No shell, no pre-deploy step | Each start runs `migrate`, then `ensure_admin`, which creates the admin from `DJANGO_ADMIN_EMAIL` and `DJANGO_ADMIN_PASSWORD` once. |

Also know:

- The site **sleeps** after 15 minutes without visitors; the first visit after that
  takes about a minute.
- Render's **free Postgres expires 30 days** after you create it. Before then, upgrade it
  or make a new one (the data in the old one is lost).

## Steps

1. In Brevo: **SMTP & API → API keys → Generate a new API key**. Copy it into your
   password manager only. Check the sender email is verified in **Senders**.
2. In Render: **New → Blueprint**, pick this GitHub repository. Render reads
   `render.yaml` and creates the web service and the database.
3. It asks for the values marked `sync: false`:

   | Variable | Value |
   |---|---|
   | `DJANGO_ALLOWED_HOSTS` | `amfi-meetups.onrender.com` (your service's address) |
   | `DJANGO_SITE_URL` | `https://amfi-meetups.onrender.com` |
   | `DJANGO_DEFAULT_FROM_EMAIL` | `AMFI Meetups <your-verified-sender@example.com>` |
   | `BREVO_API_KEY` | the key from step 1 |
   | `DJANGO_ADMIN_EMAIL` | your admin email |
   | `DJANGO_ADMIN_PASSWORD` | a long new password, kept in your password manager |

4. **Apply**. When the deploy is live, open `https://<your-address>/admin/` and log in.

The real address is shown at the top of the service's page; if it isn't
`amfi-meetups.onrender.com`, fix the first two variables in **Environment** and save.

Never put the API key or the admin password in git, an issue, a chat or `.env.example`.
