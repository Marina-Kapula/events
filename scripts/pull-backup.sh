#!/usr/bin/env bash
# Pulls a consistent copy of the production database from your VPS to your laptop and keeps
# the newest 30. Usage: scripts/pull-backup.sh <VPS_IP> <APP> [SSH_USER]   (SSH_USER defaults to
# ubuntu). Run it in Git Bash or WSL on Windows. Restoring: docs/deployment/backups.md.
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
final="$dir/db-$(date +%Y-%m-%d-%H%M).sqlite3"
part="$final.part"
mkdir -p "$dir"
trap 'rm -f "$part"' EXIT

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

# Names sort chronologically; keep the newest 30.
ls -1r "$dir"/db-*.sqlite3 | tail -n +31 | while IFS= read -r old; do
  rm -f -- "$old"
done

echo "Saved $final"
