#!/usr/bin/env python3
"""Application-level checks for `tgyt doctor`. Prints one JSON object per line:

    {"status": "ok|warn|fail", "name": "...", "detail": "...", "fix": "..."}

Stdlib + `cryptography` only; reads the env file directly (so it still works when the app's
own config validation would refuse to start). Never prints a secret. It does NOT open a second
Telegram connection with the relay session (that can upset Telegram while the service is using
the same session) -- membership is checked through the Bot API instead.

    python tools/doctor_checks.py [--env-file /etc/tgyt/tgyt.env]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sqlite3
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_ENV = os.environ.get("TGYT_ENV_FILE", "/etc/tgyt/tgyt.env")


PLAIN = False


def emit(status: str, name: str, detail: str = "", fix: str = "") -> None:
    if PLAIN:   # tab-separated for the bash renderer in `tgyt doctor`
        clean = [" ".join(str(x).split()) for x in (status, name, detail, fix)]  # no tabs/newlines inside a field
        print("\t".join(clean), flush=True)
    else:
        print(json.dumps({"status": status, "name": name, "detail": detail, "fix": fix}), flush=True)


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip().strip("'\"")
    return values


def bot_api(token: str, method: str, **params) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        with urllib.request.urlopen(url, data=urllib.parse.urlencode(params).encode(), timeout=15) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            return json.load(exc)
        except Exception:
            return {"ok": False, "description": f"HTTP {exc.code}"}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "description": f"network error: {exc}"}


def decode_session_user_id(session: str) -> int | None:
    """Pyrogram/Kurigram session strings are urlsafe-base64 of a fixed struct that ends with
    the account's user id. Returns None if the format is not recognised."""
    try:
        raw = base64.urlsafe_b64decode(session + "=" * (-len(session) % 4))
    except Exception:
        return None
    for fmt in (">BI?256sQ?", ">B?256sQ?", ">B?256sI?"):
        if struct.calcsize(fmt) == len(raw):
            return struct.unpack(fmt, raw)[-2]
    return None


def check_bot(env: dict[str, str]) -> None:
    token = env.get("BOT_TOKEN", "")
    if not token:
        return emit("fail", "Telegram bot token", "BOT_TOKEN is empty", "Run: sudo tgyt config BOT_TOKEN")
    res = bot_api(token, "getMe")
    if res.get("ok"):
        emit("ok", "Telegram bot token", f"valid - @{res['result'].get('username')}")
    else:
        emit("fail", "Telegram bot token", res.get("description", "rejected"),
             "Get a fresh token from @BotFather (/mybots -> API Token) and run: sudo tgyt config BOT_TOKEN")


def check_relay(env: dict[str, str]) -> None:
    session, chat = env.get("USER_SESSION", ""), env.get("RELAY_CHAT_ID", "")
    if not session and not chat:
        return emit("warn", "Large-file relay", "not configured - videos over 20 MB are rejected",
                    "Run: sudo tgyt relay")
    if not session or not chat:
        return emit("fail", "Large-file relay", "USER_SESSION and RELAY_CHAT_ID must both be set",
                    "Run: sudo tgyt relay")
    user_id = decode_session_user_id(session)
    if user_id is None:
        return emit("fail", "Relay session", "USER_SESSION is not a valid session string", "Run: sudo tgyt relay")
    emit("ok", "Relay session", "string is well-formed (a bad session would crash the service at start-up)")
    try:
        max_bytes = int(env.get("MAX_FILE_BYTES", "0"))
        emit("ok", "Max file size", f"{max_bytes / 1024**3:.0f} GB"
             + (" (Premium relay accounts can use 4 GB)" if max_bytes <= 2 * 1024**3 else ""))
    except ValueError:
        emit("fail", "Max file size", "MAX_FILE_BYTES is not a number", "Run: sudo tgyt config MAX_FILE_BYTES")
    token = env.get("BOT_TOKEN", "")
    if not token:
        return
    me = bot_api(token, "getMe")
    if not me.get("ok"):
        return
    bot_member = bot_api(token, "getChatMember", chat_id=chat, user_id=me["result"]["id"])
    if not bot_member.get("ok"):
        return emit("fail", "Relay channel - bot", bot_member.get("description", "unknown"),
                    "Add the bot to the relay channel as an administrator, or re-run: sudo tgyt relay")
    st = bot_member["result"]
    if st.get("status") not in ("administrator", "creator"):
        emit("fail", "Relay channel - bot", f"bot is '{st.get('status')}', must be administrator",
             "Channel -> Manage -> Administrators -> add the bot (Post + Delete messages)")
    elif st.get("status") == "administrator" and not (st.get("can_post_messages") and st.get("can_delete_messages")):
        emit("fail", "Relay channel - bot", "bot is admin but lacks Post and/or Delete messages",
             "Edit the bot's admin rights in the channel and enable both")
    else:
        emit("ok", "Relay channel - bot", "bot is an admin of the relay channel")
    user_member = bot_api(token, "getChatMember", chat_id=chat, user_id=user_id)
    if user_member.get("ok") and user_member["result"].get("status") in ("member", "administrator", "creator"):
        emit("ok", "Relay channel - relay account", "relay account is a member of the relay channel")
    else:
        emit("fail", "Relay channel - relay account",
             (user_member.get("description") or f"status {user_member.get('result', {}).get('status')}"),
             "Join the relay channel with the relay account, or re-run: sudo tgyt relay")


