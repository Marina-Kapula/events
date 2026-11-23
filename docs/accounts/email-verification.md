# Email verification links

How `/verify/<uidb64>/<token>/` works (`accounts/services.py`, issue 008).

- **The token is Django's password reset token** (`default_token_generator`). It is a time stamp
  plus a hash of the user's id, password hash, `last_login` and email, signed with `SECRET_KEY`.
  Nothing is stored in the database.
- **It expires** after `PASSWORD_RESET_TIMEOUT` (3 days by default), or when any of the hashed
  values changes. Changing `SECRET_KEY` kills every link already sent.
- **It works once.** `user_verify` only looks for *inactive*, not deleted users, and the view logs
  the student in, which sets `last_login` and changes the hash.
- **The resend page always says the same**, whatever the email, so nobody can use it to find out
  who is registered. It emails only inactive, not deleted students.
- **Password reset links can't activate anyone**: reset emails go only to active users.
