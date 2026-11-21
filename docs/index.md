# Notes

Short notes for future developers and agents. Read this index first, then the notes that match
your task.

## Plan (the students' starting point)

- [App plan](app-plan.md): the students' list of requirements, 1–37. SPEC.md supersedes it.
- [Flow diagram](<Untitled (1).png>): organizer → review → event list → meetup, and "My events".
- [Desktop wireframe](wireframe-desktop.svg) and [mobile wireframe](wireframe-mobile.svg): the
  event list with filters, cards, spots and the Join / Join Waiting List / Not approved states.

## Deployment (your own VPS with Dokku)

- [Deploy to Dokku](deployment/deploy-to-dokku.md): from ordering an OVHcloud VPS to a running
  site with HTTPS, step by step with the why; environment variables, Brevo email, redeploys,
  logs, troubleshooting.
- [Backups](deployment/backups.md): pull a copy of the database with `scripts/pull-backup.sh`,
  restore it.

## Typing

- [Custom QuerySets and pyrefly](typing/custom-querysets.md): the one-line `objects` declaration
  that keeps custom QuerySet methods typed.

## Testing

- Static files in tests](testing/static-files.md): why tests use plain static storage, and why
  `assets/static/.gitkeep` exists.
