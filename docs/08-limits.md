# 8. Limits — stated honestly

Read this before you promise anyone "unlimited uploads". Most limits come from YouTube and Telegram, not from this software.

## You need your own Google Cloud project

Uploading to YouTube requires API credentials registered to a Google Cloud project. Those credentials carry the project's quota and its
verification status. Because quota and audit status belong to the project, **every installer must create their own project** ([guide](05-google-cloud.md));
a shared project would share one tiny quota between everyone. Nothing is hidden: the project is yours, free, and under your control.

## Daily quota: about 6 uploads per day (per project)

- The YouTube Data API gives a new project **10,000 quota units per day**, shared by **all channels and all Google accounts** linked to that project.
- One video upload (`videos.insert`) costs **1,600 units**, so the default is roughly **6 uploads per day**. Other calls are cheap but not free
  (for example `videos.delete` and `thumbnails.set` cost 50 each; reading a list costs 1).
- The quota resets at **midnight Pacific Time**.
- You can **request more quota** from Google (the YouTube API *quota extension* form, which also needs the compliance audit).
  Check real usage in Cloud Console → APIs & Services → YouTube Data API v3 → *Quotas*.
- **Do not create extra projects or OAuth clients to multiply quota.** YouTube's API Services terms forbid it, and it risks getting your projects shut down.
  The panel deliberately uses one OAuth client for everything.

> Note: the "uploads left today" counter in the bot and panel is the app's own bookkeeping and does not replace the figures in Google Cloud Console.
> If they differ, trust Google's number.

## Uploads stay Private until Google audits your project

Videos uploaded through a new API project are forced to **Private** by YouTube, whatever privacy you choose, until the project passes the
**YouTube API Services compliance audit**. For personal use, upload privately and publish from YouTube Studio. After the audit passes, set
**Project audited** in *Settings* to `true`.

## 15-minute cap on unverified channels

YouTube limits channels that haven't been **phone-verified** to videos up to 15 minutes. Verify each channel once at <https://www.youtube.com/verify>.
The bot warns before uploading, not after it fails.

## Google "Testing" mode

An OAuth consent screen in *Testing* status allows at most **100 test users** and **expires refresh tokens after 7 days**
(you re-authorize channels weekly). Moving to *In production* removes both limits but, because the YouTube scopes are classed as sensitive,
requires Google's OAuth verification review.

## Telegram

| Limit | Value |
|---|---|
| Bot API download | 20 MB (the reason the relay exists) |
| With the relay, normal account | up to **2 GB** |
| With the relay, Telegram **Premium** account | up to **4 GB** |
| YouTube file size / type | up to 256 GB, `video/*` |

## Server

- Each video is stored on the server's disk while it uploads. Roughly: free space ÷ (file size × 1.2) concurrent files, after a 5 GB safety margin.
  Big videos wait for space instead of failing. Set `MAX_CONCURRENT_DOWNLOADS` accordingly.
- Upload speed is limited by your VPS's network and YouTube.
