# 7. Linking YouTube channels (including Brand Accounts)

One Google `client_secret.json` (uploaded once under *Channels → Link a channel*) covers **every** account and channel you will ever link. Each channel you link is its own Google
consent and gets its own encrypted login, stored per YouTube channel ID — linking a second Brand-Account channel never overwrites the first.

## Link a channel, step by step

Prerequisites: [Google Cloud](05-google-cloud.md) is set up, the JSON is uploaded, and the Google account you'll sign in with is listed under **Test users**.

1. Panel → **Channels** → **Add a channel** (or `/addyt` in the bot, which sends you the link).
2. Google shows an **account chooser** — pick the Google account that **owns** the channel.
3. **"Google hasn't verified this app"** — expected, because your private project isn't verified. Click **Advanced → Go to *your-app* (unsafe)**.
   You are only trusting your own server.
4. Google lists the permissions. **Leave every box ticked** (upload, view, manage/delete videos, email) and press **Continue**.
5. If that Google account has Brand Accounts, Google shows the **channel chooser**: choose the channel you want to add *now*.
6. You land back in the panel with a success message and the channel appears, grouped under its Google account.

Linking a channel that is already linked refreshes it (and says so) instead of making a duplicate.

## Brand Accounts and several channels

- A Google account can own several channels; Google offers **one channel per consent**. So three channels = three links. Use the
  **"Add another channel from this account"** button on an account's card: it pre-selects the account so Google jumps to that account's channel chooser.
  **"Link a channel from another Google account"** starts with the account chooser.
- The panel, `/channels` and the bot's channel picker group channels under their Google account. Set a **default** channel (listed first) and an optional **display label** on the Channels page.
- If a channel's login breaks it shows a red badge, is skipped in the picker, and the owner is told to re-authorize it (Channels → Re-authorize).

## "Why can't I link a channel I only manage in YouTube Studio?"

If you were *invited* as a manager through YouTube Studio → Settings → **Permissions**, that access is **not available through the YouTube API**. YouTube's own help says
people added through channel permissions "can't manage via YouTube APIs". Google simply never offers such a channel in the chooser for your account, and you'll see
"No new channel was added".

What works: sign in with the Google account that **owns** the channel (shown as *Owner* in Studio → Permissions, or the Brand Account's owner/manager in that account's Google settings)
and link it from there. This is a Google API limit — it can't be worked around from this app, and creating extra Google projects doesn't help (and violates YouTube's terms).

## If Google skips the chooser or signs into the wrong account

- Try a private/incognito window signed in to only that account.
- Remove the app's access at <https://myaccount.google.com/permissions> and link again.
- Make sure the account is a **Test user** (see [errors](10-troubleshooting.md#oauth-errors)).

## Re-authorizing every 7 days

While your OAuth consent screen is in **Testing**, Google expires refresh tokens after **7 days**. Channels then turn red ("needs re-authorization"), the bot DMs the owner,
and you click *Re-authorize* (two clicks, same flow as above). Publishing the app removes this but requires Google's OAuth verification (the YouTube scopes count as sensitive).

## Advanced: no-hostname (loopback) mode

Only if you installed with option 3: the Add-channel page shows an `ssh -L` tunnel command and an offline helper (`tools/link_channel.py`) you run on your own computer;
it writes a `token.json` you upload in the panel. Treat that file like a password and delete it afterwards.
