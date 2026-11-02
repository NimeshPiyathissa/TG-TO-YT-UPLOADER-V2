"""Installer unit tests: input validation, env-file generation, log redaction.

The shell libraries under deploy/lib are sourced into a real bash; skipped where bash is missing.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = (ROOT / "deploy" / "lib").as_posix()
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")


def sh(script: str, *, check: bool = True) -> subprocess.CompletedProcess:
    full = f'set -u; source "{LIB}/validate.sh"; source "{LIB}/common.sh"; source "{LIB}/envgen.sh"; LOG_FILE=""\n{script}'
    res = subprocess.run([BASH, "-c", full], capture_output=True, text=True, timeout=60)
    if check and res.returncode not in (0, 1):
        raise AssertionError(res.stderr)
    return res


def valid(fn: str, value: str) -> bool:
    return subprocess.run([BASH, "-c", f'source "{LIB}/validate.sh"; {fn} "$1"', "_", value],
                          capture_output=True, timeout=30).returncode == 0


@pytest.mark.parametrize("value,expected", [
    ("upload.example.com", True), ("a.b.example.co.uk", True), ("my-app.example.org", True),
    ("203-0-113-10.sslip.io", True),
    ("example", False), ("localhost", False), ("1.2.3.4", False), ("UP.example.com", False),
    ("under_score.example.com", False), ("-bad.example.com", False), ("a b.example.com", False),
    ("https://example.com", False), ("example.com/path", False), ("", False), ("exa$mple.com", False),
    ("a" * 64 + ".example.com", False),
])
def test_is_domain(value, expected):
    assert valid("is_domain", value) is expected


@pytest.mark.parametrize("value,expected", [
    ("123456789:AAH-fake-test-token-0123456789abc", True),
    ("123456789:AAH-fake_token_with-dashes_and_under", True),
    ("123456789", False), ("abc:AAH-fake-test-token-0123456789abc", False), ("123456789:short", False),
    ("123456789:AAH-fake-test-token-0123456789abc ; rm -rf /", False), ("", False),
])
def test_is_bot_token(value, expected):
    assert valid("is_bot_token", value) is expected


@pytest.mark.parametrize("fn,value,expected", [
    ("is_api_id", "1234567", True), ("is_api_id", "0", False), ("is_api_id", "12ab", False), ("is_api_id", "", False),
    ("is_api_hash", "0123456789abcdef0123456789abcdef", True), ("is_api_hash", "0123456789ABCDEF0123456789ABCDEF", False),
    ("is_api_hash", "0123456789abcdef", False), ("is_api_hash", "0123456789abcdef0123456789abcdeg", False),
    ("is_tg_user_id", "123456789", True), ("is_tg_user_id", "-100123456", False), ("is_tg_user_id", "12", False),
    ("is_relay_chat_id", "-1001234567890", True), ("is_relay_chat_id", "1234567890", False), ("is_relay_chat_id", "-123", False),
    ("is_email", "me@example.com", True), ("is_email", "me@", False), ("is_email", "not an email", False),
    ("is_username", "admin", True), ("is_username", "ab", False), ("is_username", "has space", False), ("is_username", "a;b;c", False),
    ("is_region_code", "US", True), ("is_region_code", "us", False), ("is_region_code", "USA", False),
    ("is_port", "443", True), ("is_port", "65535", True), ("is_port", "0", False), ("is_port", "65536", False), ("is_port", "http", False),
    ("is_bool", "true", True), ("is_bool", "false", True), ("is_bool", "yes", False),
    ("is_chunk_bytes", "8388608", True), ("is_chunk_bytes", "1000", False),
    ("is_positive_int", "2147483648", True), ("is_positive_int", "-1", False), ("is_positive_int", "0", False),
    ("is_ipv4", "203.0.113.10", True), ("is_ipv4", "256.1.1.1", False), ("is_ipv4", "1.2.3", False),
    ("is_privacy", "unlisted", True), ("is_privacy", "secret", False),
])
def test_simple_validators(fn, value, expected):
    assert valid(fn, value) is expected


def test_session_string_validator():
    assert valid("is_session_string", "A" * 350)
    assert not valid("is_session_string", "A" * 50)
    assert not valid("is_session_string", "A" * 300 + " ; echo")


def _load_admin_user():
    spec = importlib.util.spec_from_file_location("admin_user_tool", ROOT / "tools" / "admin_user.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("pw", [
    "short", "alllowercaseletters", "ALLUPPERCASELETTERS", "123456789012", "aaaaaaaaaaaA1", "abcabcabcabc",
    "Str0ng-pass-phrase!", "correct Horse 9 battery", "Tr0ub4dor&3xyz", "onlylower1234", "UPPERlower12",
])
def test_password_policy_matches_python_tool(pw):
    """Bash (installer) and Python (tools/admin_user.py) must accept/reject identically."""
    py_ok = _load_admin_user().password_problem(pw) is None
    res = subprocess.run([BASH, "-c", f'source "{LIB}/validate.sh"; password_problem "$1" >/dev/null', "_", pw],
                         capture_output=True, timeout=30)
    assert (res.returncode == 0) is py_ok


def test_env_set_get_roundtrip_preserves_other_lines(tmp_path):
    f = tmp_path / "t.env"
    f.write_text("# comment\nA=1\nB=two words # not a comment\nC=\n", encoding="utf-8")
    sh(f'env_set "{f.as_posix()}" B "x=y#z"; env_set "{f.as_posix()}" NEW 5; env_set "{f.as_posix()}" C filled')
    assert f.read_text(encoding="utf-8") == "# comment\nA=1\nB=x=y#z\nC=filled\nNEW=5\n"
    assert sh(f'env_get "{f.as_posix()}" B').stdout == "x=y#z"
    assert sh(f'env_get "{f.as_posix()}" MISSING').stdout == ""


def test_env_set_rejects_newlines(tmp_path):
    f = tmp_path / "t.env"
    f.write_text("A=1\n", encoding="utf-8")
    res = sh(f'env_set "{f.as_posix()}" A $\'x\\nINJECTED=1\'', check=False)
    assert res.returncode != 0
    assert f.read_text(encoding="utf-8") == "A=1\n"


def _generated_env(tmp_path, **overrides) -> Path:
    """Run the installer's own apply_install_settings over .env.example."""
    out = tmp_path / "tgyt.env"
    shutil.copy(ROOT / ".env.example", out)
    values = dict(
        API_ID="7654321", API_HASH="fedcba9876543210fedcba9876543210", BOT_TOKEN="987654321:AAH-fake-bot-token-0123456789abcdef",
        OWNER_ID="555000111", OAUTH_MODE="hostname", PUBLIC_IP="203.0.113.77", DOMAIN="panel.example.net", WEB_PORT="443",
        ADMIN_USER="boss", REQUIRE_TOTP="true", REGION="GB", MAX_FILE_BYTES="4294967296",
        FERNET_KEY_PATH=(tmp_path / "fernet.key").as_posix(), DATA_DIR=tmp_path.as_posix(),
    )
    values.update(overrides)
    exports = "\n".join(f'{k}="{v}"' for k, v in values.items())
    sh(f'{exports}\napply_install_settings "{out.as_posix()}"')
    return out


