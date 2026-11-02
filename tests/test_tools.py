"""Tests for tools/generate_session.py, tools/doctor_checks.py, tools/admin_user.py, tools/migrate_db.py."""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import shutil
import sqlite3
import stat
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"tool_{name}", ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gs = load("generate_session")
dc = load("doctor_checks")


def fake_session(user_id: int = 4242, fmt: str = ">BI?256sQ?") -> str:
    raw = struct.pack(fmt, 2, 1234567, False, b"\x01" * 256, user_id, False)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


# ------------------------------------------------------------------ generate_session
def test_update_env_text_replaces_appends_and_keeps_comments():
    text = "# c\nUSER_SESSION=\nRELAY_CHAT_ID=\nOTHER=1\n"
    out = gs.update_env_text(text, {"USER_SESSION": "abc", "RELAY_CHAT_ID": "-100123456", "MAX_FILE_BYTES": "4294967296"})
    assert out == "# c\nUSER_SESSION=abc\nRELAY_CHAT_ID=-100123456\nOTHER=1\nMAX_FILE_BYTES=4294967296\n"


def test_update_env_text_handles_values_with_special_chars_and_missing_newline():
    out = gs.update_env_text("A=1", {"A": r"x\1 y&z", "B": "2"})
    assert out == "A=x\\1 y&z\nB=2\n"


def test_update_env_text_rejects_newline_injection():
    with pytest.raises(ValueError):
        gs.update_env_text("A=1\n", {"A": "x\nEVIL=1"})


def test_update_env_file_keeps_mode(tmp_path):
    f = tmp_path / "t.env"
    f.write_text("USER_SESSION=\n", encoding="utf-8")
    if os.name != "nt":
        f.chmod(0o600)
    gs.update_env_file(f, {"USER_SESSION": "zzz"})
    assert f.read_text(encoding="utf-8") == "USER_SESSION=zzz\n"
    if os.name != "nt":
        assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_write_private_file_is_0600(tmp_path):
    p = tmp_path / "s.txt"
    gs.write_private_file(p, "USER_SESSION=secret\n")
    assert stat.S_IMODE(p.stat().st_mode) == 0o600 and p.read_text() == "USER_SESSION=secret\n"


def test_max_file_bytes_depends_on_premium():
    assert gs.max_file_bytes_for(True) == 4 * 1024**3
    assert gs.max_file_bytes_for(False) == 2 * 1024**3


def test_bot_id_and_chat_id_validation():
    assert gs.bot_id_from_token("123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx") == 123456789
    assert gs.valid_chat_id("-1001234567890") and not gs.valid_chat_id("1234567890") and not gs.valid_chat_id("-12")


@pytest.mark.parametrize("member,ctype,ok", [
    ({"status": "creator"}, "channel", True),
    ({"status": "administrator", "can_post_messages": True, "can_delete_messages": True}, "channel", True),
    ({"status": "administrator", "can_post_messages": False, "can_delete_messages": True}, "channel", False),
    ({"status": "administrator", "can_delete_messages": False, "can_post_messages": True}, "channel", False),
    ({"status": "member"}, "channel", False),
    ({"status": "left"}, "supergroup", False),
    ({"status": "administrator", "can_delete_messages": True}, "supergroup", True),
])
def test_bot_admin_verdict(member, ctype, ok):
    got, problems = gs.bot_admin_verdict(member, ctype)
    assert got is ok and (ok or problems)


def test_generator_never_prints_the_session_string():
    src = (ROOT / "tools" / "generate_session.py").read_text(encoding="utf-8")
    # the only use of the exported string is writing it to the env file / private file
    assert "print(session" not in src and "print(updates" not in src and "{session}" not in src


# ------------------------------------------------------------------ doctor_checks
def test_session_decoding_all_known_formats():
    assert dc.decode_session_user_id(fake_session(777)) == 777
    raw64 = struct.pack(">B?256sQ?", 2, False, b"\x02" * 256, 888, False)
    assert dc.decode_session_user_id(base64.urlsafe_b64encode(raw64).decode().rstrip("=")) == 888
    assert dc.decode_session_user_id("not-a-session") is None
    assert dc.decode_session_user_id("") is None


def run_checks(env_path: Path) -> list[dict]:
    res = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "doctor_checks.py"), "--env-file", str(env_path)],
                         capture_output=True, text=True, timeout=120)
    return [json.loads(ln) for ln in res.stdout.splitlines() if ln.startswith("{")]


async def make_db(path: Path, fernet_key: bytes | None = None, channels: int = 0, status: str = "active"):
    from cryptography.fernet import Fernet

    from db.store import Store

    store = Store(str(path))
    await store.connect()
    for i in range(channels):
        enc = Fernet(fernet_key).encrypt(b"refresh") if fernet_key else b"x"
        await store.conn.execute(
            "INSERT INTO yt_channels (channel_id, channel_title, refresh_token_enc, scopes, status, added_at)"
            " VALUES (?,?,?,?,?, '2026-01-01')", (f"UC{i}", f"Chan {i}", enc, "youtube.upload youtube.force-ssl", status))
    await store.conn.commit()
    await store.close()


