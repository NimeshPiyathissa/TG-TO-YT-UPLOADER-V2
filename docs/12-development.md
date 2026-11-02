# 12. Developer guide

How to clone the project, run it on your own computer, test it, change it and ship the change to a server.
If you only want to *use* the uploader, you don't need this page: follow [Running the installer](06-install.md).

**Contents:** [Requirements](#requirements) · [Windows setup](#windows-setup-powershell) · [Linux setup](#linux-ubuntu-setup) ·
[Running it locally](#running-it-locally) · [Tests](#tests-and-checks) · [Source tour](#source-tour) · [Configuration](#configuration) ·
[Workflow](#workflow-branches-pull-requests-releases) · [Deploying a change](#deploying-a-change-to-a-server) · [Debugging](#debugging)

## Requirements

| Need | Version / notes |
|---|---|
| **Git** | any recent version |
| **Python** | 3.10 or newer. Tested on Python 3.14 (Ubuntu 26.04 staging server) and 3.12 (Windows development). |
| **OS for development** | Windows 10/11, Ubuntu 22.04+, or macOS. The *server* side (installer, `tgyt`, systemd) is Linux-only. |
| **SQLite** | built into Python; nothing to install. The `sqlite3` command-line tool is handy for inspecting a database. |
| **FFmpeg** | not needed for development. The installer puts it on servers; the app does not need it to upload. |
| **C compiler** | only for the optional `tgcrypto` speed-up (`requirements-optional.txt`). Skip it on Windows; the app falls back to pure Python. |
| **ShellCheck** | to check the shell scripts (`pip install shellcheck-py` gives you a `shellcheck` command on any OS). |
| **Bash** | to run the shell-script tests on Windows: Git for Windows includes Git Bash. Without it those tests are skipped. |

To **run** the bot locally (the tests don't need any of this), you also need test credentials, never your production ones:

- a **separate test bot** from @BotFather (one token can only be used by one running copy at a time);
- an API ID and API hash from [my.telegram.org](https://my.telegram.org) ([4.2](04-telegram-setup.md#42-api-id-and-api-hash-mytelegramorg));
- for channel linking: a Google Cloud OAuth client ([5](05-google-cloud.md)). Google only redirects to the hostname you register, so linking
  channels is easiest on a test server; locally you can work on everything else.

## Windows setup (PowerShell)

```powershell
# 1. Tools (skip what you already have)
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
# Open a new PowerShell window afterwards so both are on PATH.

# 2. Get the code
git clone https://github.com/NimeshPiyathissa/TG-TO-YT-UPLOADER-V2.git
cd TG-TO-YT-UPLOADER-V2

# 3. Virtual environment and dependencies
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
pip install -r requirements-dev.txt   # pinned app dependencies + pytest, pytest-asyncio, httpx
pip install shellcheck-py             # optional: shellcheck for the scripts

# 4. Run the tests (about 3 minutes)
python -m pytest -q
```

## Linux (Ubuntu) setup

```bash
sudo apt update && sudo apt install -y git python3 python3-venv python3-dev build-essential shellcheck sqlite3
git clone https://github.com/NimeshPiyathissa/TG-TO-YT-UPLOADER-V2.git
cd TG-TO-YT-UPLOADER-V2
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -r requirements-optional.txt     # optional tgcrypto speed-up (needs build-essential)
python -m pytest -q
```

## Running it locally

The app reads its settings from the file named by `TGYT_ENV_FILE`, or `.env` in the current folder. `.env` is git-ignored.

```powershell
# Windows PowerShell, from the repository folder with the venv active
Copy-Item .env.example .env
New-Item -ItemType Directory -Force data | Out-Null
python -c "from cryptography.fernet import Fernet; open('data/fernet.key','wb').write(Fernet.generate_key())"
python -c "import secrets; print(secrets.token_hex(32))"      # copy the output into SESSION_SECRET
notepad .env
```

```bash
# Linux / macOS
cp .env.example .env && mkdir -p data
python -c "from cryptography.fernet import Fernet; open('data/fernet.key','wb').write(Fernet.generate_key())"
python -c "import secrets; print(secrets.token_hex(32))"      # copy the output into SESSION_SECRET
nano .env
```

Edit `.env` (all paths may be relative to the repository folder):

| Setting | Local value |
|---|---|
| `API_ID`, `API_HASH`, `BOT_TOKEN` | your **test** bot and API credentials |
| `OWNER_TG_ID` | your numeric Telegram ID (@userinfobot) |
| `PUBLIC_HOST` | `localhost` |
| `SESSION_SECRET` | the random string generated above |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | a local panel login; it's hashed into the database on first start and blanked in `.env` |
| `FERNET_KEY_PATH`, `DB_PATH`, `JOBS_DIR` | `data/fernet.key`, `data/tgyt.db`, `data/jobs` |
| `USER_SESSION`, `RELAY_CHAT_ID` | leave empty unless you are working on the large-file relay |

Then:

```bash
python tools/migrate_db.py      # optional: creates/migrates data/tgyt.db and prints "Database OK (14 tables)"
python -m bot.main              # starts the bot, the queue and the panel in one process; Ctrl+C stops it
```

- The panel listens on **http://127.0.0.1:8001** (on a server nginx puts HTTPS in front of this port). Its login cookie is marked *Secure*;
  current Chrome, Edge and Firefox accept that on `localhost`/`127.0.0.1`.
- Send `/start` to your **test** bot in Telegram.
- Files over 20 MB need the relay (`python tools/generate_session.py --env-file .env`, with a test account; [4.4](04-telegram-setup.md#44-the-relay-channel-only-for-videos-over-20-mb)).

`bot.main` needs a working Telegram login to start; with fake credentials it exits with an error, which is expected.

## Tests and checks

```bash
python -m pytest -q                  # whole suite, ~3 min; nothing touches real Telegram or Google
python -m pytest -q tests/test_queue.py              # one file
python -m pytest -q -k manifest                      # tests whose name matches
python -m pytest -m slow                             # adds a ~4 GB resumable-upload run through localhost
shellcheck -x -P deploy install.sh deploy/install.sh deploy/tgyt deploy/lib/*.sh
```

On Windows two tests are skipped on purpose (POSIX file permissions, and the installer's root check); on Linux as a normal user everything runs. CI runs the same tests on Python 3.12
and 3.14, a ruff error lint (`ruff check --select E9,F63,F7,F82`), ShellCheck and a gitleaks secret scan on every push and pull request
([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)).

| Test file | Covers |
|---|---|
| `test_queue.py`, `test_upload_resume.py`, `test_disk.py` | job lifecycle, resumable upload against a fake Google server, retries, disk-space checks |
| `test_accounts.py`, `test_multichannel.py`, `test_link_diagnostics.py` | channel linking, Brand Accounts, grouping, default channel, OAuth diagnostics |
| `test_premium_emoji.py`, `test_telegram_api_usage.py` | real bot handlers through Kurigram's parser; keyword arguments checked against the real Kurigram signatures |
| `test_live_progress.py`, `test_notify.py`, `test_restart.py` | live progress stream, Telegram notifications from the panel, the panel's Restart button |
| `test_command_routing.py`, `test_jobs_command.py` | every command reaches its own handler through Kurigram's real dispatcher; `/jobs` replies |
| `test_store_users.py`, `test_main_exit.py` | concurrent first contact; a startup failure ends the process |
| `test_release_docs.py` | documentation: every link, anchor and image resolves; README starts with the thumbnail; no placeholders; version matches the changelog |
| `test_installer_shell.py` | installer validation, generated env file loads in the app, log and panel redaction |
| `test_tgyt_cli.py` | `tgyt` command: off-site backups, failure alerts, backup manifests and restore checks, token rotation |
| `test_tools.py`, `test_relay_selftest.py` | session generator, `tgyt doctor` checks, admin tool, migrations, relay self-test |

## Source tour

```
bot/            Telegram side, and the process entry point
  main.py         starts everything: database, bot client, relay client, queue, panel (uvicorn)
  config.py       all settings, validated at start (pydantic-settings)
  handlers/       commands and callbacks: start, channels (/addyt, /channels, /removeyt), ingest (videos), caption, jobs
  queue.py        job state machine, workers, retries, leases (survives restarts)
  downloader.py   Telegram download: bot API for small files, relay account for large ones
  access.py       roles: owner › admin › uploader › blocked
  crypto.py       Fernet encryption of stored Google tokens and secrets
  fmt.py, ui.py   message formatting (HTML, custom emoji) and keyboards
yt/             YouTube side: OAuth (oauth.py), resumable upload (upload.py), quota (quota.py), token refresh, metadata
web/            admin panel (FastAPI + Jinja2 + htmx): app.py, auth/TOTP, CSRF, routes/, templates/, static/
db/             schema.sql and store.py (SQLite through aiosqlite; migrations run on connect)
tools/          admin_user, doctor_checks, generate_session (relay login), link_channel, migrate_db, relay_selftest
deploy/         install.sh (13-step installer), tgyt (management command), lib/*.sh, systemd units, nginx and fail2ban configs
tests/          pytest suite
docs/           these guides
```

Request flow and processes: [architecture.md](architecture.md).

## Configuration

Every setting, its default and what it does: [configuration.md](configuration.md). In short:

- The app reads **only** environment settings (`/etc/tgyt/tgyt.env` on a server, `.env` locally). Some limits can be overridden in the panel's
  **Settings** page; those are stored in the database and win over the file.
- On a server, change a setting with `sudo tgyt config KEY` (validated, secrets typed hidden, backup of the old file, optional restart).
- Never put real values in `.env.example`, tests or docs. CI's gitleaks scan fails the build on anything that looks like a credential.

## Workflow: branches, pull requests, releases

1. Branch from `main`: `git switch -c fix/short-description`.
2. Make the change **with a test**. Shell scripts must pass ShellCheck and keep LF line endings (`.gitattributes` enforces this).
3. `python -m pytest -q` and ShellCheck must pass locally.
4. Add a line to `CHANGELOG.md` under *Unreleased*, and update the docs if behaviour changed.
5. Open a pull request; describe *why* and what you tested. CI must be green.
6. Releases: bump `VERSION`, move *Unreleased* to a version heading in `CHANGELOG.md`, merge to `main`, tag `vX.Y.Z`
   ([14. Releases and upgrades](14-releases-and-upgrades.md)).

Dependencies are **pinned** in `requirements.txt`. To update one: change the pin, run the full suite, and note it in the changelog. Kurigram
(the Telegram library) changes its API between minor versions; `test_telegram_api_usage.py` catches most breakage, but test a real `/start`,
`/addyt` and an upload on a test bot before releasing.

## Deploying a change to a server

Never test unreleased code on a production server while uploads are running. With a checkout or an unpacked copy of the new version on the server:

```bash
sudo tgyt update --from /path/to/new/source   # rollback copy → install → migrations → health check → automatic rollback if unhealthy
sudo tgyt rollback                            # manual: back to the version before the last update
```

From a Windows checkout, make the copy with LF line endings (plain `git archive` on Windows can produce CRLF, which breaks the scripts):

```powershell
git -c core.autocrlf=false archive --format=tar HEAD -o tgyt-src.tar
scp tgyt-src.tar user@your-server:~/
# on the server: mkdir -p ~/tgyt-src && tar -xf ~/tgyt-src.tar -C ~/tgyt-src && sudo tgyt update --from ~/tgyt-src
```

Check first that nothing is uploading (`/jobs` in Telegram, or the panel's dashboard): `tgyt update` restarts the service. Interrupted transfers
resume, but there is no reason to make them.

## Debugging

| Where | How |
|---|---|
| Live log on a server | `sudo tgyt logs -f` (JSON lines; secrets are never logged) |
| More detail | `sudo tgyt config LOG_LEVEL` → `DEBUG`, then back to `INFO` |
| Health of everything | `sudo tgyt doctor` |
| Large-file path | `sudo tgyt relay-test` (pauses the bot, then downloads test files through the relay without touching YouTube) |
| Database | `sudo sqlite3 -readonly /var/lib/tgyt/tgyt.db` (read-only, safe while running) |
| Locally | `LOG_LEVEL=DEBUG` in `.env`, run `python -m bot.main` in a terminal |
