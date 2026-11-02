# Third-party notices

TG → YT Uploader V2 is licensed under the GNU AGPL-3.0-only ([LICENSE](LICENSE)). It includes, or installs, the third-party components below, each under its own
licence. Those licences continue to apply to those components.

## Included in this repository

| Component | Files | Licence | Notice |
|---|---|---|---|
| Bricolage Grotesque | `web/static/fonts/bricolage-grotesque-*.woff2` | SIL Open Font License 1.1 | Copyright 2022 The Bricolage Grotesque Project Authors (https://github.com/ateliertriay/bricolage) |
| Instrument Sans | `web/static/fonts/instrument-sans-*.woff2` | SIL Open Font License 1.1 | Copyright 2022 The Instrument Sans Project Authors (https://github.com/Instrument/instrument-sans) |
| Space Grotesk | `web/static/fonts/space-grotesk-*.woff2` | SIL Open Font License 1.1 | Copyright 2020 The Space Grotesk Project Authors (https://github.com/floriankarsten/space-grotesk) |
| Geist Mono | `web/static/fonts/geist-mono-*.woff2` | SIL Open Font License 1.1 | Copyright 2024 The Geist Project Authors (https://github.com/vercel/geist-font) |
| htmx 1.9.12 | `web/static/htmx.min.js` | Zero-Clause BSD (0BSD) | https://github.com/bigskysoftware/htmx |

The full SIL Open Font License text, with the copyright lines above, is in
[`web/static/fonts/OFL.txt`](web/static/fonts/OFL.txt). The fonts are served by the admin panel; under the OFL they may not be sold on
their own.

## Installed at setup time (not included in this repository)

The installer downloads these with `pip` from PyPI (versions pinned in `requirements.txt` and `requirements-optional.txt`).
They are used unmodified.

| Package | Licence |
|---|---|
| kurigram (Telegram MTProto client, imported as `pyrogram`) | LGPL-3.0-or-later |
| tgcrypto (optional) | LGPL-3.0-or-later |
| aiohttp | Apache-2.0 AND MIT |
| aiofiles, google-auth, google-api-python-client, python-multipart | Apache-2.0 |
| cryptography | Apache-2.0 OR BSD-3-Clause |
| structlog | MIT OR Apache-2.0 |
| aiosqlite, fastapi, pydantic, pydantic-settings, argon2-cffi, pyotp | MIT |
| uvicorn, jinja2, itsdangerous, python-dotenv, qrcode | BSD |

kurigram and tgcrypto are LGPL libraries: they are installed separately into the server's virtual environment and can be replaced by the user
with another compatible version, as the LGPL requires. This project does not modify or redistribute them.

System packages (nginx, certbot, restic, ffmpeg, fail2ban, ufw, …) come from Ubuntu's repositories under their own licences.