async def test_db_and_key_checks_report_ok(tmp_path):
    from cryptography.fernet import Fernet

    key = Fernet.generate_key()
    (tmp_path / "fernet.key").write_bytes(key)
    await make_db(tmp_path / "t.db", key, channels=2)
    env = tmp_path / "t.env"
    env.write_text(f"DB_PATH={tmp_path / 't.db'}\nFERNET_KEY_PATH={tmp_path / 'fernet.key'}\nJOBS_DIR={tmp_path}\n"
                   "MIN_FREE_DISK_BYTES=1\nBOT_TOKEN=\n", encoding="utf-8")
    by_name = {r["name"]: r for r in run_checks(env)}
    assert by_name["Database"]["status"] == "ok"
    assert by_name["Linked YouTube channels"]["status"] == "ok" and "2 linked" in by_name["Linked YouTube channels"]["detail"]
    assert by_name["Encryption key"]["status"] == "ok" and "decrypts" in by_name["Encryption key"]["detail"]
    assert by_name["Google OAuth client"]["status"] == "warn"
    assert by_name["Disk space"]["status"] == "ok"
    assert by_name["Telegram bot token"]["status"] == "fail"           # empty token
    assert by_name["Large-file relay"]["status"] == "warn"             # not configured


async def test_wrong_fernet_key_is_detected(tmp_path):
    from cryptography.fernet import Fernet

    await make_db(tmp_path / "t.db", Fernet.generate_key(), channels=1)
    (tmp_path / "fernet.key").write_bytes(Fernet.generate_key())      # a different key than the DB was written with
    env = tmp_path / "t.env"
    env.write_text(f"DB_PATH={tmp_path / 't.db'}\nFERNET_KEY_PATH={tmp_path / 'fernet.key'}\nJOBS_DIR={tmp_path}\nMIN_FREE_DISK_BYTES=1\n", encoding="utf-8")
    by_name = {r["name"]: r for r in run_checks(env)}
    assert by_name["Encryption key"]["status"] == "fail" and "does not match" in by_name["Encryption key"]["detail"]


async def test_channel_needing_reauth_is_a_failure(tmp_path):
    from cryptography.fernet import Fernet

    key = Fernet.generate_key()
    (tmp_path / "fernet.key").write_bytes(key)
    await make_db(tmp_path / "t.db", key, channels=1, status="needs_reauth")
    env = tmp_path / "t.env"
    env.write_text(f"DB_PATH={tmp_path / 't.db'}\nFERNET_KEY_PATH={tmp_path / 'fernet.key'}\nJOBS_DIR={tmp_path}\nMIN_FREE_DISK_BYTES=1\n", encoding="utf-8")
    by_name = {r["name"]: r for r in run_checks(env)}
    assert by_name["Linked YouTube channels"]["status"] == "fail" and "needs_reauth" in by_name["Linked YouTube channels"]["detail"]


def test_missing_db_is_a_failure_with_a_fix(tmp_path):
    env = tmp_path / "t.env"
    env.write_text(f"DB_PATH={tmp_path / 'nope.db'}\nJOBS_DIR={tmp_path}\nMIN_FREE_DISK_BYTES=1\n", encoding="utf-8")
    db = {r["name"]: r for r in run_checks(env)}["Database"]
    assert db["status"] == "fail" and db["fix"]


def test_relay_half_configured_fails_and_malformed_session_fails(tmp_path):
    env = tmp_path / "t.env"
    env.write_text(f"DB_PATH={tmp_path / 'x.db'}\nJOBS_DIR={tmp_path}\nMIN_FREE_DISK_BYTES=1\nUSER_SESSION=abc\nRELAY_CHAT_ID=\n", encoding="utf-8")
    assert {r["name"]: r for r in run_checks(env)}["Large-file relay"]["status"] == "fail"
    env.write_text(f"DB_PATH={tmp_path / 'x.db'}\nJOBS_DIR={tmp_path}\nMIN_FREE_DISK_BYTES=1\nUSER_SESSION=abc\nRELAY_CHAT_ID=-1001234567890\n", encoding="utf-8")
    assert {r["name"]: r for r in run_checks(env)}["Relay session"]["status"] == "fail"


def test_doctor_output_never_contains_secrets(tmp_path):
    token = "123456789:AAHsecretsecretsecretsecretsecret0000"
    sess = fake_session()
    env = tmp_path / "t.env"
    env.write_text(f"DB_PATH={tmp_path / 'x.db'}\nJOBS_DIR={tmp_path}\nMIN_FREE_DISK_BYTES=1\nBOT_TOKEN={token}\n"
                   f"USER_SESSION={sess}\nRELAY_CHAT_ID=-1001234567890\n", encoding="utf-8")
    res = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "doctor_checks.py"), "--env-file", str(env)],
                         capture_output=True, text=True, timeout=120)
    assert "secretsecret" not in res.stdout and sess not in res.stdout


