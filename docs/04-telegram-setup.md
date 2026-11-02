# 4. Telegram setup

You need four things from Telegram. Keep them in a notes file for the installer (never post them anywhere public).

## 4.1 Create the bot and get its token (BotFather)

1. In Telegram, open **@BotFather** (the one with the blue check).
2. Send `/newbot`. Choose a display name, then a username ending in `bot` (e.g. `my_uploader_bot`).
3. BotFather replies with a token that looks like `123456789:AAH...`. **That is your bot token.** Treat it like a password.
   - Lost it or leaked it? `/mybots` → your bot → *API Token* → *Revoke current token*, then on the server
     `sudo tgyt config BOT_TOKEN` (hidden prompt) and answer **y** to restart. The bot is offline only between the revoke and the restart.
4. Optional but nice: `/setdescription`, `/setuserpic`, and `/setcommands` with:
   ```
   start - Welcome
   help - How it works
   status - Bot health and quota
   channels - Linked YouTube channels
   addyt - Add a YouTube channel
   removeyt - Remove a channel
   jobs - Active and recent uploads
   cancel - Cancel an upload
   id - Show your Telegram ID
   ```
5. **Animated (Premium) emoji in the bot's messages** need the bot's owner (the account that created it in BotFather) to have
   **Telegram Premium**, or the bot to have a collectible username bought on Fragment. Telegram decides this per bot when each
   message is sent. Without it, Telegram removes the custom emoji and users see the normal emoji, with everything else working.
   Users don't need Premium to see them. Once the owner has Premium again, new messages show animated emoji with no
   changes to the app. Messages sent earlier stay plain. The log shows `fmt.custom_emoji_removed_by_telegram` or `fmt.custom_emoji_delivered`.

## 4.2 API ID and API hash (my.telegram.org)

These identify *your application* to Telegram (needed for the large-file relay and for the bot library).

1. Go to <https://my.telegram.org> and log in with your phone number (a code arrives in Telegram).
2. Click **API development tools**.
3. Fill the form: App title and short name can be anything (e.g. `TGYT Uploader` / `tgytup`). Platform: *Other* (or Desktop).
4. You get **App api_id** (a number) and **App api_hash** (32 letters/digits). Copy both.

If the page shows an error, try again later or without a VPN; Telegram is picky about this form.

## 4.3 Your Telegram user ID (the owner)

Open **@userinfobot** in Telegram and press *Start*. It replies with `Id: 123456789`. That number is your **owner ID**: the account that is
always allowed, and the only one that can't be locked out. You can also message your own bot `/id` after it is running.

## 4.4 The relay channel (only for videos over 20 MB)

Telegram bots can only download files up to **20 MB**. To accept bigger videos, a *normal Telegram account* (the "relay account") downloads
them instead. The bot forwards each incoming video into a **private channel** that both the bot and the relay account belong to;
the relay account downloads it from there; the bot deletes the forwarded copy.

You need:

1. **A relay account.** Your own account works. **Telegram Premium** on that account raises the limit from 2 GB to **4 GB**.
   (Use an account you control. The session you create gives full access to it; see the warning below.)
2. **A private channel**: Telegram → *New Channel* → name it (e.g. "tgyt relay") → **Private** → create. Add the relay account if it isn't the creator.
3. **Add your bot as an administrator** of that channel: channel → *Manage* → *Administrators* → *Add Administrator* → search your bot.
   Enable **Post messages** and **Delete messages** (the bot posts the forwarded copy and cleans it up).
4. The installer (or `sudo tgyt relay` later) runs a guided login: phone number → code → 2FA password if you have one →
   it lists your channels so you pick the relay channel and shows its `-100…` ID → it checks the bot is an admin there.

> ⚠️ **The session string created by this step gives full access to the relay Telegram account** (reading and sending messages, joining chats…).
> It is saved only into `/etc/tgyt/tgyt.env` (mode 600) and is never displayed. Never share it, never commit it, and you can revoke it any time in
> Telegram → *Settings → Devices*. For extra safety use a dedicated account rather than your main one.

Premium vs normal: the generator detects Premium automatically and sets `MAX_FILE_BYTES` to 4 GB or 2 GB. A non-Premium account simply can't
download files over 2 GB, so don't raise the limit by hand.

You can skip the relay now: everything else works, and videos over 20 MB are rejected with a clear message until you run `sudo tgyt relay`.

## 4.5 Using the generator on your own computer (optional)

```bash
pip install kurigram            # tgcrypto is NOT required (it is only a speed-up)
python tools/generate_session.py --out tgyt_session.txt
```

It works on Windows, macOS and Linux and writes the three lines (`USER_SESSION`, `RELAY_CHAT_ID`, `MAX_FILE_BYTES`) into a file only you can read.
Copy them into the server's env file with `sudo tgyt config` (or paste them into `/etc/tgyt/tgyt.env`) and delete the local file.
