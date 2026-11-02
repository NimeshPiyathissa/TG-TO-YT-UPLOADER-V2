# Architecture and dependency inventory

## Processes

One systemd service, `tgyt`, runs **one Python process** (`python -m bot.main`) that contains:

```
 Telegram ◀─MTProto─▶  bot client (Kurigram)  ──┐
 Telegram ◀─MTProto─▶  relay client (user session, optional) ──┤   JobQueue ── downloader ─▶ /var/lib/tgyt/jobs
                                                │                          └─ uploader ─▶ YouTube Data API (resumable)
 browser ◀─HTTPS─▶ nginx ─HTTP 127.0.0.1:8001─▶ FastAPI/uvicorn (admin panel, SSE /events, /oauth/callback)
                                                │
                                           SQLite (aiosqlite) + Fernet-encrypted secrets
```

- `bot/` Telegram handlers, queue, downloader, access control, notifications · `web/` panel (FastAPI, Jinja2, HTMX, SSE) · `yt/` OAuth, upload, quota, metadata
- `db/` schema and store · `tools/` helpers · `deploy/` installer, `tgyt` CLI, nginx/systemd templates · `tests/`

## External services

| Service | Used for | Needed from the user |
|---|---|---|
| Telegram Bot API / MTProto | receiving messages, downloading files ≤ 20 MB | bot token, API ID/hash |
| Telegram MTProto (user session) | **relay**: downloading files > 20 MB via a private channel | a relay account session + channel |
| Google OAuth 2.0 + YouTube Data API v3 | channel linking, uploads, deletes | own Google Cloud project, Web OAuth client JSON, test users |
| Let's Encrypt (ACME HTTP-01) | free HTTPS certificate for the hostname | DNS A record, reachable port 80 |
| `sslip.io` (optional) | free hostname without buying a domain | — |
| PyPI / apt mirrors | install | internet access from the server |

## System packages (installed by the installer)

`python3` (≥ 3.10), `python3-venv`, `python3-pip`, `python3-dev`, `build-essential` (for the optional `tgcrypto`), `ffmpeg`, `nginx`, `certbot`,
`git`, `openssl`, `curl`, `rsync`, `bind9-dnsutils` (dig), `ufw`, `fail2ban`, `python3-systemd`, `sqlite3`.

## Python packages (pinned in `requirements.txt`)

`kurigram==2.1.38` (Pyrogram fork), `aiohttp`, `aiofiles`, `google-auth`, `google-api-python-client`, `aiosqlite`, `cryptography`, `fastapi`, `uvicorn[standard]`,
`jinja2`, `python-multipart`, `itsdangerous`, `python-dotenv`, `structlog`, `pydantic`, `pydantic-settings`, `argon2-cffi`, `pyotp`, `qrcode`.
Optional (`requirements-optional.txt`): `tgcrypto` — a C speed-up for Telegram encryption; without it Kurigram falls back to pure Python.
Development: `requirements-dev.txt` (`pytest`, `pytest-asyncio`, `httpx`).

## Manual steps a new user must do (cannot be automated)

1. Rent a VPS; open ports 22/80/443 in the provider's firewall.
2. (Recommended) buy a domain and add an A record.
3. Create the Telegram bot (BotFather), get API ID/hash, owner ID.
4. (For > 20 MB) create the private relay channel, add the bot as admin, and complete the Telegram phone login.
5. Create a Google Cloud project, enable YouTube Data API v3, configure the consent screen + test users, create the Web OAuth client with the exact redirect URI, upload the JSON in the panel.
6. Link each channel by completing Google's consent in a browser.
7. (Optional) request Google's API audit / quota extension.

## Install flow (what `deploy/install.sh` does, in order)

preflight → questions (before anything is changed) → apt packages → user + folders (+ swap) → rsync app → venv + pip → Fernet key, env file, admin in DB →
systemd unit (+ backup timer) → nginx (self-signed first, then certbot webroot, then the real certificate) → ufw + fail2ban → relay (optional) → SSH hardening (optional) → `tgyt doctor`.
Re-running keeps settings, the database, the key and the admin; each step is skipped or repeated safely.

## Updates and rollbacks

`tgyt update`: fetch → snapshot (hard-link copy of code + venv, online DB backup, env, key) → rsync → pip → `tools/migrate_db.py` → start → health check →
automatic restore of the snapshot on any failure. Database changes are additive (new tables/columns), which is why restoring the old code with the snapshot database is safe.
