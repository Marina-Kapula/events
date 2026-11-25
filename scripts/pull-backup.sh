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
