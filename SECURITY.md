# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's private reporting:
repository → **Security** → **Report a vulnerability** (GitHub Private Vulnerability Reporting).
Include what you found, how to reproduce it, and the version (`tgyt version`). You'll get an acknowledgement within a few days.

## Scope

In scope: the admin panel (authentication, CSRF, sessions, file upload of OAuth JSON), secret handling (env file, Fernet key, logs, backups),
the installer and `tgyt` CLI (privilege handling, file permissions, command injection), the Telegram access-control logic, and the OAuth flow.
Out of scope: vulnerabilities in Ubuntu, nginx, Telegram or Google themselves; attacks that need an already-compromised server;
issues caused by sharing your own secrets.

## Supported versions

Only the latest release receives fixes. Use `sudo tgyt update`.

## If you leaked a secret

| Secret | What to do |
|---|---|
| Bot token | @BotFather → `/mybots` → your bot → *API Token* → *Revoke*; then `sudo tgyt config BOT_TOKEN` |
| Relay session string | Telegram → Settings → Devices → terminate the session; then `sudo tgyt relay` |
| API hash | my.telegram.org → regenerate; `sudo tgyt config API_HASH` (re-run `tgyt relay`) |
| Google client secret | Cloud Console → Credentials → reset secret; re-upload the JSON in *Settings* |
| Panel password | `sudo tgyt admin` |
| Fernet key / database backup | assume saved YouTube logins are exposed: revoke the app at <https://myaccount.google.com/permissions> for each Google account, create a new key, re-link channels |
| `SESSION_SECRET` | `sudo tgyt config` / edit the env file with a new random value (logs everyone out) |

## Design notes

See [docs/11-security.md](docs/11-security.md) for how secrets are stored and what the installer hardens.
