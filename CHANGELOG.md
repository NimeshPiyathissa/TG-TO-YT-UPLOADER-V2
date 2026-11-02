# Changelog

All notable changes to this project. Format based on [Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [1.0.1] — 2026-11-02 — first public release

### Added
- Licensed under the **GNU AGPL-3.0-only**. The panel (sidebar and login page) and `/help` link to the source code; the link is the
  new `SOURCE_CODE_URL` setting.
- Documentation: developer guide ([docs/12](docs/12-development.md)), backups and disaster recovery ([docs/13](docs/13-backup-and-recovery.md)),
  releases and upgrades ([docs/14](docs/14-releases-and-upgrades.md)), an extended domain/subdomain/DNS guide (Spaceship, Cloudflare,
  several subdomains, DNS tools, HTTPS, redirect URI), `LICENSE` and `THIRD_PARTY_NOTICES.md` (bundled fonts' OFL text in `web/static/fonts/OFL.txt`).

### Security
- The admin panel now forbids being embedded in other sites (`X-Frame-Options: DENY`, `frame-ancestors 'none'`) and sends
  `Referrer-Policy: same-origin`, on every response.

### Fixed
- `/jobs` and `/cancel <id>` got no reply: the title step's text handler matched every text message, commands included, and
  Kurigram runs only the first matching handler, so the commands registered after it never ran. Commands are now excluded from it,
  and one function (`bot.handlers.register_all`) fixes the order for the bot and the tests. `/jobs` now shows active uploads with
  progress, says "No active uploads." when there are none, lists recent DONE/CANCELLED/FAILED jobs, and answers a database error
  with a message instead of silence.
- Several messages arriving at once from someone the bot hadn't seen before crashed all but one handler with
  `UNIQUE constraint failed: tg_users.tg_user_id`. The user record is now created in a single statement.
- Backups listed their own `MANIFEST.txt` with a checksum taken while the file was still being written, so `tgyt offsite setup`,
  `tgyt offsite restore-test` and `tgyt restore` failed with `./MANIFEST.txt: FAILED` although every data file was intact. New backups
  no longer list the manifest and are verified before they count as written; existing backups stay restorable (the self-entry is
  skipped, every real file is still checked). Checksum errors now name the files that differ.
- A startup failure (e.g. a revoked bot token) now ends the process so systemd restarts it; before, an open database thread kept it
  running and the service looked healthy while the bot was down.
- `tgyt config BOT_TOKEN` moves the old bot login (`tgyt-bot.session`) aside, so the bot logs in with the new token instead of
  failing with `SESSION_REVOKED`.

### Changed
- Docs and the `fmt.custom_emoji_removed_by_telegram` log entry now state Telegram's rule for animated emoji in bot messages:
  the bot's owner needs Telegram Premium (or the bot a Fragment username).

## [1.0.0] — 2026-11-01 — first staging deployment (not published)

### Added
- One-command installer (`install.sh`) and interactive, idempotent, validated wizard (`deploy/install.sh`) for Ubuntu 26.04 / 24.04 / 22.04:
  OS/arch/RAM/disk checks, DNS A-record verification with the exact record to add, Let's Encrypt via nginx with auto-renewal, ufw, fail2ban,
  optional key-only SSH hardening with a lock-out safeguard, non-interactive mode (config file or `TGYT_*` variables), redacted install log.
- `tgyt` management command: `status`, `logs`, `restart`, `doctor`, `config`, `relay`, `admin`, `backup` (+ encryption, nightly schedule), `restore`,
  `update` (rollback copy, migrations, health check, automatic rollback), `rollback`, `uninstall`.
- `tools/generate_session.py`: guided relay login (phone, code, 2FA), channel picker, bot-admin check, Premium detection (2 GB / 4 GB); stores the session without ever printing it. Works without `tgcrypto`.
- `tools/doctor_checks.py`, `tools/admin_user.py` (admin creation / password and authenticator reset), `tools/migrate_db.py`.
- `tgyt offsite setup|run|status|restore-test|restore`: encrypted off-site backups to Backblaze B2 or any S3-compatible storage with restic.
  Setup verifies the first upload by downloading and checking it. The nightly job uploads after the local backup with 7/4/6 retention and a weekly
  partial data check, and sends the owner a Telegram message if anything fails. `tgyt doctor` and `tgyt status` report the last upload.
- Documentation for beginners (`docs/`), `.env.example` documenting every variable, security policy, contributing guide, issue templates, CI.

### Changed
- The admin account is created directly in the database by the installer; the password is never written to a file.
- `tgcrypto` moved to `requirements-optional.txt` (a failed C build no longer breaks the install).
- nginx config streams `/events` (SSE) unbuffered and adds HSTS; certificates are obtained with certbot's webroot method.
- The panel's "SSH tunnel" hint no longer assumes the `azureuser` account.
- fail2ban bans through ufw, so a ban never cuts an SSH session that is already open, and an existing `jail.d/tgyt.local` is no longer overwritten on re-runs.
- Dependencies updated to current releases (FastAPI 0.162, cryptography 50, kurigram 2.2, uvicorn 0.54, pydantic 2.14, …).

### Fixed
- `tgyt update`'s health check started from a malformed variable, and `tgyt relay-test` lost the test's exit code.
- The panel's **Restart** button never worked: the service's `NoNewPrivileges` sandbox blocks `sudo`. The app now exits cleanly and systemd's
  `Restart=always` brings it back, so the sudoers rule is no longer installed (and an old one is removed).
- Ubuntu 26.04: install `bind9-dnsutils` (the `dnsutils` package no longer exists), and `tgyt` keeps its settings when it re-runs itself with
  sudo, because sudo-rs ignores a bare `sudo -E`. Tested on Ubuntu 26.04 with Python 3.14.
- **Security:** the Settings page's "redacted" env view showed `USER_SESSION` (the relay account session) in clear text. It is now masked.

### Notes
- Feature set is that of the previous private releases: Telegram bot, large-file relay (up to 4 GB with Premium), multi-channel and Brand-account linking,
  roles and permissions, admin notifications, web panel (red theme, dark mode, SSE live progress, TOTP), quota display, resumable uploads with retries, disk checks and job expiry.
