#!/usr/bin/env python3
"""Interactive helper that sets up the large-file RELAY for TG->YT Uploader.

Run it on the server (the installer does this for you) or on your own computer:

    python tools/generate_session.py                      # on a server: writes /etc/tgyt/tgyt.env
    python tools/generate_session.py --env-file my.env    # update a specific env file
    python tools/generate_session.py --out session.txt    # just save the string to a 600 file

What it does:
  1. logs in to a normal Telegram account (phone number, login code, 2FA password)
  2. lists your channels so you can pick the private relay channel (its -100... id)
  3. checks that your bot is an admin of that channel
  4. detects Telegram Premium and picks MAX_FILE_BYTES (4 GB Premium / 2 GB normal)
  5. stores USER_SESSION, RELAY_CHAT_ID and MAX_FILE_BYTES -- the session string is
     NEVER printed to the screen.

Needs only `pip install kurigram`. `tgcrypto` is an optional speed-up and is not required.
This file is self-contained on purpose (it must run on Windows, macOS and Linux without
the rest of the project).
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import re
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

DEFAULT_ENV_FILE = "/etc/tgyt/tgyt.env"
PREMIUM_MAX_FILE_BYTES = 4_294_967_296   # 4 GiB
NORMAL_MAX_FILE_BYTES = 2_147_483_648    # 2 GiB

BOT_TOKEN_RE = re.compile(r"^[0-9]{6,12}:[A-Za-z0-9_-]{30,50}$")
API_HASH_RE = re.compile(r"^[a-f0-9]{32}$")
API_ID_RE = re.compile(r"^[0-9]{1,10}$")
CHAT_ID_RE = re.compile(r"^-100[0-9]{5,}$")

INTRO = """
=====================  LARGE-FILE RELAY SETUP  =====================

Why is this needed?
  Telegram bots can only download files up to 20 MB. To accept bigger videos,
  the bot forwards each video into a PRIVATE channel, and a second, real
  Telegram account (the "relay account") downloads it from there over MTProto.
  Without this, every video over 20 MB is rejected.

What you need:
  - a Telegram account to act as the relay (your own is fine; Premium = 4 GB
    files, a normal account = 2 GB files)
  - a private channel that this account is in, with YOUR BOT added as an admin
    (Telegram -> New Channel -> Private -> Manage -> Administrators -> Add)

!! SECURITY WARNING !!
  The session string created here gives FULL ACCESS to that Telegram account
  (read messages, send messages, everything). It is stored only in the env file
  / a file readable by you alone, and is never shown on screen. Never share it,
  never commit it, and treat it like the account's password. You can revoke it
  any time: Telegram -> Settings -> Devices -> terminate the session.