# ------------------------------------------------------------------ admin_user + migrate_db (real app code, temp DB)
def tool_env(tmp_path: Path) -> dict:
    env_file = tmp_path / "app.env"
    env_file.write_text(
        "API_ID=1\nAPI_HASH=0123456789abcdef0123456789abcdef\nBOT_TOKEN=1:AAHfake\nOWNER_TG_ID=5\nSESSION_SECRET=s\n"
        f"DB_PATH={(tmp_path / 'app.db').as_posix()}\nFERNET_KEY_PATH={(tmp_path / 'f.key').as_posix()}\n"
        f"JOBS_DIR={(tmp_path / 'jobs').as_posix()}\nREQUIRE_TOTP=true\n", encoding="utf-8")
    e = {k: v for k, v in os.environ.items() if k not in ("API_ID", "API_HASH", "BOT_TOKEN", "OWNER_TG_ID", "SESSION_SECRET")}
    e["TGYT_ENV_FILE"] = env_file.as_posix()
    return e


def run_tool(name: str, env: dict, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "tools" / name), *args], input=stdin, env=env, cwd=str(ROOT),
                          capture_output=True, text=True, timeout=120)


def test_admin_user_create_reset_and_unlock(tmp_path):
    env = tool_env(tmp_path)
    assert run_tool("migrate_db.py", env).returncode == 0
    r = run_tool("admin_user.py", env, "--username", "boss", "--password-stdin", stdin="Str0ng-pass-phrase!\n")
    assert r.returncode == 0 and "Created" in r.stdout
    db = sqlite3.connect(tmp_path / "app.db")
    h1 = db.execute("select password_hash from app_users where username='boss'").fetchone()[0]
    from bot import security
    assert security.verify_password(h1, "Str0ng-pass-phrase!") and "Str0ng" not in h1

    db.execute("update app_users set failed_attempts=5, locked_until='2999-01-01T00:00:00+00:00', totp_secret_enc=x'00ff' where username='boss'")
    db.commit()
    r = run_tool("admin_user.py", env, "--username", "boss", "--password-stdin", stdin="An0ther-Good-pass!\n")
    assert r.returncode == 0 and "lockout cleared" in r.stdout
    row = db.execute("select password_hash, failed_attempts, locked_until from app_users where username='boss'").fetchone()
    assert security.verify_password(row[0], "An0ther-Good-pass!") and row[1] == 0 and row[2] is None

    r = run_tool("admin_user.py", env, "--username", "boss", "--reset-totp")
    assert r.returncode == 0 and db.execute("select totp_secret_enc from app_users where username='boss'").fetchone()[0] is None


def test_admin_user_rejects_weak_password_and_bad_username(tmp_path):
    env = tool_env(tmp_path)
    r = run_tool("admin_user.py", env, "--username", "boss", "--password-stdin", stdin="weak\n")
    assert r.returncode != 0 and "rejected" in r.stderr
    r = run_tool("admin_user.py", env, "--username", "bad name;", "--password-stdin", stdin="Str0ng-pass-phrase!\n")
    assert r.returncode != 0
    assert "weak" not in r.stdout


def test_migrate_db_is_idempotent_and_upgrades_old_schema(tmp_path):
    env = tool_env(tmp_path)
    # an "old" database: yt_channels without the later columns
    old = sqlite3.connect(tmp_path / "app.db")
    old.execute("CREATE TABLE yt_channels (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id TEXT NOT NULL UNIQUE, channel_title TEXT NOT NULL,"
                " handle TEXT, thumbnail_url TEXT, refresh_token_enc BLOB NOT NULL, access_token_enc BLOB, access_expires_at TEXT,"
                " scopes TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', is_default INTEGER NOT NULL DEFAULT 0, added_at TEXT NOT NULL,"
                " added_by TEXT, last_used_at TEXT, uploads_count INTEGER NOT NULL DEFAULT 0)")
    old.execute("INSERT INTO yt_channels (channel_id, channel_title, refresh_token_enc, scopes, added_at) VALUES ('UC1','Old',x'01','s','2025-01-01')")
    old.commit(); old.close()
    for _ in range(2):
        assert run_tool("migrate_db.py", env).returncode == 0
    cols = {r[1] for r in sqlite3.connect(tmp_path / "app.db").execute("pragma table_info(yt_channels)")}
    assert {"display_label", "google_email", "subscriber_count"} <= cols
    assert sqlite3.connect(tmp_path / "app.db").execute("select channel_title from yt_channels").fetchone()[0] == "Old"
