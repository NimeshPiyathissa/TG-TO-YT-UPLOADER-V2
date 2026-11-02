# Contributing

Thanks for helping! Bug reports, docs fixes and focused pull requests are welcome.

The project is licensed under the GNU AGPL-3.0-only ([LICENSE](LICENSE)). By submitting a contribution (a pull request, patch or
suggested change) you license it under the same terms. The full setup, test and release workflow is in
the [developer guide](docs/12-development.md).

## Ground rules

- **Never commit secrets**: bot tokens, session strings, `client_secret*.json`, `token.json`, `.env` files, databases, Fernet keys, real domains/IPs/emails.
  CI runs gitleaks; a leaked credential must be revoked even if you delete the commit.
- Keep behaviour changes small and covered by tests. Don't change the quota, security or installer behaviour without discussing it in an issue first.
- Shell scripts must pass `shellcheck` and use LF line endings (enforced by `.gitattributes`). Scripts under `deploy/` run as root on users' servers — be conservative and idempotent.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt                          # tgcrypto is optional: on Windows skip it
pytest                                                       # ~2 minutes; `pytest -m slow` adds a 4 GB resumable-upload run
shellcheck -x -P deploy install.sh deploy/install.sh deploy/tgyt deploy/lib/*.sh
```

Run the app locally: copy `.env.example` to `.env`, put fake-but-valid values in it, create a Fernet key file, and `python -m bot.main`
(you need a real bot token and API credentials to start the Telegram client).

## What the tests cover

| File | Covers |
|---|---|
| `tests/test_queue.py`, `test_upload_resume.py`, `test_disk.py` | job lifecycle, resumable upload against a fake Google endpoint, retries, disk checks, sweeper |
| `tests/test_accounts.py`, `test_multichannel.py`, `test_link_diagnostics.py` | channel linking, Brand accounts, grouping, defaults, OAuth diagnostics |
| `tests/test_live_progress.py`, `test_notify.py` | SSE progress, admin notifications |
| `tests/test_installer_shell.py` | installer input validation, generated env file loads in the app, log redaction, panel redaction |
| `tests/test_tools.py` | session generator helpers, doctor checks, admin tool, migrations |

## Pull requests

1. Fork, branch, make the change with tests.
2. `pytest` and `shellcheck` must pass.
3. Update `CHANGELOG.md` (Unreleased section) and the docs if behaviour changed.
4. Describe *why* in the PR; screenshots for UI changes (with fake data).

## Testing the installer

The unit tests exercise the validators and config generation. The real end-to-end test needs a **fresh, empty Ubuntu 24.04 VPS** (never a server you care about):
run `install.sh`, then `tgyt doctor`, re-run the installer, `tgyt backup` / `restore`, `tgyt update`. Please note in your PR what you tested.

## Code style

Python: type hints, small functions, structured logging (`structlog`) with no secrets in log fields. Match the surrounding code. Shell: `set -Eeuo pipefail`, quote everything, use the helpers in `deploy/lib`.
