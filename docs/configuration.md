# Configuration reference

All settings live in `/etc/tgyt/tgyt.env` (mode 600, owner `tgyt`) as `KEY=value` lines. Change them safely with `sudo tgyt config KEY`
(validated, previous file saved, optional restart) or edit the file and run `sudo tgyt restart`. A fully commented template with fake values is [`.env.example`](../.env.example).

Settings marked **UI** can also be changed live in the panel's *Settings* page; panel values are stored in the database and override the env file at start-up.

| Variable | Required | Default | What it does |
|---|---|---|---|
| `API_ID` | **yes** | — | Telegram application ID from my.telegram.org |
| `API_HASH` | **yes** | — | Telegram application hash (32 hex chars). Secret |
| `BOT_TOKEN` | **yes** | — | Bot token from @BotFather. Secret |
| `OWNER_TG_ID` | **yes** | — | Numeric Telegram ID of the owner (always allowed) |
| `SESSION_SECRET` | **yes** | generated | Signs login cookies; changing it logs everyone out. Secret |
| `USER_SESSION` | no | empty | Relay account session string (needed for videos > 20 MB). **Full access to that account.** Secret |
| `RELAY_CHAT_ID` | with `USER_SESSION` | empty | Private relay channel ID (`-100…`) |
| `OAUTH_MODE` | no | `hostname` | `hostname` (nginx + Let's Encrypt on `PUBLIC_HOST`) or `loopback` (self-signed, SSH tunnel / offline linking) |
| `PUBLIC_HOST` | hostname mode | — | Domain serving the panel, e.g. `upload.example.com` |
| `PUBLIC_IP` | no | detected | Informational; used in loopback URLs |
| `WEB_PORT` | no | `443` | Port the panel is served on. Non-443 ports appear in every URL and in the Google redirect URI |
| `LOOPBACK_PORT` | no | `8721` | Loopback mode only: local OAuth redirect port |
| `PROJECT_AUDITED` | no | `false` | `true` once Google's compliance audit passed (until then YouTube forces uploads Private). **UI** |
| `YT_REGION_CODE` | no | `US` | Region for YouTube category lists |
| `ADMIN_USERNAME` | no | `admin` | First admin's login name (the account is created by the installer) |
| `ADMIN_PASSWORD` | no | empty | Only used if no admin exists at first start; hashed into the DB then blanked. The installer leaves this empty |
| `REQUIRE_TOTP` | no | `false` | Force two-factor for all panel logins |
| `FERNET_KEY_PATH` | no | `/etc/tgyt/fernet.key` | Encryption key file. **Back it up** |
| `JOBS_DIR` | no | `/var/lib/tgyt/jobs` | Where videos are stored while uploading (real disk) |
| `DB_PATH` | no | `/var/lib/tgyt/tgyt.db` | SQLite database |
| `MAX_FILE_BYTES` | no | `2147483648` | Largest accepted video (4294967296 only with a Premium relay account) |
| `UPLOAD_CHUNK_BYTES` | no | `8388608` | Resumable-upload slice; must be a multiple of 262144. **UI** |
| `MAX_CONCURRENT_DOWNLOADS` | no | `2` | Parallel Telegram downloads. **UI** |
| `MAX_CONCURRENT_UPLOADS` | no | `1` | Parallel YouTube uploads. **UI** |
| `DEFAULT_PRIVACY` | no | `private` | `private`, `unlisted` or `public` (YouTube may force private). **UI** |
| `JOB_RETENTION_HOURS` | no | `24` | Hours before finished/failed jobs' files are deleted. **UI** |
| `MIN_FREE_DISK_BYTES` | no | `5368709120` | Free space downloads never consume (5 GiB) |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `SOURCE_CODE_URL` | no | this repository | Source-code link shown in the panel and `/help` (AGPL-3.0 §13). Change it if you run a modified version. |

Values must not be quoted and must not carry trailing `# comments`.

## Installer settings (`TGYT_*`)

Used only by `install.sh` (config file or environment). See [`deploy/install.conf.example`](../deploy/install.conf.example).

| Variable | Meaning |
|---|---|
| `TGYT_ACCESS_MODE` | `domain`, `sslip`, or `loopback` |
| `TGYT_DOMAIN` | the domain/subdomain (domain mode) |
| `TGYT_PUBLIC_IP` | override auto-detection |
| `TGYT_LE_EMAIL` | Let's Encrypt contact email (optional) |
| `TGYT_BOT_TOKEN`, `TGYT_API_ID`, `TGYT_API_HASH`, `TGYT_OWNER_ID` | the Telegram values |
| `TGYT_ADMIN_USER`, `TGYT_ADMIN_PASSWORD`, `TGYT_REQUIRE_TOTP` | panel account |
| `TGYT_REGION`, `TGYT_WEB_PORT`, `TGYT_MAX_FILE_BYTES` | region, port, size limit |
| `TGYT_SETUP_RELAY` | `yes` (interactive), `no`, or `preset` (with `TGYT_USER_SESSION` + `TGYT_RELAY_CHAT_ID`) |
| `TGYT_ENABLE_FIREWALL`, `TGYT_ENABLE_FAIL2BAN`, `TGYT_BACKUP_SCHEDULE` | `yes`/`no` |
| `TGYT_HARDEN_SSH` + `TGYT_SSH_KEY_CONFIRMED=yes` | key-only SSH (only after you verified key login) |
| `TGYT_SKIP_DNS_CHECK`, `TGYT_SKIP_CERT`, `TGYT_LE_STAGING`, `TGYT_FORCE_OS` | testing / unusual setups |
| `TGYT_RECONFIGURE=yes` | re-apply answers over an existing installation |
| `TGYT_REF`, `TGYT_REPO_URL` | (bootstrap) version/tag and repository to install |

## Files and folders

| Path | Owner / mode | Purpose |
|---|---|---|
| `/opt/tgyt-uploader/` | `tgyt` | installed application + `venv/` |
| `/opt/tgyt-src/` | root | git checkout used by `tgyt update` |
| `/opt/tgyt-rollback/` | root | the last two pre-update snapshots |
| `/etc/tgyt/tgyt.env` | `tgyt` 600 | settings and secrets |
| `/etc/tgyt/fernet.key` | `tgyt` 400 | encryption key |
| `/etc/tgyt/tls/` | `tgyt` | self-signed certificate (fallback / loopback mode) |
| `/var/lib/tgyt/tgyt.db` (+ `-wal`, `-shm`) | `tgyt` | database |
| `/var/lib/tgyt/jobs/<id>/` | `tgyt` | videos in progress |
| `/var/backups/tgyt/` | root 700 | backups and previous env files |
| `/etc/tgyt-offsite/` (`offsite.conf`, `restic.pass`, `last-success`) | root 700 / files 600 | off-site storage key and encryption password; only if you ran `tgyt offsite setup` |
| `/var/cache/tgyt-restic/` | root | restic's local cache (safe to delete) |
| `/etc/systemd/system/tgyt.service` (+ `tgyt-backup.{service,timer}`) | root | service and nightly backup |
| `/etc/nginx/sites-available/tgyt.conf` (+ `sites-enabled` link) | root | reverse proxy |
| `/etc/letsencrypt/` | root | certificates and renewal config |
| `/etc/fail2ban/jail.d/tgyt.local` | root | SSH jail |
| `/etc/ssh/sshd_config.d/00-tgyt-hardening.conf` | root | only if you chose SSH hardening |
| `/usr/local/bin/tgyt` | symlink | management command |
| `/var/log/tgyt-install.log`, `/var/log/tgyt-manage.log` | root 600 | redacted logs of the installer / `tgyt` |
