# 5. Google Cloud setup (YouTube API + OAuth client)

YouTube only allows uploads through an app registered with Google. **Everyone who installs this must create their own free Google Cloud project**
— there is no shared one, and you shouldn't want one (see [limits](08-limits.md)). It takes about 15 minutes and costs nothing.

You'll finish with a file called `client_secret_….json` that you upload in the admin panel.

> Google renames and rearranges these screens from time to time. The newer console groups the consent screen under **Google Auth Platform**
> (*Branding*, *Audience*, *Data Access*, *Clients*); the older one calls it **OAuth consent screen**. The steps below name both.

## 5.1 Create the project

1. Open <https://console.cloud.google.com> and sign in with the Google account that will manage the project (any account; it doesn't have to own the YouTube channels).
2. Top bar → project picker → **New Project** → name it e.g. `tgyt-uploader` → **Create**. Make sure it is selected afterwards.

## 5.2 Enable the YouTube Data API v3

1. Menu → **APIs & Services → Library**.
2. Search **YouTube Data API v3** → open it → **Enable**.

## 5.3 OAuth consent screen

1. Menu → **APIs & Services → OAuth consent screen** (or **Google Auth Platform → Get started**).
2. App name: anything (e.g. `TGYT Uploader`). User support email: yours. Developer contact email: yours.
3. **Audience / User type: External.**
4. **Data Access / Scopes → Add or remove scopes.** Add these (search by the URL part, or paste them under *Manually add scopes*):

   | Scope | Why |
   |---|---|
   | `https://www.googleapis.com/auth/youtube.upload` | upload videos |
   | `https://www.googleapis.com/auth/youtube.readonly` | read the channel name/thumbnail and the upload result |
   | `https://www.googleapis.com/auth/youtube.force-ssl` | delete a video from YouTube when you delete it in the panel (optional; without it deletes only happen locally) |
   | `openid`, `…/auth/userinfo.email` | show which Google account a channel belongs to |

5. **Test users → Add users:** add the Gmail address of **every Google account you'll link channels from** (including your own). Up to 100.
   While the app is in *Testing* status, only these people can sign in. **Forgetting this is the #1 cause of "Access blocked" errors.**
6. Leave the publishing status as **Testing**. (See [limits](08-limits.md): in Testing, Google expires logins after 7 days, so you'll re-authorize each channel weekly,
   unless you later publish the app, which needs Google's verification.)

## 5.4 Create the OAuth client (Web application)

1. Menu → **APIs & Services → Credentials → Create credentials → OAuth client ID**
   (or **Google Auth Platform → Clients → Create client**).
2. **Application type: Web application.** Name: anything.
3. **Authorized redirect URIs → Add URI** — this must match **exactly** (https, your hostname, no trailing slash):

   ```
   https://upload.example.com/oauth/callback
   ```
   - With the free sslip.io name: `https://203-0-113-10.sslip.io/oauth/callback`.
   - If you chose a non-443 port: `https://upload.example.com:8443/oauth/callback`.
   - The installer prints the exact string for your setup at the end, and the panel shows it on *Channels → Add a channel*.
   - *Advanced loopback mode only:* choose **Desktop app** instead; no redirect URI is needed.
4. **Create.** In the dialog click **Download JSON**. The file is called `client_secret_….apps.googleusercontent.com.json`. Keep it private.
   (It's a *Web client* JSON — not a "service account" key. Service accounts can never upload to YouTube; the panel rejects them.)

## 5.5 Upload it in the panel

Admin panel → **Channels → Link a channel** → **Upload client_secret.json**. The secret is stored encrypted. The same page shows the redirect URI to copy. Then link a channel:
[7. Linking channels](07-linking-channels.md).

## 5.6 About "private until audited"

Videos uploaded through a *new* API project are forced to **Private** by YouTube until the project passes Google's
**API compliance audit** ([form](https://support.google.com/youtube/contact/yt_api_form)). For personal use many people simply leave uploads private
and publish them from YouTube Studio. When (if) the audit passes, set **Project audited** in *Settings* (or `sudo tgyt config PROJECT_AUDITED true`).
The bot warns you about this on `/start` and after uploads.
