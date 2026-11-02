# 9. Day-to-day use

## Using the bot

1. Send `/start` — shows your channels and quota. Unknown users get "You're not authorised" plus their numeric ID.
2. **Send a video** (as a video or a file). Pick the channel (skipped if only one), type a title/caption, and watch the progress bar.
3. `/jobs` lists your active uploads (with live progress) and your last 10 jobs, `/cancel <id>` stops one, `/status` shows bot health and quota.
   A title can't start with `/` (that's read as a command).
4. Owner/admins: `/addyt` (link a channel), `/removeyt`, `/channels`.

**Giving someone access:** ask them to message the bot (they get their numeric ID), then Panel → **Users** → *Grant access* (role `uploader`, `admin`, or `blocked`).
They are notified on Telegram when promoted.

Roles: `owner` (always allowed, set at install) › `admin` (manage channels and users) › `uploader` (upload only) › `blocked`.

## Using the panel

Open your panel address and log in. Dashboard (live progress), Channels, Users, Jobs, Videos, Logs, Settings — see [overview](01-overview.md).
Lost your authenticator app or forgot the password? On the server: `sudo tgyt admin`.

## The `tgyt` command

Run these on the server (they ask for `sudo` themselves if needed).

| Command | What it does |
|---|---|
| `tgyt status` | Service state, panel address, mode, relay, certificate expiry, free disk, channels/jobs, last backup |
| `tgyt logs [-f] [-n 200]` | Show / follow the service log |
| `tgyt restart` · `start` · `stop` | Control the service |
| `tgyt doctor [--deep]` | Verification with a fix for each failure; `--deep` also tests certificate renewal. Ends with a checklist to try by hand. |
| `tgyt config` | Lists settings (secrets hidden). `tgyt config KEY` changes one: the value is **validated**, the old file is copied to `/var/backups/tgyt`, then you can restart. |
| `tgyt relay` | Re-run the large-file Telegram login (new session, channel, 2 GB/4 GB detection) |
| `tgyt admin` | Reset a panel password / create an admin / remove a lost authenticator and clear the lockout |
| `tgyt backup [--encrypt] [--out DIR] [--keep N]` | See below |
| `tgyt backup schedule on\|off\|status` | Nightly backup at ~03:30, keeps the last 7 (and uploads off-site when configured) |
| `tgyt offsite setup\|run\|status\|restore-test\|restore` | Encrypted off-site copies in Backblaze B2 / S3, see [below](#off-site-backups-strongly-recommended) |
| `tgyt restore FILE` | See below |
| `tgyt update [--ref vX.Y.Z] [-y]` | See below |
| `tgyt rollback` | Return to the version before the last update |
| `tgyt uninstall` | See below |

## Backups — read this

`tgyt backup` writes `/var/backups/tgyt/tgyt-backup-YYYYMMDD-HHMMSS.tar.gz` (mode 600) containing:
- the **database** (consistent online copy — channels, users, jobs, videos, encrypted YouTube logins),
- the **env file** (bot token, secrets…),
- the **Fernet key** (`/etc/tgyt/fernet.key`), and a checksum manifest.

> ⚠️ **Without the Fernet key, the saved YouTube logins in the database cannot be decrypted** — you would have to re-link every channel. Always keep the key with the database backup,
> and keep at least one copy **off the server** (your computer, another cloud). Because the archive contains your secrets, `--encrypt` adds a passphrase
> (AES-256, PBKDF2) before you store it elsewhere. Copy it with `scp root@YOUR_SERVER:/var/backups/tgyt/tgyt-backup-….tar.gz .`

### Off-site backups (strongly recommended)

> Complete guide, including how backups are verified and how to recover on a new VPS:
> [13. Backups and disaster recovery](13-backup-and-recovery.md).

A backup that only lives on the server disappears with the server. `tgyt offsite` sends the same archive, **encrypted on your server
before it leaves**, to cheap object storage: Backblaze B2 (about $6/TB per month, so a few cents for this) or any S3-compatible service. It uses
[restic](https://restic.net).

**Set it up once (about 5 minutes):**

1. In Backblaze: **Buckets → Create a Bucket**, with a unique name and *Files in Bucket*: **Private**. Note the bucket's **Endpoint** (`s3.<region>.backblazeb2.com`).
2. **Application Keys → Add a New Application Key**: allow access to **only that bucket**, type *Read and Write*. Copy the `keyID` and `applicationKey`;
   the key is shown only once.
3. On the server: `sudo tgyt offsite setup`. Enter the endpoint, bucket, keyID and key (hidden), then choose an **encryption password**
   (16+ characters, hidden).
4. **Save that password in your password manager now.** It is the only thing that can decrypt the backups, and it is not stored anywhere except on this
   server. If the server is lost and you don't have the password, the backups are useless.

Setup creates the encrypted repository, uploads the first backup, **downloads it again to prove it can be restored**, and switches on the nightly job.

**What happens every night** (`tgyt-backup.timer`, about 03:30): a local backup (last 7 kept), then the off-site upload. Off-site retention is 7 daily,
4 weekly and 6 monthly copies, and every Sunday 5% of the stored data is read back and verified. **If anything fails, the bot sends you
(the owner) a Telegram message.** `tgyt doctor` also flags an off-site backup older than 2 days.

| Command | What it does |
|---|---|
| `sudo tgyt offsite status` | Storage, last upload, list of snapshots |
| `sudo tgyt offsite run` | Upload a backup now |
| `sudo tgyt offsite restore-test` | Download the newest backup and verify it (checksums, database integrity, Fernet key). Changes nothing. |
| `sudo tgyt offsite restore` | Download the newest backup and restore it (same safety steps as `tgyt restore`) |

**Recovering on a brand-new server:** install normally, then run `sudo tgyt offsite setup` with the **same** bucket, key and encryption password
(setup notices the existing repository and keeps it), then `sudo tgyt offsite restore`. Your channels, users and keys come back; then point DNS at the
new server.

The storage key and encryption password are kept in `/etc/tgyt-offsite/` (root only, never inside a backup and never in the app's own config folder).

### Restoring

`tgyt restore FILE` verifies the checksums and the database integrity, makes a safety backup of the current state, asks you to type `restore`, replaces the database/env/key,
restarts and runs `doctor`. Use it to recover from mistakes or to move to a new server (install first, then restore).

## Updating

```bash
sudo tgyt update               # shows what changed, asks, then upgrades to the newest release tag
sudo tgyt update --ref v1.2.0  # a specific version
```

What happens: fetch → show changes → **rollback copy** of the code, Python environment and database/keys → install files → update dependencies →
database migrations (run before the new version starts) → start → **health check** (service stays up, panel answers, no fatal errors in the log).
If anything fails — including the health check — it **rolls back automatically** (old code, old libraries, old database) and tells you. `tgyt rollback` does it manually later.
If a release changes server-level pieces (nginx config), re-run `sudo /opt/tgyt-src/deploy/install.sh` (it keeps your settings).

## Uninstalling

`sudo tgyt uninstall` asks, step by step, before removing anything: an optional **final backup**, whether to delete the database/videos, the settings **and Fernet key**,
the certificate, and the `tgyt` user. Deleting data needs you to type `DELETE`. It always leaves nginx, ufw/fail2ban settings and apt packages alone.

## Routine care

- Re-authorize channels when they turn red (every 7 days while Google's consent screen is in Testing).
- Check `tgyt doctor` after server maintenance. Keep Ubuntu updated (`sudo apt update && sudo apt upgrade`); the system restarts the service on boot.
- Watch free disk space (`tgyt status`); finished job files are deleted after 24 h.
