# 13. Backups and disaster recovery

Everything you need to survive losing the server: what is backed up, how to send encrypted copies to Backblaze B2, how to prove a backup
works without touching production, and how to rebuild on a new VPS.

**Contents:** [What's in a backup](#whats-in-a-backup) · [Local backups](#local-backups) · [Off-site to Backblaze B2](#off-site-backups-to-backblaze-b2) ·
[Schedule and retention](#schedule-and-retention) · [How a backup is verified](#how-a-backup-is-verified) · [Testing a restore safely](#testing-a-restore-safely) ·
[Restoring](#restoring-on-the-same-server) · [Full VPS recovery](#full-recovery-on-a-new-vps) · [Checklist](#checklist)

## What's in a backup

| File in the archive | Why it matters |
|---|---|
| `tgyt.db` | channels, users and roles, jobs and history, the **encrypted** Google tokens and OAuth client secret. Copied with SQLite's online backup API, so it is consistent even while the service runs. |
| `fernet.key` | the **only** key that decrypts the stored Google tokens. Without it a restored database can't upload anywhere and every channel must be re-linked. |
| `tgyt.env` | all settings, including the bot token and the relay session string. |
| `tls/`, `nginx-tgyt.conf` | the self-signed fallback certificate and the nginx site, if present. (Let's Encrypt certificates are simply re-issued on a new server.) |
| `MANIFEST.txt` | version, creation time, host name and a SHA-256 checksum of every other file. |

**Not included:** videos (they are deleted from the server after upload anyway), logs, and the Python environment (the installer rebuilds it).

> [!WARNING]
> A backup contains everything needed to upload to your channels and to log in to the relay Telegram account. Treat every copy like a password.
> Off-site copies are encrypted before they leave the server; local archives are not unless you use `--encrypt`.

## Local backups

```bash
sudo tgyt backup                      # one now, in /var/backups/tgyt (root-only)
sudo tgyt backup --encrypt            # the same, encrypted with a passphrase you type (AES-256, PBKDF2)
sudo tgyt backup schedule on|off      # the nightly job (on by default after install)
sudo tgyt backup schedule             # when it runs next
```

The nightly job (`tgyt-backup.timer`, about 03:30 server time) keeps the last 7 local archives, then makes the off-site copy if one is set up.
A local backup alone doesn't protect you from losing the server; set up off-site copies too.

## Off-site backups to Backblaze B2

`tgyt offsite` uses [restic](https://restic.net), which encrypts on the server before uploading. Backblaze B2 costs about $6 per TB per
month, so a few cents for this. Any S3-compatible storage works the same way.

### 1. In Backblaze

1. Create an account at backblaze.com (B2 Cloud Storage).
2. **Buckets → Create a Bucket**: a globally unique name (lowercase letters, digits, dashes; e.g. `tgyt-backup-yourname`),
   **Files in Bucket: Private**, default encryption may stay off (restic encrypts anyway), object lock off.
3. Note the bucket's **Endpoint**, e.g. `s3.us-west-004.backblazeb2.com`.
4. **Application Keys → Add a New Application Key**: name it, **Allow access to Bucket(s): only this bucket**, **Type of Access: Read and Write**.
   Copy the **keyID** and the **applicationKey** now; the key is shown only once.

A key limited to one bucket means a leaked server can't touch anything else in your Backblaze account.

### 2. On the server

```bash
sudo tgyt offsite setup
```

It installs restic if needed and asks for the endpoint, the bucket, the keyID and the applicationKey (typed hidden). Then it asks you to choose
an **encryption password** of at least 16 characters, typed twice and hidden.

> [!IMPORTANT]
> **Save the encryption password in your password manager before you continue.** It is stored only on this server, in
> `/etc/tgyt-offsite/restic.pass`. If the server is lost and you don't have it, nobody, including Backblaze, can decrypt your backups.

Setup then:

1. creates the encrypted repository (or reuses an existing one in that bucket if the password matches);
2. makes a backup and uploads it;
3. **downloads it again and verifies it** (the [restore test](#testing-a-restore-safely));
4. turns on the nightly job.

The storage key and password live in `/etc/tgyt-offsite/` (directory 700, files 600, owned by root), never inside a backup and never in
the app's own config folder.

## Schedule and retention

| What | When |
|---|---|
| Local archive + off-site upload | every night, about 03:30 server time |
| Off-site retention | 7 daily, 4 weekly, 6 monthly snapshots (older ones are pruned after each upload) |
| Off-site integrity check | every Sunday, 5% of the stored data is downloaded and verified (`restic check --read-data-subset=5%`) |
| Failure alert | if any step fails, the bot sends **you (the owner)** a Telegram message |
| Staleness check | `tgyt doctor` reports a failure when the newest off-site upload is more than 2 days old |

While the daily/weekly/monthly slots aren't full yet, restic also keeps the very first snapshot ("oldest daily/weekly/monthly"). That's expected.

```bash
sudo tgyt offsite status      # storage, last upload, list of snapshots
sudo tgyt offsite run         # upload one now
```

## How a backup is verified

Every check that reads a backup (`tgyt restore`, `tgyt offsite restore-test`, `tgyt offsite restore`) does the same, before changing anything:

1. the archive unpacks;
2. **every file matches its SHA-256 checksum** from `MANIFEST.txt`; any mismatch stops with the names of the files that differ;
3. the database passes SQLite's `integrity_check`;
4. the Fernet key is present (and, for restore tests, compared with the server's own key).

New backups are also checked right after they are written; a backup that fails its own check is not kept.

> [!NOTE]
> **Backups made with v1.0.0** list `MANIFEST.txt` inside itself, with a checksum taken while that file was still being written, so that one
> line can never match (v1.0.0 then reported `./MANIFEST.txt: FAILED`). From v1.0.1 the check skips that self-entry and still verifies every
> real file, so those backups remain fully restorable. New backups no longer contain the line.

## Testing a restore safely

```bash
sudo tgyt offsite restore-test
```

Downloads the newest off-site snapshot into a private temporary folder, decrypts it, runs [all the checks above](#how-a-backup-is-verified),
compares the Fernet key with this server's, prints `Restore test passed`, and securely deletes the folder. **It changes nothing on the
server**, so you can run it any time, even while uploads are running. It exits with a non-zero status if anything fails.

Run it after setup, after any change to the server, and every few months.

## Restoring on the same server

Use this to undo a mistake (a deleted channel, a broken setting):

```bash
ls -lt /var/backups/tgyt/                           # local archives, newest first
sudo tgyt restore /var/backups/tgyt/tgyt-backup-YYYYMMDD-HHMMSS.tar.gz
sudo tgyt offsite restore                           # or: download the newest off-site snapshot and restore that
```

`tgyt restore` verifies the archive first, makes a **safety copy of the current state**, asks you to type `restore`, stops the service,
puts back the database, settings and Fernet key, starts the service again and runs `tgyt doctor`. If you change your mind, restore the safety copy
the same way.

## Full recovery on a new VPS

You need: a new Ubuntu server, the **same** Backblaze bucket, keyID/applicationKey (or a new key for that bucket) and the **encryption
password**.

1. Point your domain's A record at the new server's IP ([3](03-domain-and-dns.md)) and wait until it resolves.
2. Install normally ([6](06-install.md)). You can enter your usual settings; the restore replaces them.
3. `sudo tgyt offsite setup` with the **same** bucket and password. Setup notices the existing repository and keeps it.
4. `sudo tgyt offsite restore-test`, to see that the snapshot is readable before you rely on it.
5. `sudo tgyt offsite restore`, then type `restore`. Channels, users, settings and keys come back.
6. If the hostname changed, run `sudo /opt/tgyt-uploader/deploy/install.sh` again (keep settings) to update nginx and the certificate, and add
   the new redirect URI in Google Cloud Console.
7. `sudo tgyt doctor`, then `/start` in Telegram and a short test upload.

Restoring the same bot token on two running servers makes them fight over Telegram updates: shut the old server down (or stop its `tgyt` service)
first. The same goes for the relay session.

## Checklist

- [ ] `sudo tgyt offsite setup` done, and **the encryption password is in your password manager**
- [ ] `sudo tgyt offsite restore-test` passes
- [ ] `sudo tgyt backup schedule` shows the nightly timer
- [ ] you know where the Backblaze keyID/applicationKey are stored (or how to create a new bucket key)
- [ ] after a server change: run the restore test again

Problems: [Troubleshooting → Off-site backups](10-troubleshooting.md#backups).