def test_generated_env_is_accepted_by_the_app_settings(tmp_path, monkeypatch):
    env = _generated_env(tmp_path)
    monkeypatch.setenv("TGYT_ENV_FILE", env.as_posix())
    for k in ("API_ID", "API_HASH", "BOT_TOKEN", "OWNER_TG_ID", "SESSION_SECRET"):
        monkeypatch.delenv(k, raising=False)
    from pydantic_settings import SettingsConfigDict

    from bot.config import Settings

    class S(Settings):
        model_config = SettingsConfigDict(env_file=env.as_posix(), env_file_encoding="utf-8", extra="ignore")

    s = S()
    assert (s.api_id, s.owner_tg_id, s.public_host, s.web_port, s.yt_region_code) == (7654321, 555000111, "panel.example.net", 443, "GB")
    assert s.max_file_bytes == 4294967296 and s.require_totp is True and s.admin_username == "boss"
    assert s.admin_password == "" and s.user_session in (None, "") and s.relay_chat_id is None
    assert s.redirect_uri == "https://panel.example.net/oauth/callback"
    assert s.db_path == (tmp_path / "tgyt.db").as_posix()


def test_generated_env_custom_port_and_relay(tmp_path, monkeypatch):
    env = _generated_env(tmp_path, WEB_PORT="8443", USER_SESSION="S" * 300, RELAY_CHAT_ID="-1001234567890")
    text = env.read_text(encoding="utf-8")
    assert "WEB_PORT=8443\n" in text and "RELAY_CHAT_ID=-1001234567890\n" in text and ("USER_SESSION=" + "S" * 300) in text
    assert text.count("\nBOT_TOKEN=") == 1                       # replaced, not duplicated
    assert "ADMIN_PASSWORD=\n" in text                           # the plaintext password is never written


