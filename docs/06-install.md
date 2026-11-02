# 6. Running the installer

Before you start have ready: the VPS IP and SSH login ([2](02-get-a-vps.md)), a domain with an A record ([3](03-domain-and-dns.md)),
the bot token, API ID/hash and your user ID ([4](04-telegram-setup.md)). The Google part ([5](05-google-cloud.md)) can be done after.

## Start it

Log in to the server with SSH and run **one** of:

```bash
# A) one command (downloads the project to /opt/tgyt-src, then starts the installer)
curl -fsSL https://raw.githubusercontent.com/NimeshPiyathissa/TG-TO-YT-UPLOADER-V2/main/install.sh | sudo bash

# B) clone first, read it, then run
git clone https://github.com/NimeshPiyathissa/TG-TO-YT-UPLOADER-V2.git
cd TG-TO-YT-UPLOADER-V2 && sudo ./install.sh
```

Both download from GitHub without logging in, so they work while the repository is **public**. For a private repository use a read-only
deploy key or a copied release folder: [14. If the repository is private](14-releases-and-upgrades.md#if-the-repository-is-private).

Pin a version with `TGYT_REF=v1.0.1` (a tag), e.g. `curl -fsSL …/install.sh | sudo env TGYT_REF=v1.0.1 bash`. It is safe to run the installer again at any time — see [re-running](#re-running-and-changing-settings).

A progress bar `[3/13] ███░░░` shows where you are. Everything is also written (secrets removed) to `/var/log/tgyt-install.log`.

## The 13 steps and every question

| # | Step | What happens |
|---|---|---|
| 1 | **Checking your server** | Verifies Ubuntu 22.04/24.04/26.04, x86_64/arm64, ≥ 1 GB RAM, ≥ 8 GB free disk, systemd, root, internet access (Telegram, PyPI, Let's Encrypt), that nothing else is using ports 80/443, and detects the server's public IP. Stops with a clear message if something is wrong. |
| 2 | **Your settings** | The questions below. Nothing is installed until you confirm the summary. |
| 3 | System packages | python3, venv, ffmpeg, nginx, certbot, ufw, fail2ban, git… via apt (retries on network errors). |
| 4 | Service user and folders | Dedicated no-login user `tgyt`; `/var/lib/tgyt` (data), `/etc/tgyt` (secrets). Adds a 2 GB swap file on small servers. |
| 5 | Application files | Copied to `/opt/tgyt-uploader`; a source copy is kept in `/opt/tgyt-src` for updates; installs the `tgyt` command. |
| 6 | Python environment | Virtualenv and **pinned** dependencies. (`tgcrypto`, an optional speed-up, is attempted and skipped if it can't build.) |
| 7 | Keys and configuration | Generates the **Fernet key** and the session secret, writes `/etc/tgyt/tgyt.env` (mode 600, owner `tgyt`) and creates your admin account directly in the database — the panel password is never written to a file. |
| 8 | System service | systemd unit (`Restart=always`, memory limit, sandboxing), starts it and waits for it to be healthy. |
| 9 | Web server and HTTPS | nginx reverse proxy (with live-progress streaming) and a free Let's Encrypt certificate, auto-renewing. |
| 10 | Firewall and protection | ufw allows only SSH, 80 and the panel port; fail2ban guards SSH. |
| 11 | Large-file relay | Optional guided Telegram login ([4.4](04-telegram-setup.md#44-the-relay-channel-only-for-videos-over-20-mb)). |
| 12 | Optional: harden SSH | Key-only login. Only offered after you confirm a key login works, and auto-reverts if you don't confirm. |
| 13 | Checking everything | Runs `tgyt doctor` and prints your panel address, the exact Google redirect URI and next steps. |

### Questions in step 2

Each question re-asks until the answer is valid. Secrets are typed hidden (nothing shows) and never logged.

1. **Web address** — `1` your own domain (recommended), `2` free `sslip.io` name, `3` advanced no-hostname mode.
   - *Domain/subdomain:* e.g. `upload.example.com` (lowercase, no `https://`).
   - The installer then **checks your DNS A record against this server's IP**. If it doesn't match it shows the exact record to add, and you can press Enter to re-check,
     `w` to wait up to 10 minutes automatically, or `s` to skip (not recommended).
2. **Email for Let's Encrypt** — optional; only for expiry warnings.
3. **Bot token** — from @BotFather. It's checked live with Telegram (`getMe`) and the bot's @username is shown.
4. **API ID** (digits) and **API hash** (32 hex characters) — from my.telegram.org.
5. **Your Telegram ID** — from @userinfobot; this becomes the owner.
6. **Admin username and password** — password is hidden, typed twice, and must be ≥ 12 characters mixing at least 3 of lowercase / UPPERCASE / digits / symbols.
   **Require two-factor (TOTP)?** — recommended. On first login the panel shows a QR code to scan with Google Authenticator, Aegis, 1Password, etc.
7. **YouTube region code** — two capital letters (US, GB, DE, LK…) used for YouTube category lists.
   **Max file size** — in bytes; default 2 GB. (The relay tool sets 4 GB automatically if the relay account has Premium.)
8. **Set up the relay now?** — yes/no ([what is it?](04-telegram-setup.md#44-the-relay-channel-only-for-videos-over-20-mb)).
9. **Firewall? fail2ban? nightly backups?** — all default to yes.

Finally you see a summary (secrets masked) and confirm.

## Unattended installs

For automation, copy `deploy/install.conf.example`, fill it in, protect it (`chmod 600`) and run:

```bash
sudo ./install.sh --config /root/install.conf         # implies non-interactive
# or with environment variables:
sudo TGYT_ACCESS_MODE=sslip TGYT_BOT_TOKEN=... TGYT_API_ID=... TGYT_API_HASH=... TGYT_OWNER_ID=... \
     TGYT_ADMIN_PASSWORD=... ./install.sh --non-interactive
```

Missing or invalid values stop the run with the name of the setting. The relay login needs a human (phone code), so run `sudo tgyt relay` afterwards,
or supply a pre-made `TGYT_USER_SESSION` + `TGYT_RELAY_CHAT_ID` with `TGYT_SETUP_RELAY=preset`. **Delete the config file when done** — it holds your secrets.

## When it finishes

You'll see your panel address, login name, and the **exact redirect URI** to paste into Google Cloud. Then:

1. Finish [Google Cloud setup](05-google-cloud.md) if you haven't, upload the JSON in *Settings*.
2. [Link a channel](07-linking-channels.md).
3. In Telegram send `/start` to your bot.
4. `sudo tgyt backup` and copy the file somewhere safe.
5. `sudo tgyt doctor` any time to re-check.

## Re-running and changing settings

The installer is **idempotent**. Run it again and, if it finds an existing installation, it offers:
1. **Keep my settings** and just repair/update the installed files (default; nothing is overwritten),
2. **Change some settings** (previous env file is copied to `/var/backups/tgyt` first),
3. Cancel.

It never overwrites the database, the Fernet key or an existing admin account. To change a single value use `sudo tgyt config KEY`.
To change the domain: change it via the installer (option 2) so nginx and the certificate follow, then update the redirect URI in Google Cloud.

## If it stops

The message names the failing step and what to do. Typical fixes: wrong DNS, port 80 blocked by the provider's firewall, a busy apt lock
(wait a minute). Fix it and just run the installer again — completed work is skipped. More in [troubleshooting](10-troubleshooting.md).
