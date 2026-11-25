# Back up the photos too

Status: done · Opened: 2026-11-21 · Milestone: M3 · Depends on: 004, 006

## Why

`scripts/pull-backup.sh` copies the database to your laptop (issue 004,
`docs/deployment/backups.md`). Since issue 006 the server holds a second kind of data: the
photos students upload, in `var/media/` on the storage mount (SPEC.md §2 #13, §6.8). The
database only stores their file names. Restore a database without the photos, and every profile
and event shows a broken image.

This issue extends the same script to also pull an archive of the photos, and the restore notes
to put them back. The script stays generic: the server's address and the app's name are
arguments, as now, so every student runs it against their own server and nothing private goes
into git.

## What you'll build

- `scripts/pull-backup.sh` also saves `~/dokku-backups/<APP>/media-<YYYY-MM-DD-HHMM>.tar.gz` next
  to the database copy, and keeps the newest 30 of each.
- `docs/deployment/backups.md` explains the photos: what is saved, and how to restore them.
- The script passes `bash -n` and ShellCheck, and you tested it against your own server.

## Before you start

Read:
- `docs/deployment/backups.md` (all) and `scripts/pull-backup.sh`: you change both.
- `docs/deployment/deploy-to-dokku.md` part 8 (the storage mount, and why photos live in `var/`).
- SPEC.md §2 #4, #13; §6.8 (old photo files are never deleted).
- [GNU tar manual](https://www.gnu.org/software/tar/manual/tar.html) and
  [ShellCheck](https://www.shellcheck.net/).

Words you'll meet:
- **`tar`**: packs a folder into one file (an *archive*) and unpacks it again. With `-z` it is
  also compressed with gzip: a `.tar.gz`.
- **Stream**: `tar -czf -` writes the archive to its standard output instead of a file; `ssh`
  carries that output to your laptop, where the script saves it. Nothing is written on the server.
- **Heredoc** (`<<'REMOTE' … REMOTE`): a block of text given to a command as its input. The
  script uses it to send a small script to the server's `bash`.
- **ShellCheck**: a linter for shell scripts, like ruff for Python.

## Steps

### 1. How the photos get to your laptop

On the server, the photos are in `/var/lib/dokku/data/storage/<APP>/media/`. The script logs in
as `<SSH_USER>`, who owns those files (user id 1000, the user the app runs as, deploy guide part
8), so it needs no `sudo`, and runs:

```sh
tar -C /var/lib/dokku/data/storage/<APP> -czf - media
```

`-C` goes into the storage folder first, so the archive holds `media/photos/...` and not the
whole path; `-c` creates, `-z` compresses, `-f -` writes to standard output. On your laptop that
output goes into a file.

Why this and not something else:

- **`scp -r`** would copy the folder file by file: thousands of small copies, nothing that tells
  you the copy is complete, and no single file to date and count.
- **`rsync`** would copy only what changed, but it isn't in Git Bash on Windows, and keeping 30
  dated versions with it needs more tricks.
- **One archive per run** is one file you can check (`tar -tzf`), keep 30 of, and restore with
  one command. Photos are small (at most 1024 px, 006), so a full copy each time is fine.

- [x] You can explain each part of the `tar` command.

### 2. The new script

Replace `scripts/pull-backup.sh` with this. The database part is unchanged except for the
shared date stamp and the clean-up function:

```bash
#!/usr/bin/env bash
# Pulls a consistent copy of the production database and an archive of the uploaded photos
# from your VPS to your laptop, and keeps the newest 30 of each.
# Usage: scripts/pull-backup.sh <VPS_IP> <APP> [SSH_USER]   (SSH_USER defaults to ubuntu).
# Run it in Git Bash or WSL on Windows. Restoring: docs/deployment/backups.md.
set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "usage: $0 <VPS_IP> <APP> [SSH_USER]" >&2
  exit 2
fi
host=$1
app=$2
user=${3:-ubuntu}

umask 077 # the copies hold personal data

dir=~/dokku-backups/$app
stamp=$(date +%Y-%m-%d-%H%M)
final="$dir/db-$stamp.sqlite3"
media_final="$dir/media-$stamp.tar.gz"
part="$final.part"
media_part="$media_final.part"
mkdir -p "$dir"
trap 'rm -f "$part" "$media_part"' EXIT

# Keeps the newest 30 files of one kind; the names sort chronologically.
keep_newest_30() {
  printf '%s\n' "$dir/$1"-*"$2" | sort -r | tail -n +31 | while IFS= read -r old; do
    rm -f -- "$old"
  done
}

# VACUUM INTO rather than cp: in WAL mode recent commits sit in db.sqlite3-wal, and VACUUM INTO
# reads everything in one transaction. It runs as the database's owner (uid 1000), so no sudo.
# mode=rw makes a wrong path fail instead of creating an empty database.
ssh "$user@$host" 'bash -s' -- "$app" >"$part" <<'REMOTE'
set -euo pipefail
db=/var/lib/dokku/data/storage/$1/db.sqlite3
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
python3 -c '
import sqlite3, sys
src = sqlite3.connect(f"file:{sys.argv[1]}?mode=rw", uri=True)
src.execute("VACUUM INTO ?", (sys.argv[2],))
src.close()
copy = sqlite3.connect(sys.argv[2])
result = copy.execute("pragma integrity_check").fetchone()[0]
if result != "ok":
    sys.exit(f"integrity_check failed: {result}")
' "$db" "$tmp"
cat "$tmp"
REMOTE

# A failed download or an error message is not a SQLite file.
if [ "$(head -c 15 "$part")" != "SQLite format 3" ]; then
  echo "the downloaded file is not a SQLite database" >&2
  exit 1
fi
mv "$part" "$final"
keep_newest_30 db .sqlite3
echo "Saved $final"

# The photos, after the database: photos are never deleted, so every photo this database
# copy points to is in the archive. tar streams them over SSH; no copy is left on the server.
# No media directory yet (nobody uploaded a photo) means an empty download.
ssh "$user@$host" 'bash -s' -- "$app" >"$media_part" <<'REMOTE'
set -euo pipefail
storage=/var/lib/dokku/data/storage/$1
if [ -d "$storage/media" ]; then
  tar -C "$storage" -czf - media
fi
REMOTE

if [ ! -s "$media_part" ]; then
  echo "No photos on the server yet"
  exit 0
fi
# An interrupted download or an error message is not a readable archive.
if ! tar -tzf "$media_part" >/dev/null; then
  echo "the downloaded photos are not a readable .tar.gz archive" >&2
  exit 1
fi
mv "$media_part" "$media_final"
keep_newest_30 media .tar.gz
echo "Saved $media_final"
```

What changed, and why:

- **One `stamp` for both files**, so the database and the photos of one run have the same date in
  their names. When you restore, take the pair.
- **The database first, then the photos.** SPEC.md §6.8: photo files are never deleted. So any
  photo the database copy points to was already on disk, and is in the archive taken a moment
  later. The other order could miss a photo uploaded between the two copies.
- **No `media` folder yet** (nobody uploaded a photo) is not an error: the server sends nothing,
  the script says "No photos on the server yet" and stops, with the database already saved.
- **`tar -tzf` checks the download**: it lists the archive and fails if the file is cut short or
  is an error message. Like the "SQLite format 3" check, a bad copy never gets the final name.
- **`.part` files and the `trap`**: the download goes to `….part` and is renamed only when it is
  good. The `trap` deletes leftovers on every exit, success or failure.
- **`keep_newest_30`** replaces the old `ls -1r … | tail -n +31` and serves both kinds. The glob
  `"$dir/$1"-*"$2"` lists the files in name order, which is date order; `sort -r` puts the newest
  first; `tail -n +31` keeps the lines from the 31st on, the ones to delete. It uses `printf`
  instead of `ls`, which ShellCheck warns about (SC2012).
- **`umask 077`** (unchanged) makes both files readable by you only: the photos are personal
  data, like the database.

- [x] `scripts/pull-backup.sh` as above.

### 3. Check the script

```sh
bash -n scripts/pull-backup.sh          # syntax only; prints nothing if it is fine
shellcheck scripts/pull-backup.sh       # prints nothing if it is fine
```

Install ShellCheck with `brew install shellcheck` (macOS) or `sudo apt install shellcheck`
(Ubuntu, WSL). Without installing anything: `uvx --from shellcheck-py shellcheck
scripts/pull-backup.sh`.

- [x] Both commands print nothing.

### 4. Test it against your server

There is no automated test for this script: it needs your server. Test it by hand, and write
what you saw in the pull request.

1. Make sure there is at least one photo on the server: your profile photo (009), or an event's.
2. Pull a backup:

   ```sh
   scripts/pull-backup.sh <VPS_IP> <APP>    # laptop
   ```

   The last two lines say `Saved …/db-….sqlite3` and `Saved …/media-….tar.gz`.
3. Look inside the archive: `tar -tzf ~/dokku-backups/<APP>/media-<DATE>.tar.gz | head` lists
   `media/photos/users/…`.
4. Unpack it somewhere harmless and open a photo:

   ```sh
   mkdir -p /tmp/restore-test
   tar -C /tmp/restore-test -xzf ~/dokku-backups/<APP>/media-<DATE>.tar.gz
   ls /tmp/restore-test/media/photos/users
   ```

   Then delete `/tmp/restore-test`: it holds personal data.
5. Check that only 30 copies are kept, without waiting a month: make 31 empty "old" files, run
   the script, count.

   ```sh
   for day in $(seq -w 1 31); do
     touch ~/dokku-backups/<APP>/media-2000-01-$day-0000.tar.gz
   done
   scripts/pull-backup.sh <VPS_IP> <APP>
   ls ~/dokku-backups/<APP>/media-* | wc -l    # 30
   ```

   The fake files from the year 2000 are the oldest, so they are the ones deleted. Remove the
   rest afterwards: `rm ~/dokku-backups/<APP>/media-2000-*`.
6. `ls -l ~/dokku-backups/<APP>` shows `-rw-------` for the new files: only you can read them.

- [x] Steps 1–6 done on your server; what you saw is in the pull request.

### 5. Update the notes

In `docs/deployment/backups.md`:

- The title and the first paragraph: the backup is now the database **and the photos**
  (`media/` in the same storage directory).
- "Pull a copy to your laptop": the photos go to
  `~/dokku-backups/<APP>/media-<YYYY-MM-DD-HHMM>.tar.gz`, checked with `tar -tzf`, the newest 30
  kept; "No photos on the server yet" is normal before the first upload. The check line: the
  last two lines say `Saved …`.
- A new part after "Restore", for example:

  ```markdown
  ## Restore the photos

  Use the archive with the same date as the database copy you restored. It runs on your laptop,
  while the app is stopped (step 1 above) or running: adding files doesn't disturb it.

      ssh <SSH_USER>@<VPS_IP> tar -C /var/lib/dokku/data/storage/<APP> -xzf - < ~/dokku-backups/<APP>/media-<DATE>.tar.gz

  `<` sends the archive from your laptop into `ssh`, and `tar -xzf -` on the server unpacks it
  into the storage directory, as `media/…`. Photos that are already there are overwritten with
  the same file; newer ones stay. The files belong to `<SSH_USER>` (user id 1000), the user the
  app runs as.

  Check: a profile page with a photo shows it.
  ```

- "A new server": restore the database copy *and* the photos archive of the same date.

And in `docs/index.md`, the Backups line: "pull a copy of the database and the photos with
`scripts/pull-backup.sh`, restore them".

- [x] `backups.md` and `index.md` updated.

## Done when

- [x] `scripts/pull-backup.sh <VPS_IP> <APP> [SSH_USER]` saves the database and a photos archive
      with the same date stamp, checks both, and keeps the newest 30 of each.
- [x] With no photos on the server it still saves the database and says so.
- [x] `bash -n` and `shellcheck` are clean.
- [x] Tested by hand against your server (step 4); the pull request says what you saw.
- [x] `docs/deployment/backups.md` explains the photos backup and their restore.
- [x] `scripts/check.sh` passes (nothing in it changed, but the pre-commit hook runs it).
- [x] This issue's tasks are ticked and its `Status:` line says done.

## Git

```sh
git switch main && git pull
git switch -c 019-back-up-photos
```

Suggested commits:
1. `Pull an archive of the photos in pull-backup.sh`
2. `Explain the photos backup and restore in backups.md`
3. `Close 019 in the issue`

Open a pull request titled "Back up the photos too". Paste the script's output (without your
server's address) and the `ls -l` of step 4.6.

## Watch out

- **Never commit a backup, or put your server's address in the script.** The address and the app
  name are arguments; `~/dokku-backups/` is outside the repo on purpose.
- **Keep the backups out of synced folders** (Dropbox, iCloud, OneDrive): the photos are students'
  faces. `backups.md` already says it for the database; it is true for the photos too.
- **The archives grow.** Each one is a full copy. JPEGs don't get smaller with gzip, so 200 photos
  of 200 KB are about 40 MB per archive, and 30 archives about 1.2 GB. `du -sh
  ~/dokku-backups/<APP>` shows how much you keep.
- **Restore the pair.** A database from one day with the photos from an older day can point at
  photos that aren't in the archive.
- **`<SSH_USER>` must be the user with id 1000** (OVH's `ubuntu` is). Another user can't read the
  photos without `sudo`, and the database part would fail first anyway.
- **Windows**: run it in Git Bash or WSL, as before: both have `ssh` and `tar`.

## Results

- Tested 2026-11-25 against the DigitalOcean droplet, as `root` (the third argument): on this
  server there is no `ubuntu` user, and root can read the storage directory.
- Output: `Saved …/db-2026-11-25-0936.sqlite3` and `Saved …/media-2026-11-25-0936.tar.gz`.
  The archive lists `media/photos/events/…` and `media/photos/users/…` (5 photos); unpacked in a
  scratch folder, the photos open, and the folder was deleted. The database copy passes
  `integrity_check`.
- Rotation: with 31 fake `media-2000-01-*` files, one run left exactly 30 media files.
- On Windows (Git Bash on NTFS) `ls -l` shows `-rw-r--r--`: `umask 077` has no effect there.
  The files are still private, because `~` is only readable by your Windows account; keep that
  folder out of OneDrive.

## Further reading

- [GNU tar manual](https://www.gnu.org/software/tar/manual/tar.html): `-c`, `-x`, `-t`, `-z`,
  `-f -`, `-C`.
- [Bash manual: Here Documents](https://www.gnu.org/software/bash/manual/bash.html#Here-Documents)
  and [The Set Builtin](https://www.gnu.org/software/bash/manual/bash.html#The-Set-Builtin)
  (`set -euo pipefail`).
- [ShellCheck](https://www.shellcheck.net/) and its wiki page
  [SC2012](https://www.shellcheck.net/wiki/SC2012).
- [Dokku: Persistent storage](https://dokku.com/docs/advanced-usage/persistent-storage/).
- The [3-2-1 backup rule](https://www.backblaze.com/blog/the-3-2-1-backup-strategy/): why a copy
  on your laptop is good, and a second copy somewhere else is better.
- [The Missing Semester: Shell Tools and Scripting](https://missing.csail.mit.edu/2020/shell-tools/):
  variables, quoting, exit codes and `&&`, the bash a backup script is made of.
- [The Missing Semester: Command-line Environment, Remote Machines](https://missing.csail.mit.edu/2020/command-line/#remote-machines):
  running a command on the server with `ssh` and piping its output back to your laptop.
- [Julia Evans: Bash scripting quirks & safety tips](https://jvns.ca/blog/2017/03/26/bash-quirks/):
  `set -euo pipefail` and quoting, in plain words.
- [William Shotts: The Linux Command Line](https://linuxcommand.org/tlcl.php), a free book on the
  command line and shell scripting, for the whole picture.