def test_reinstall_does_not_blank_an_existing_relay(tmp_path):
    env = _generated_env(tmp_path, USER_SESSION="K" * 300, RELAY_CHAT_ID="-1009998887776")
    exports = 'API_ID=1 API_HASH=a BOT_TOKEN=b OWNER_ID=2 OAUTH_MODE=hostname PUBLIC_IP=1.1.1.1 DOMAIN=x.example.com WEB_PORT=443 ' \
              'ADMIN_USER=admin REQUIRE_TOTP=false REGION=US MAX_FILE_BYTES=2147483648 FERNET_KEY_PATH=/k DATA_DIR=/d'
    sh(f'{exports}; USER_SESSION=""; RELAY_CHAT_ID=""; apply_install_settings "{env.as_posix()}"')
    text = env.read_text(encoding="utf-8")
    assert "USER_SESSION=" + "K" * 300 in text and "RELAY_CHAT_ID=-1009998887776" in text


def test_example_env_documents_every_setting_the_app_reads():
    from bot.config import Settings

    example = {ln.split("=", 1)[0] for ln in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
               if ln and not ln.startswith("#") and "=" in ln}
    missing = {f.upper() for f in Settings.model_fields} - example
    assert not missing, f".env.example lacks: {sorted(missing)}"


def test_redact_masks_tokens_secrets_and_registered_values():
    res = sh(r'''
register_secret "my-Super-Secret-pw"
printf '%s\n' "token 123456789:AAH-fake-test-token-0123456789abc end" \
  "USER_SESSION=$(printf 'A%.0s' {1..300})" "hash 0123456789abcdef0123456789abcdef x" \
  "password is my-Super-Secret-pw ok" "API_HASH=abcdef" "plain line stays" | redact
''')
    out = res.stdout
    assert "AAH-fake-test" not in out and "my-Super-Secret-pw" not in out and "0123456789abcdef0123456789abcdef" not in out
    assert "A" * 50 not in out and "API_HASH=[REDACTED]" in out
    assert "plain line stays" in out and "[REDACTED-BOT-TOKEN]" in out


def test_log_file_never_contains_secrets(tmp_path):
    log = tmp_path / "install.log"
    sh(f'''LOG_FILE="{log.as_posix()}"; register_secret "hunter2-Hunter2!"
init_log; info "using hunter2-Hunter2! and 123456789:AAH-fake-test-token-0123456789abc"
run "echo a secret" bash -c 'echo hunter2-Hunter2!' ''')
    text = log.read_text(encoding="utf-8")
    assert "hunter2" not in text and "AAH-fake-test" not in text and "REDACTED" in text


def test_validator_table_covers_every_configurable_key():
    for key in ("BOT_TOKEN", "API_HASH", "MAX_FILE_BYTES", "WEB_PORT", "REQUIRE_TOTP", "UPLOAD_CHUNK_BYTES", "RELAY_CHAT_ID"):
        assert sh(f'validator_for_key {key}').stdout.strip().startswith("is_")
    assert sh("validator_for_key FERNET_KEY_PATH").stdout.strip() == ""   # paths are not editable via `tgyt config`


def test_installer_refuses_to_run_without_root():
    if sys.platform == "win32":
        pytest.skip("root check semantics differ on Windows")
    import os
    if os.geteuid() == 0:
        pytest.skip("running as root")
    res = subprocess.run([BASH, str(ROOT / "deploy" / "install.sh")], capture_output=True, text=True, timeout=30)
    assert res.returncode != 0 and "root" in (res.stdout + res.stderr).lower()


def test_panel_env_view_redacts_the_relay_session(tmp_path, monkeypatch):
    """Regression: USER_SESSION (full access to a Telegram account) used to be shown in clear text."""
    from web import envfile

    env = tmp_path / "t.env"
    env.write_text("BOT_TOKEN=123456789:AAHsecret\nUSER_SESSION=SESSIONSECRETVALUE\nSESSION_SECRET=abc\nAPI_HASH=0123\n"
                   "WEB_PORT=443\nADMIN_USERNAME=admin\nRELAY_CHAT_ID=-100123456\nUSER_SESSION_EMPTY=\n", encoding="utf-8")
    monkeypatch.setattr(envfile, "ENV_FILE", env.as_posix())
    shown = "\n".join(envfile.redacted_env_lines())
    for secret in ("AAHsecret", "SESSIONSECRETVALUE", "zz9plural", "deadbeefcafe"):
        assert secret not in shown
    assert "WEB_PORT=443" in shown and "ADMIN_USERNAME=admin" in shown and "RELAY_CHAT_ID=-100123456" in shown
