# Backups of the database and the photos

All data (users, events, sign-ups) is in one file on the server: `db.sqlite3` in the storage
directory `/var/lib/dokku/data/storage/<APP>/`. The photos students upload are next to it, in
`media/`; the database only stores their file names. If the VPS breaks, or a migration goes
wrong, you lose both. Keep copies on your own laptop. Placeholders are explained in
[deploy-to-dokku.md](deploy-to-dokku.md).

OVH's own VPS backup option is not a replacement: it keeps few copies, and restoring one rolls
back the whole server.

## Pull a copy to your laptop

```sh
scripts/pull-backup.sh <VPS_IP> <APP>               # laptop
scripts/pull-backup.sh <VPS_IP> <APP> <SSH_USER>    # if your user is not ubuntu
```

On Windows, run it in Git Bash or WSL.

- The script logs in over SSH and asks SQLite for a consistent copy (`VACUUM INTO`). A plain
  file copy is not safe: SQLite in WAL mode keeps recent writes in a separate `-wal` file.
- It checks the copy on the server (`integrity_check`) and on your laptop (the file must be a
  SQLite database).
- Copies go to `~/dokku-backups/<APP>/db-<YYYY-MM-DD-HHMM>.sqlite3`. The newest 30 are kept.
- Then it streams the photos over SSH as one archive,
  `~/dokku-backups/<APP>/media-<YYYY-MM-DD-HHMM>.tar.gz`, with the same date as the database
  copy. It checks the archive with `tar -tzf` and keeps the newest 30. Before anyone uploads a
  photo it says "No photos on the server yet": that is normal.
- Run it before every deploy and about once a week.

Check: the last two lines say `Saved .../db-....sqlite3` and `Saved .../media-....tar.gz`, and
`ls -l ~/dokku-backups/<APP>` shows files that are not empty.

Each archive is a full copy, and JPEGs don't shrink with gzip: 200 photos of 200 KB are about
40 MB per archive. `du -sh ~/dokku-backups/<APP>` shows how much you keep.

The copies hold personal data. Keep them outside the git repo and outside shared or synced
folders. Never commit them. The photos are students' faces: the same care. Use disk encryption on your laptop (FileVault, BitLocker).

## Restore

Use the newest good copy, or an older one if the newest is the problem. These commands run on
your laptop.

1. Stop the app, so nothing writes while you replace the file:

   ```sh
   ssh <SSH_USER>@<VPS_IP> sudo dokku ps:stop <APP>
   ```

2. Upload the copy as the database file:

   ```sh
   scp ~/dokku-backups/<APP>/db-<DATE>.sqlite3 <SSH_USER>@<VPS_IP>:/var/lib/dokku/data/storage/<APP>/db.sqlite3
   ```

   `scp` as `<SSH_USER>` makes you the owner (user id 1000), which is the user the app runs as.

3. Remove the old WAL files. If they stay, SQLite replays them on top of the restored database:

   ```sh
   ssh <SSH_USER>@<VPS_IP> rm -f /var/lib/dokku/data/storage/<APP>/db.sqlite3-wal /var/lib/dokku/data/storage/<APP>/db.sqlite3-shm
   ```

4. Start the app again. Its `release` step runs `migrate`, so a copy older than your code is
   brought up to date:

   ```sh
   ssh <SSH_USER>@<VPS_IP> sudo dokku ps:start <APP>
   ```

Check: the site loads and you can log in with an account that existed in the backup.

If the restore is because of a bad migration, skip step 4. Starting the app would run the bad
migration again. Fix the code and deploy it (`git push dokku main:master`): the deploy migrates
the restored database and starts the app.

## Restore the photos

Use the archive with the same date as the database copy you restored. It runs on your laptop,
while the app is stopped (step 1 above) or running: adding files doesn't disturb it.

    ssh <SSH_USER>@<VPS_IP> tar -C /var/lib/dokku/data/storage/<APP> -xzf - < ~/dokku-backups/<APP>/media-<DATE>.tar.gz

`<` sends the archive from your laptop into `ssh`, and `tar -xzf -` on the server unpacks it
into the storage directory, as `media/…`. Photos that are already there are overwritten with
the same file; newer ones stay. The files belong to `<SSH_USER>` (user id 1000), the user the
app runs as.

Check: a profile page with a photo shows it.

## A new server

To move to a new VPS: do all of [deploy-to-dokku.md](deploy-to-dokku.md) except `createsuperuser`,
then restore the database copy *and* the photos archive of the same date, as above (the app must
exist and have been deployed once). A database from one day with photos from an older day can
point at photos that aren't in the archive.