def check_db(env: dict[str, str]) -> None:
    db_path = Path(env.get("DB_PATH", "/var/lib/tgyt/tgyt.db"))
    if not db_path.is_file():
        return emit("fail", "Database", f"{db_path} does not exist yet", "Start the service once: sudo tgyt restart")
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        conn.execute("BEGIN IMMEDIATE")   # proves the DB is writable, then undone
        conn.execute("ROLLBACK")
        if quick != "ok":
            conn.close()
            return emit("fail", "Database", f"integrity check: {quick}", "Restore a backup: sudo tgyt restore")
        emit("ok", "Database", f"{db_path} is writable and healthy ({db_path.stat().st_size // 1024} KB)")
    except sqlite3.Error as exc:
        return emit("fail", "Database", str(exc), "Check ownership: sudo chown -R tgyt:tgyt /var/lib/tgyt")

    try:
        client = conn.execute("SELECT client_id, client_type FROM oauth_client WHERE id = 1").fetchone()
        if client:
            emit("ok", "Google OAuth client", f"uploaded ({client['client_type']} client)")
        else:
            emit("warn", "Google OAuth client", "not uploaded yet",
                 "Panel -> Settings (or Channels -> Add) -> upload the client_secret JSON. See docs/05-google-cloud.md")
        channels = conn.execute(
            "SELECT channel_title, status, scopes, google_email, refresh_token_enc FROM yt_channels").fetchall()
        if not channels:
            emit("warn", "Linked YouTube channels", "none linked yet", "Panel -> Channels -> Add a channel")
        else:
            bad = [c for c in channels if c["status"] != "active"]
            summary = ", ".join(f"{c['channel_title']} [{c['status']}]" for c in channels)
            emit("fail" if bad else "ok", "Linked YouTube channels", f"{len(channels)} linked: {summary}",
                 "Re-authorize the red ones: Panel -> Channels -> Re-authorize" if bad else "")
            nodelete = [c["channel_title"] for c in channels if "youtube.force-ssl" not in (c["scopes"] or "")]
            if nodelete:
                emit("warn", "Channel permissions", "no delete permission for: " + ", ".join(nodelete),
                     "Re-authorize them with every permission ticked if you want panel deletes to reach YouTube")
        _check_fernet(env, channels)
    except sqlite3.Error as exc:
        emit("fail", "Database content", str(exc), "Restart the service once so migrations run: sudo tgyt restart")
    finally:
        conn.close()


def _check_fernet(env: dict[str, str], channels) -> None:
    key_path = Path(env.get("FERNET_KEY_PATH", "/etc/tgyt/fernet.key"))
    try:
        from cryptography.fernet import Fernet, InvalidToken
        fernet = Fernet(key_path.read_bytes().strip())
    except FileNotFoundError:
        return emit("fail", "Encryption key", f"{key_path} is missing",
                    "Restore it from a backup (sudo tgyt restore). Without it saved YouTube tokens are unreadable.")
    except Exception as exc:  # noqa: BLE001 - report anything
        return emit("fail", "Encryption key", f"cannot load key: {type(exc).__name__}", "Restore it from backup")
    for c in channels[:1]:
        try:
            fernet.decrypt(c["refresh_token_enc"])
        except InvalidToken:
            return emit("fail", "Encryption key", "key does not match the stored YouTube tokens",
                        "You restored the database with a different key. Restore the matching fernet.key.")
    emit("ok", "Encryption key", "present" + (" and decrypts the stored tokens" if channels else ""))


def check_disk(env: dict[str, str]) -> None:
    jobs = Path(env.get("JOBS_DIR", "/var/lib/tgyt/jobs"))
    floor = int(env.get("MIN_FREE_DISK_BYTES", "5368709120") or 0)
    probe = jobs if jobs.exists() else jobs.parent
    free = shutil.disk_usage(probe).free
    gb = free / 1024**3
    if free < floor:
        emit("fail", "Disk space", f"{gb:.1f} GB free on the jobs volume, below the {floor / 1024**3:.0f} GB safety floor",
             "Free space or resize the disk; large videos will be refused until then")
    elif free < floor * 2:
        emit("warn", "Disk space", f"{gb:.1f} GB free - room for roughly {max(0, (free - floor) // (2 * 1024**3))} large videos",
             "Add disk space if you upload many multi-GB videos")
    else:
        emit("ok", "Disk space", f"{gb:.1f} GB free")
    if jobs.exists() and not os.access(jobs, os.W_OK):
        emit("fail", "Jobs directory", f"{jobs} is not writable", "sudo chown -R tgyt:tgyt /var/lib/tgyt")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=DEFAULT_ENV)
    parser.add_argument("--plain", action="store_true", help="tab-separated output instead of JSON lines")
    args = parser.parse_args()
    global PLAIN
    PLAIN = args.plain
    try:
        env = parse_env(Path(args.env_file))
    except OSError as exc:
        emit("fail", "Env file", f"cannot read {args.env_file}: {exc}", "Run this through: sudo tgyt doctor")
        sys.exit(1)
    for check in (check_bot, check_relay, check_db, check_disk):
        try:
            check(env)
        except Exception as exc:  # noqa: BLE001 - one broken check must not hide the others
            emit("fail", check.__name__, f"check crashed: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