====================================================================
"""


# --------------------------------------------------------------------------- helpers (pure, unit-tested)
def parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def update_env_text(text: str, updates: dict[str, str]) -> str:
    """Return ``text`` with KEY=value set for every key in ``updates`` (replace the
    first existing line, otherwise append). Values are written verbatim."""
    for key, value in updates.items():
        if re.search(r"[\r\n]", value):
            raise ValueError(f"refusing to write a multi-line value for {key}")
        pattern = re.compile(rf"(?m)^{re.escape(key)}=.*$")
        line = f"{key}={value}"
        if pattern.search(text):
            text = pattern.sub(lambda _m, line=line: line, text, count=1)
        else:
            if text and not text.endswith("\n"):
                text += "\n"
            text += line + "\n"
    return text


def bot_id_from_token(token: str) -> int:
    return int(token.split(":", 1)[0])


def max_file_bytes_for(is_premium: bool) -> int:
    return PREMIUM_MAX_FILE_BYTES if is_premium else NORMAL_MAX_FILE_BYTES


def valid_chat_id(value: str) -> bool:
    return bool(CHAT_ID_RE.match(value.strip()))


def bot_admin_verdict(member: dict, chat_type: str) -> tuple[bool, list[str]]:
    """Interpret a Bot API ChatMember. Returns (is_ok, problems)."""
    status = member.get("status")
    if status == "creator":
        return True, []
    if status != "administrator":
        return False, [f"the bot is '{status or 'not a member'}', it must be an ADMINISTRATOR of the channel"]
    problems = []
    if chat_type == "channel" and not member.get("can_post_messages", False):
        problems.append("the bot needs the 'Post messages' admin permission")
    if not member.get("can_delete_messages", False):
        problems.append("the bot needs the 'Delete messages' admin permission (it cleans up relay copies)")
    return not problems, problems


def write_private_file(path: Path, content: str) -> None:
    """Create/overwrite ``path`` readable by its owner only (0600 on POSIX)."""
    path = path.expanduser()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        try:
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    """Atomically update an env file, keeping its mode and owner."""
    st = path.stat()
    new_text = update_env_text(path.read_text(encoding="utf-8"), updates)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(new_text, encoding="utf-8", newline="\n")
    try:
        os.chmod(tmp, stat.S_IMODE(st.st_mode))
        if hasattr(os, "chown") and os.geteuid() == 0:
            os.chown(tmp, st.st_uid, st.st_gid)
    except OSError:
        pass
    os.replace(tmp, path)


# --------------------------------------------------------------------------- Bot API
def bot_api(token: str, method: str, **params) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=20) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            return json.load(exc)
        except Exception:
            return {"ok": False, "description": f"HTTP {exc.code}"}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "description": f"network error: {exc}"}


# --------------------------------------------------------------------------- prompts
def ask(prompt: str, validator=None, *, secret: bool = False, default: Optional[str] = None,
        error: str = "That doesn't look right, try again.") -> str:
    while True:
        shown = f"{prompt} [{default}]: " if default else f"{prompt}: "
        raw = (getpass.getpass(shown) if secret else input(shown)).strip()
        if not raw and default is not None:
            raw = default
        if raw and (validator is None or validator(raw)):
            return raw
        print(f"  {error}")


def yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        raw = input(f"{prompt} {suffix}: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False


def load_defaults(env_file: Optional[Path]) -> dict[str, str]:
    if env_file and env_file.is_file():
        try:
            return parse_env_text(env_file.read_text(encoding="utf-8"))
        except OSError as exc:
            print(f"(could not read {env_file}: {exc})")
    return {}


# --------------------------------------------------------------------------- Telegram login
async def login(app) -> None:
    from pyrogram.errors import (
        FloodWait, PasswordHashInvalid, PhoneCodeExpired, PhoneCodeInvalid,
        PhoneNumberInvalid, SessionPasswordNeeded,
    )

    print("\nStep 1/3 - log in to the RELAY account")
    print("  Enter the phone number in international format, e.g. +14155550123.")
    while True:
        phone = ask("  Phone number", lambda v: re.fullmatch(r"\+?[0-9 ()-]{7,20}", v) is not None,
                    error="Use digits with the country code, e.g. +14155550123.")
        phone = re.sub(r"[ ()-]", "", phone)
        try:
            sent = await app.send_code(phone)
            break
        except PhoneNumberInvalid:
            print("  Telegram says that phone number is invalid.")
        except FloodWait as exc:
            raise SystemExit(f"Telegram asks you to wait {exc.value} seconds before trying again.")
    print("  A login code was sent to your Telegram app (check the 'Telegram' service chat), or by SMS.")
    while True:
        code = ask("  Login code", lambda v: re.fullmatch(r"[0-9 -]{4,10}", v) is not None,
                   error="The code is 5 digits.").replace(" ", "").replace("-", "")
        try:
            await app.sign_in(phone, sent.phone_code_hash, code)
            return
        except SessionPasswordNeeded:
            break
        except PhoneCodeInvalid:
            print("  Wrong code, try again.")
        except PhoneCodeExpired:
            print("  That code expired. Run this tool again to get a fresh one.")
            raise SystemExit(1)
    print("  This account has two-step verification (2FA).")
    while True:
        password = getpass.getpass("  2FA password (hidden): ")
        try:
            await app.check_password(password)
            return
        except PasswordHashInvalid:
            print("  Wrong password, try again.")


async def pick_channel(app) -> tuple[int, str]:
    from pyrogram.enums import ChatType

    print("\nStep 2/3 - choose the relay channel")
    channels = []
    async for dialog in app.get_dialogs():
        chat = dialog.chat
        if chat.type in (ChatType.CHANNEL, ChatType.SUPERGROUP):
            channels.append(chat)
        if len(channels) >= 60:
            break
    if channels:
        print("  Your channels and groups (private ones have no @username):")
        for i, chat in enumerate(channels, 1):
            kind = "public " if chat.username else "private"
            print(f"   {i:>2}. [{kind}] {chat.title}   (id {chat.id})")
    else:
        print("  No channels found on this account. Create a PRIVATE channel first, add your bot as an")
        print("  admin, then run this tool again (or paste a -100... id below).")
    while True:
        raw = ask("  Number of the relay channel (or paste its -100... id)")
        if valid_chat_id(raw):
            chat_id = int(raw)
            title = next((c.title for c in channels if c.id == chat_id), "(typed manually)")
            return chat_id, title
        if raw.isdigit() and 1 <= int(raw) <= len(channels):
            chat = channels[int(raw) - 1]
            return chat.id, chat.title
        print("  Pick a number from the list, or a channel id that starts with -100.")


def check_bot_admin(bot_token: str, chat_id: int) -> bool:
    print("\nStep 3/3 - checking that your bot is an admin there")
    while True:
        chat = bot_api(bot_token, "getChat", chat_id=chat_id)
        member = bot_api(bot_token, "getChatMember", chat_id=chat_id, user_id=bot_id_from_token(bot_token))
        if not member.get("ok"):
            print(f"  Could not check: {member.get('description')}")
            print("  (Usually: the bot has not been added to that channel yet.)")
            ok, problems = False, []
        else:
            ctype = (chat.get("result") or {}).get("type", "channel")
            ok, problems = bot_admin_verdict(member["result"], ctype)
        if ok:
            print("  OK - the bot is an admin of the relay channel.")
            return True
        for p in problems:
            print(f"  - {p}")
        if not yes_no("  Fix that in Telegram, then check again?", True):
            return False


# --------------------------------------------------------------------------- main
async def run(args: argparse.Namespace) -> int:
    try:
        from pyrogram import Client
    except ImportError:
        print("The 'kurigram' package is missing. Install it with:\n    pip install kurigram")
        return 1

    print(INTRO)
    env_file = Path(args.env_file).expanduser() if args.env_file else (
        Path(DEFAULT_ENV_FILE) if Path(DEFAULT_ENV_FILE).is_file() else None)
    defaults = load_defaults(env_file)

    api_id = args.api_id or os.environ.get("TGYT_API_ID") or defaults.get("API_ID", "")
    api_hash = os.environ.get("TGYT_API_HASH") or defaults.get("API_HASH", "")
    bot_token = os.environ.get("TGYT_BOT_TOKEN") or defaults.get("BOT_TOKEN", "")

    if not API_ID_RE.match(api_id or ""):
        print("API ID and API hash come from https://my.telegram.org -> API development tools.")
        api_id = ask("API ID (digits)", API_ID_RE.match)
    if not API_HASH_RE.match(api_hash or ""):
        api_hash = ask("API hash (32 hex characters, hidden)", API_HASH_RE.match, secret=True)
    if not BOT_TOKEN_RE.match(bot_token or ""):
        bot_token = ask("Bot token from @BotFather (hidden)", BOT_TOKEN_RE.match, secret=True)

    # in_memory: no .session file is ever written to disk.
    app = Client("tgyt-relay-setup", api_id=int(api_id), api_hash=api_hash, in_memory=True)
    await app.connect()
    try:
        await login(app)
        me = await app.get_me()
        premium = bool(getattr(me, "is_premium", False))
        print(f"\n  Logged in as {me.first_name}. Telegram Premium: {'yes' if premium else 'no'}.")
        max_bytes = max_file_bytes_for(premium)
        print(f"  -> files up to {max_bytes // 1024**3} GB will be accepted"
              f" ({'Premium accounts can send/receive 4 GB' if premium else 'normal accounts are limited to 2 GB'}).")
        chat_id, title = await pick_channel(app)
        print(f"  Selected: {title}  ({chat_id})")
        if not check_bot_admin(bot_token, chat_id):
            print("\nThe relay will not work until the bot is an admin of that channel.")
            if not yes_no("Save the settings anyway?", False):
                return 1
        session = await app.export_session_string()
    finally:
        try:
            await app.disconnect()
        except Exception:
            pass

    updates = {"USER_SESSION": session, "RELAY_CHAT_ID": str(chat_id), "MAX_FILE_BYTES": str(max_bytes)}
    saved_to_env = False
    if env_file and not args.out:
        try:
            update_env_file(env_file, updates)
            saved_to_env = True
            print(f"\nSaved USER_SESSION, RELAY_CHAT_ID and MAX_FILE_BYTES to {env_file}.")
            print("Restart the service to apply:  sudo tgyt restart")
        except (OSError, PermissionError) as exc:
            print(f"\nCould not write {env_file} ({exc}). Re-run with sudo, or use --out FILE.")
    if not saved_to_env:
        out = Path(args.out or "tgyt_session.txt").expanduser()
        write_private_file(out, "\n".join(f"{k}={v}" for k, v in updates.items()) + "\n")
        print(f"\nSaved to {out} (readable only by you). Copy those 3 lines into /etc/tgyt/tgyt.env on the")
        print("server (e.g. `sudo tgyt config`), then delete the file. The session string was not displayed.")
    del session, updates
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", help=f"env file to update (default: {DEFAULT_ENV_FILE} if it exists)")
    parser.add_argument("--out", help="write the settings to this file (mode 600) instead of the env file")
    parser.add_argument("--api-id", help="Telegram API ID (otherwise read from the env file or asked)")
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(run(args)))
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled - nothing was saved.")
        sys.exit(130)


if __name__ == "__main__":
    main()
