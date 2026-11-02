# 11. Security notes

## What is protected, and how

| Asset | Where it lives | Protection |
|---|---|---|
| Bot token, API hash, relay session string, session secret | `/etc/tgyt/tgyt.env` | mode **600**, owned by the `tgyt` service user; redacted in logs and in the panel's env view |
| YouTube refresh/access tokens, Google client secret, TOTP secrets | SQLite database | **Fernet-encrypted** (AES-128-CBC + HMAC) at rest |
| Fernet key | `/etc/tgyt/fernet.key` | mode **400**, never in the env file; included in every `tgyt backup` (without it the encrypted tokens are unreadable) |
| Panel password | database | **Argon2id** hash; never stored in a file (the installer creates the admin straight in the DB) |
| Install log | `/var/log/tgyt-install.log` | mode 600; tokens, hashes, session strings and typed passwords are masked |
| Uploaded videos | `/var/lib/tgyt/jobs` | mode 750; deleted after 24 h (configurable) |

## Hardening the installer applies

- Dedicated system user `tgyt` with **no login shell**.
- systemd sandbox: `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome`, narrow `ReadWritePaths`, kernel protections, **memory limit**.
- The service has **no** privileges beyond its own user: no sudo rule. The panel's *Restart* button simply makes the app exit cleanly, and systemd's `Restart=always` starts it again.
- **ufw** firewall: SSH, 80 (certificate challenge/redirect), and the panel port; everything else denied.
- **fail2ban** on SSH: 5 failures in 10 minutes → 1-hour ban. Bans go through ufw, which only blocks *new* connections, so a ban never cuts an SSH session that is already open.
  An existing `/etc/fail2ban/jail.d/tgyt.local` is never overwritten, so your own tuning survives a re-run.
  If you manage the server through a shared web-terminal gateway (one IP used by many customers), other people's failed logins can get that IP banned: keep a
  second way in (your SSH key from your own IP, or the provider's out-of-band console), or shorten `bantime`.
- HTTPS only (HSTS), Let's Encrypt certificate, auto-renewal.
- Optional **key-only SSH** (see below).
- Panel: Argon2, TOTP, CSRF, 12-hour `Secure`/`SameSite=Strict` cookies, lockout per account **and** per IP.

## Things only you can do

1. **Use two-factor** (`REQUIRE_TOTP=true`) — the panel is on the public internet.
2. **Back up** (`tgyt backup`) and keep a copy off-server. Encrypt it (`--encrypt`) if it leaves your control.
3. **Treat the relay session string like a password** — full access to that Telegram account. Prefer a dedicated account. Revoke in Telegram → Settings → Devices if you suspect a leak.
4. **Add only the Google accounts you trust** as test users.
5. **Keep Ubuntu updated** (`sudo apt update && sudo apt upgrade`; consider `unattended-upgrades`).
6. **Never share** your `tgyt.env`, `client_secret*.json`, `token.json`, the Fernet key, or a backup. Redact before posting logs — the app's own logs are already redacted.

## Hardening SSH (optional, safe)

The installer offers it at step 12. It will:
1. require you to open a **second terminal and log in with your SSH key** first;
2. refuse if no account has an authorized key;
3. write `/etc/ssh/sshd_config.d/00-tgyt-hardening.conf` (`PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PermitRootLogin no` — or `prohibit-password` if only root has a key);
   it's named `00-` so it wins over cloud-init's drop-in, which sorts later;
4. validate with `sshd -t`, reload (not restart), and **revert automatically** unless you type `ok` from the second login within 2 minutes.

Undo any time: `sudo rm /etc/ssh/sshd_config.d/00-tgyt-hardening.conf && sudo systemctl reload ssh`.

## Reducing exposure further

- Restrict the panel to your own IP: `sudo ufw delete allow 443/tcp && sudo ufw allow from YOUR.IP to any port 443 proto tcp` (keep 80 open for certificate renewal, or use a DNS-challenge setup).
- Put the panel behind a VPN such as Tailscale/WireGuard.

## Reporting a vulnerability

See [SECURITY.md](../SECURITY.md).
