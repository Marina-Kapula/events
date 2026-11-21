# Emails in tests

- Services send email in `transaction.on_commit` (AGENTS.md, Django), so nothing is sent if the
  transaction fails.
- pytest-django's `django_db` runs each test inside a transaction that is rolled back at the
  end, so the commit never happens and `on_commit` callbacks never run: `mailoutbox` stays empty.
- Run the callbacks with pytest-django's `django_capture_on_commit_callbacks` fixture:

  ```python
  def test_rejecting_emails_the_organizer(
      mailoutbox, django_capture_on_commit_callbacks, make_event
  ):
      event = make_event(status=Event.Status.PENDING)

      with django_capture_on_commit_callbacks(execute=True):
          event_reject(event=event, reason="The place is missing.")

      assert len(mailoutbox) == 1
      assert "The place is missing." in mailoutbox[0].body
  ```

- `mailoutbox` is pytest-django's list of sent emails (Django's locmem backend, which tests use
  instead of `MAILERS`).
- Further reading: [pytest-django: `django_capture_on_commit_callbacks`](https://pytest-django.readthedocs.io/en/latest/helpers.html#django-capture-on-commit-callbacks),
  [Django: performing actions after commit](https://docs.djangoproject.com/en/6.1/topics/db/transactions/#performing-actions-after-commit).
