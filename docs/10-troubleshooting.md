# 10. Troubleshooting

**First, always:** `sudo tgyt doctor` — it checks everything and prints a fix next to each problem. The install log is `/var/log/tgyt-install.log`,
the service log is `sudo tgyt logs -n 100`. (All secrets are redacted in both.)

- [DNS not resolving / installer says the record is wrong](#dns)
- [SSL / certificate failure](#ssl)
- [OAuth errors (redirect_uri_mismatch, access_denied, test user missing…)](#oauth-errors)
- [Large files: "20 MB" errors and relay errors](#relay)
- [Quota exhausted](#quota)
- [Service won't start](#service)
- [Can't log in to the panel](#panel-login)
- [Locked out of SSH](#ssh-lockout)
- [Uploads stay private / short videos only](#youtube-limits)

## <a id="dns"></a>DNS not resolving

Symptoms: the installer waits at the DNS check, or says `does not resolve yet` / `currently points to <other IP>`.

1. The record must be an **A record** with your server's IPv4: Name `upload` (or `@`), Value `203.0.113.10`. See [3](03-domain-and-dns.md).
2. Check what the world sees: `nslookup upload.example.com 1.1.1.1` (should show your IP). Your own computer may cache old answers; the installer asks public resolvers (1.1.1.1 / 8.8.8.8).
3. **Cloudflare:** set the record to *DNS only* (grey cloud).
4. Remove conflicting records for the same name (extra A records, or an `AAAA` pointing elsewhere).
5. New records usually work within minutes; some registrars take up to an hour. Choose `w` in the installer to wait automatically.
6. Typed the domain wrong? Run `nslookup` on exactly what you typed. Use lowercase, no `https://`.

## <a id="ssl"></a>SSL / certificate failure

Symptoms: *Let's Encrypt could not issue a certificate*, browser says "not secure", `tgyt doctor` says HTTPS failed.

| Cause | Fix |
|---|---|
| DNS not pointing here yet | see above, then re-run the installer |
| **Port 80 blocked** | Open TCP **80** and **443** in your provider's firewall/security group, and in ufw (`sudo ufw allow 80/tcp`). Let's Encrypt must reach port 80 even though the panel uses 443. |
| Something else is on port 80/443 | `sudo ss -ltnp 'sport = :80'`; stop Apache or another web server |
| Rate limit (too many tries for the same name) | Wait an hour (failed validations) or a week (duplicate certificates); meanwhile the panel works with a self-signed certificate |
| `sslip.io` unreachable from the server | choose a real domain |

After fixing, **re-run the installer** (choose *Keep my settings*): it retries issuance and rewrites nginx. Check renewal with `sudo tgyt doctor --deep`
(or `sudo certbot renew --dry-run`). Certificates renew automatically via `certbot.timer`.

## <a id="oauth-errors"></a>OAuth errors

| Error shown by Google / the panel | Meaning and fix |
|---|---|
| **`redirect_uri_mismatch`** | The redirect URI in Google Cloud isn't *exactly* the one the app uses. Copy the string shown at *Channels → Add a channel* (or printed by the installer) into Cloud Console → Credentials → your Web client → *Authorized redirect URIs*. Must be `https`, same host, same port if not 443, `/oauth/callback`, no trailing slash. Wait a minute after saving. |
| **`access_denied`** / "Access blocked: *app* has not completed the Google verification process" | The Google account you signed in with isn't a **Test user**. Cloud Console → OAuth consent screen / Audience → *Test users → Add users* → add that Gmail. (Max 100.) Then retry. |
| "This app isn't verified" screen | Expected. Click **Advanced → Go to … (unsafe)**. |
| **`invalid_client`** / "The OAuth client was not found" | Wrong or deleted client. Download the JSON again and re-upload it in *Settings*. Make sure it's a **Web application** client (Desktop only in loopback mode). |
| "Service accounts can't upload to YouTube" | You uploaded a service-account key. Download an **OAuth client ID** JSON instead. |
| `youtubeSignupRequired` / "no YouTube channel" | That Google account has no channel; create one at youtube.com first. |
| "No new channel was added" | You signed in with an account that doesn't *own* the channel (invited Studio managers don't count). See [7](07-linking-channels.md). |
| `invalid_grant` / channel turns red "needs re-auth" | Login expired or revoked. In *Testing* status Google expires logins every 7 days: Channels → **Re-authorize**. |
| "Missing permission" / can't delete videos | A permission box was unticked. Re-authorize and leave every box ticked. |
| Linking worked but `uploads over 15 min` fail | Phone-verify the channel at youtube.com/verify. |

Useful diagnostics: `sudo tgyt logs -n 200 | grep -i oauth` shows the request scopes and callback (codes and tokens are redacted).

## <a id="relay"></a>Large files and the relay

| Symptom | Fix |
|---|---|
| Bot says the file is **over 20 MB** and can't be fetched | The relay isn't configured. `sudo tgyt relay`. `tgyt doctor` shows *Large-file relay: not configured*. |
| `tgyt relay` can't send the login code | Phone number needs the country code (`+1…`). The code arrives **in the Telegram app** (chat "Telegram"), not SMS, if the account is logged in elsewhere. FloodWait = wait the stated seconds. |
| Doctor: *bot is 'member', must be administrator* / *lacks Post and/or Delete* | Channel → Manage → Administrators → add the bot, enable **Post messages** and **Delete messages**. |
| Doctor: *relay account is not a member* | Join the relay channel with the relay account (or run `tgyt relay` again and pick the right channel). |
| Service crash-loops with `AUTH_KEY…` / `SESSION_REVOKED` / `USER_DEACTIVATED` | The session was terminated (Telegram → Devices) or the account was banned. Run `sudo tgyt relay` to create a new session. Never use the same session string on two servers at once. |
| Bot stopped answering after a token change; log shows `SESSION_REVOKED` or `AUTH_KEY_UNREGISTERED` | The bot's saved login belongs to the old token. Set the token with `sudo tgyt config BOT_TOKEN` (it moves the old login aside), not by editing the env file. Already edited by hand? `sudo systemctl stop tgyt`, rename `/var/lib/tgyt/tgyt-bot.session` (e.g. add `.old`), `sudo systemctl start tgyt`. |
| File larger than 2 GB rejected | The relay account isn't Premium. Premium gives 4 GB. `tgyt config MAX_FILE_BYTES` can't exceed what Telegram allows the account. |
| Bot messages show plain emoji instead of animated ones; log has `fmt.custom_emoji_removed_by_telegram` | The bot's owner account has no Telegram Premium (or it expired). Telegram only lets a bot send custom emoji if its owner has Premium or it has a Fragment username ([4.1](04-telegram-setup.md#41-create-the-bot-and-get-its-token-botfather)). Renew Premium on the account that owns the bot in BotFather, or transfer the bot to a Premium account. No app change is needed. |
| Download stuck "waiting for disk space" | Not enough free disk (file × 1.2 + 5 GB). Free space (`tgyt status`), or wait for other jobs to finish. |
| `FLOOD_WAIT` in logs | Telegram rate limit; the app waits and continues. |

## <a id="quota"></a>Quota exhausted

The YouTube API allows 10,000 units per project per day and an upload costs 1,600 ([details](08-limits.md)). Symptoms: `quotaExceeded` in the log, uploads wait/fail with
"quota exhausted; resets in N h". It resets at midnight Pacific Time. Options: wait; upload fewer videos; apply to Google for a quota extension.
Do **not** spin up extra Cloud projects (against YouTube's terms). Check real usage in Cloud Console → YouTube Data API v3 → *Quotas*.

## <a id="service"></a>Service won't start

```bash
sudo tgyt status
sudo tgyt logs -n 80
```

| Log message | Fix |
|---|---|
| `invalid configuration` + a field name | A value in `/etc/tgyt/tgyt.env` is wrong. `sudo tgyt config` lists them; fix with `sudo tgyt config KEY`. |
| `no admin web-UI user exists yet` | Create one: `sudo tgyt admin`. |
| `Fernet key not found` | `/etc/tgyt/fernet.key` is missing — restore from backup (`tgyt restore`). Never generate a new one if the database has channels in it: they would become unreadable. |
| `Address already in use` | Another process uses port 8001 (or the panel port in loopback mode): `sudo ss -ltnp`. |
| `Unauthorized` / `ACCESS_TOKEN_INVALID` from Telegram | The bot token was revoked. `sudo tgyt config BOT_TOKEN`. |
| `database is locked` / permission errors | `sudo chown -R tgyt:tgyt /var/lib/tgyt` |
| Restarts repeatedly | `systemctl status tgyt` shows `MemoryMax`? On tiny servers keep swap enabled (the installer adds it); lower `MAX_CONCURRENT_DOWNLOADS`. |

## <a id="panel-login"></a>Can't log in to the panel

- Wrong password / locked after 5 failures (15-minute lockout): wait, or `sudo tgyt admin` → reset (also clears the lockout).
- Lost your authenticator: `sudo tgyt admin` → option 2.
- Browser says the certificate is invalid: see [SSL](#ssl). Loopback mode uses a self-signed certificate (warning expected).
- Page loads but login just reloads: your system clock must be right (cookies/TOTP); and the address must be `https://`.

## <a id="ssh-lockout"></a>Locked out of SSH

Most common after hardening SSH or enabling the firewall.

1. **Don't panic — the installer's SSH hardening reverts itself** if you don't confirm a working second login within 2 minutes, and it refuses to run without a key present.
2. Use your provider's **web console / VNC / "Serial console"** (every VPS provider has one) to log in as root there.
3. Undo SSH hardening: `sudo rm /etc/ssh/sshd_config.d/00-tgyt-hardening.conf && sudo systemctl reload ssh`.
4. Firewall blocking SSH on a custom port: `sudo ufw allow <port>/tcp` (or `sudo ufw disable` temporarily).
5. fail2ban banned your IP after failed logins: `sudo fail2ban-client set sshd unbanip YOUR.IP` (the ban expires after an hour anyway).
   Sessions that were already open keep working during a ban, so you can unban yourself from one of them.
6. Lost the SSH key: add a new public key through the provider's console/rescue mode to `~/.ssh/authorized_keys`.

## <a id="youtube-limits"></a>Uploads stay Private / short videos only

Private-until-audited and the 15-minute cap are YouTube rules — see [8](08-limits.md).

## <a id="backups"></a>Off-site backup problems

| Message / symptom | Cause and fix |
|---|---|
| `Could not use the bucket` during `tgyt offsite setup` | Wrong endpoint (copy it from the bucket's details, e.g. `s3.us-west-004.backblazeb2.com`), wrong bucket name, or the application key isn't allowed to read **and** write that bucket. Create a new key limited to the bucket and run setup again. |
| `wrong password or no key found` | The bucket already holds a repository made with a different encryption password. Use the original password, or a new, empty bucket. |
| Telegram message "nightly backup FAILED" | `sudo journalctl -u tgyt-backup -n 50` shows which step failed. Then `sudo tgyt offsite run` to retry by hand. |
| `tgyt doctor`: off-site backup N days old | The timer isn't running (`sudo tgyt backup schedule on`) or every night fails (see the line above). |
| `./MANIFEST.txt: FAILED` / *Checksum mismatch* on a backup made with 1.0.0 | A 1.0.0 bug recorded a wrong checksum for the manifest itself; the data is fine. After `sudo tgyt update` the check skips that line and still verifies every real file. Any other file named as FAILED means that backup really is damaged: use an older one. |
| Lost the encryption password | Existing off-site backups can't be decrypted by anyone. Make a new, empty bucket and run `sudo tgyt offsite setup` again, then save the new password. |

Test a restore at any time without changing anything: `sudo tgyt offsite restore-test`.

## Still stuck?

Run `sudo tgyt doctor` and open an issue with its output (secrets are already hidden). Never paste your env file, bot token, session string or `client_secret` JSON.
