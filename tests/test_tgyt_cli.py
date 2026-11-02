"""`tgyt` management command: off-site backup plumbing and failure alerts.

The functions are loaded from deploy/tgyt without running its command dispatcher, and the external
programs (restic, curl) are replaced by fakes on PATH that record how they were called.
"""
from __future__ import annotations

import os
import shutil
import sys
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")

FAKE_TOKEN = "123456789:AAH-fake-test-token-0123456789abc"


@pytest.fixture
def cli(tmp_path):
    """A copy of deploy/tgyt minus its dispatcher, with fake restic/curl and private config dirs."""
    work = tmp_path / "deploy"
    shutil.copytree(ROOT / "deploy" / "lib", work / "lib")
    text = (ROOT / "deploy" / "tgyt").read_text(encoding="utf-8")
    body = text[: text.rindex("\ninit_log\n")]          # everything before the dispatcher
    (work / "tgyt").write_text(body + "\n", encoding="utf-8", newline="\n")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    rec = tmp_path / "rec"
    rec.mkdir()
    (bin_dir / "restic").write_text(
        '#!/usr/bin/env bash\n'
        f'env | grep -E "^(RESTIC_|AWS_)" | sort > "{rec.as_posix()}/restic.env"\n'
        f'printf "%s\\n" "$@" > "{rec.as_posix()}/restic.args"\n', newline="\n")
    (bin_dir / "curl").write_text(
        '#!/usr/bin/env bash\n'
        f'printf "%s\\n" "$@" > "{rec.as_posix()}/curl.args"\n'
        f'cat > "{rec.as_posix()}/curl.stdin"\n', newline="\n")
    for f in bin_dir.iterdir():
        f.chmod(0o755)

    offsite = tmp_path / "offsite"
    offsite.mkdir()
    env_file = tmp_path / "tgyt.env"
    env_file.write_text(f"BOT_TOKEN={FAKE_TOKEN}\nOWNER_TG_ID=123456789\n", encoding="utf-8", newline="\n")

    def run(script: str) -> subprocess.CompletedProcess:
        env = dict(os.environ,
                   PATH=f"{bin_dir.as_posix()}{os.pathsep}{os.environ.get('PATH', '')}",
                   TGYT_OFFSITE_DIR=offsite.as_posix(), TGYT_ENV_FILE=env_file.as_posix(),
                   TGYT_BACKUP_DIR=(tmp_path / "backups").as_posix(), LOG_FILE="")
        full = f'source "{(work / "tgyt").as_posix()}"; LOG_FILE=""\n{script}'
        return subprocess.run([BASH, "-c", full], capture_output=True, text=True, timeout=60, env=env, cwd=tmp_path)

    return run, offsite, rec


def write_conf(offsite: Path, extra: str = "") -> None:
    (offsite / "offsite.conf").write_text(
        "ENDPOINT=s3.us-west-004.backblazeb2.com\nBUCKET=my-tgyt-backups\n"
        "ACCESS_KEY_ID=0041234567890abcdef0000000001\nSECRET_ACCESS_KEY=K004FAKEapplicationKeyForTests0123\n" + extra,
        encoding="utf-8", newline="\n")
    (offsite / "restic.pass").write_text("correct horse battery staple", encoding="utf-8")


def test_help_lists_offsite_commands():
    res = subprocess.run([BASH, (ROOT / "deploy" / "tgyt").as_posix(), "help"], capture_output=True, text=True, timeout=60,
                         env=dict(os.environ, LOG_FILE=""))
    assert "tgyt offsite setup" in res.stdout


def test_restic_gets_repository_region_and_password_file(cli):
    run, offsite, rec = cli
    write_conf(offsite)
    res = run("offsite_restic snapshots --compact")
    assert res.returncode == 0, res.stderr
    env = dict(line.split("=", 1) for line in (rec / "restic.env").read_text(encoding="utf-8").splitlines())
    assert env["RESTIC_REPOSITORY"] == "s3:https://s3.us-west-004.backblazeb2.com/my-tgyt-backups/tgyt"
    assert env["AWS_DEFAULT_REGION"] == "us-west-004"
    assert env["AWS_ACCESS_KEY_ID"] == "0041234567890abcdef0000000001"
    assert env["RESTIC_PASSWORD_FILE"].endswith("/restic.pass")
    # the password itself is never handed over in the environment or on the command line
    assert "RESTIC_PASSWORD" not in env
    assert "correct horse" not in (rec / "restic.args").read_text(encoding="utf-8")


def test_offsite_config_is_parsed_never_executed(cli, tmp_path):
    run, offsite, rec = cli
    marker = tmp_path / "pwned"
    write_conf(offsite, f"RESTIC_PASSWORD_COMMAND=touch {marker.as_posix()}\n$(touch {marker.as_posix()})\n")
    assert run("offsite_restic snapshots").returncode == 0
    assert not marker.exists()
    assert "RESTIC_PASSWORD_COMMAND" not in (rec / "restic.env").read_text(encoding="utf-8")


@pytest.mark.parametrize("fn,value,expected", [
    ("is_bucket_name", "my-tgyt-backups", True), ("is_bucket_name", "ab", False), ("is_bucket_name", "Upper-Case", False),
    ("is_bucket_name", "bad_underscore", False), ("is_bucket_name", "-leading-dash", False),
    ("is_s3_endpoint", "s3.us-west-004.backblazeb2.com", True), ("is_s3_endpoint", "https://s3.example.com", False),
    ("is_access_key_id", "0041234567890abcdef0000000001", True), ("is_access_key_id", "short", False),
    ("is_access_key_secret", "K004FAKEapplicationKeyForTests0123", True), ("is_access_key_secret", "has space in it xxxxxxxxx", False),
])
def test_offsite_validators(cli, fn, value, expected):
    run, _, _ = cli
    assert (run(f'{fn} "{value}"').returncode == 0) is expected


def test_owner_notification_keeps_the_token_off_the_command_line(cli):
    run, _, rec = cli
    assert run('notify_owner "backup failed"').returncode == 0
    args = (rec / "curl.args").read_text(encoding="utf-8")
    assert FAKE_TOKEN not in args
    assert "chat_id=123456789" in args and "text=backup failed" in args
    assert f"bot{FAKE_TOKEN}/sendMessage" in (rec / "curl.stdin").read_text(encoding="utf-8")


def test_scheduled_backup_alerts_the_owner_when_a_step_dies(cli):
    run, _, rec = cli
    res = run('cmd_backup() { die "disk full"; }\nbackup_scheduled')
    assert res.returncode != 0
    assert "nightly backup FAILED" in (rec / "curl.args").read_text(encoding="utf-8")


def test_need_root_names_the_variables_it_keeps(cli, tmp_path):
    """sudo-rs (Ubuntu 26.04) ignores a bare `sudo -E`, so the re-exec must use --preserve-env=LIST."""
    run, _, rec = cli
    fake_sudo = tmp_path / "bin" / "sudo"
    fake_sudo.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "{(rec / "sudo.args").as_posix()}"\n', newline="\n")
    fake_sudo.chmod(0o755)
    res = run('[[ $EUID -ne 0 ]] || exit 77\nexport TGYT_BACKUP_PASSPHRASE=x NO_COLOR=1\nneed_root backup --encrypt')
    if res.returncode == 77:
        pytest.skip("running as root: need_root never re-executes")
    args = (rec / "sudo.args").read_text(encoding="utf-8").splitlines()
    assert "-E" not in args
    preserve = [a for a in args if a.startswith("--preserve-env=")]
    assert preserve and {"TGYT_BACKUP_PASSPHRASE", "NO_COLOR", "TGYT_ENV_FILE"} <= set(preserve[0].split("=", 1)[1].split(","))
    assert args[-2:] == ["backup", "--encrypt"]


def test_scheduled_backup_success_sends_no_alert(cli):
    run, _, rec = cli
    res = run('cmd_backup() { :; }\nbackup_scheduled')
    assert res.returncode == 0, res.stderr
    assert not (rec / "curl.args").exists()


def test_new_bot_token_sets_old_bot_login_aside(cli, tmp_path):
    """Kurigram reuses tgyt-bot.session and ignores BOT_TOKEN, so after a token change the old login must go."""
    run, _, _ = cli
    data = tmp_path / "data"
    data.mkdir()
    (data / "tgyt-bot.session").write_text("old login", encoding="utf-8")
    (data / "tgyt-bot.session-journal").write_text("j", encoding="utf-8")
    with (tmp_path / "tgyt.env").open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"DB_PATH={(data / 'tgyt.db').as_posix()}\n")
    res = run("bot_session_set_aside")
    assert res.returncode == 0, res.stderr
    left = sorted(p.name for p in data.iterdir())
    assert "tgyt-bot.session" not in left and "tgyt-bot.session-journal" not in left
    kept = [n for n in left if n.startswith("tgyt-bot.session.old-")]
    assert len(kept) == 1 and (data / kept[0]).read_text(encoding="utf-8") == "old login"
    assert run("bot_session_set_aside").returncode == 0   # nothing to move: still fine


# --- Backup manifest: regression for "./MANIFEST.txt: FAILED" on every restore -----------------------------------
# Scripts run with tmp_path as the working directory and use relative paths (Windows tar reads "C:" as a host).

def backup_env(tmp_path: Path) -> str:
    """Env lines for make_backup: a real SQLite db and a Fernet key file in tmp_path."""
    import sqlite3
    db = tmp_path / "data" / "tgyt.db"
    db.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(db)
    con.execute("create table t (x)")
    con.execute("insert into t values (1)")
    con.commit()
    con.close()
    key = tmp_path / "fernet.key"
    key.write_text("fake-fernet-key-for-tests=", encoding="utf-8")
    with (tmp_path / "tgyt.env").open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"DB_PATH={db.as_posix()}\nFERNET_KEY_PATH={key.as_posix()}\n")
    return f'VENV_PY="{Path(sys.executable).as_posix()}"\n'


def test_backup_manifest_does_not_list_itself_and_verifies(cli, tmp_path):
    run, _, _ = cli
    res = run(backup_env(tmp_path) +
              'a="$(make_backup out 0)"; mkdir x; tar -xzf "$a" -C x; cat x/MANIFEST.txt\n'
              'verify_manifest x && echo VERIFIED\n'
              '(cd x && grep -E "^[0-9a-f]{64} [ *]" MANIFEST.txt | sha256sum -c --strict --quiet -) && echo STRICT_OK')
    assert res.returncode == 0, res.stderr
    assert "./MANIFEST.txt" not in res.stdout
    for name in ("./tgyt.db", "./tgyt.env", "./fernet.key"):
        assert name in res.stdout
    assert "VERIFIED" in res.stdout and "STRICT_OK" in res.stdout


def test_old_manifest_with_half_written_self_checksum_still_verifies(cli):
    """Backups made before the fix (including existing off-site snapshots) must stay restorable."""
    run, _, _ = cli
    res = run('mkdir d; cd d; echo db > tgyt.db; echo env > tgyt.env\n'
              # the old, buggy way: the redirect creates MANIFEST.txt before find lists the folder
              '{ echo "tgyt-backup v1"; find . -type f -print0 | sort -z | xargs -0 sha256sum; } > MANIFEST.txt\n'
              'grep -qE "[.]/MANIFEST[.]txt$" MANIFEST.txt || { echo "repro did not list itself"; exit 3; }\n'
              'if grep -E "^[0-9a-f]{64} [ *]" MANIFEST.txt | sha256sum -c --quiet - >/dev/null 2>&1; then echo "repro verifies"; exit 4; fi\n'
              'cd ..; verify_manifest d && echo VERIFIED')
    assert res.returncode == 0, res.stdout + res.stderr
    assert "VERIFIED" in res.stdout


def test_tampered_backup_file_fails_and_is_named(cli):
    run, _, _ = cli
    res = run('mkdir d; cd d; echo db > tgyt.db; echo env > tgyt.env\n'
              's="$(sha256sum ./tgyt.db ./tgyt.env)"; { echo "tgyt-backup v1"; echo "$s"; } > MANIFEST.txt\n'
              'echo changed > tgyt.db; cd ..; rc=0; verify_manifest d || rc=$?; echo "rc=$rc"')
    assert "rc=1" in res.stdout
    assert "./tgyt.db: FAILED" in res.stderr and "tgyt.env" not in res.stderr


def test_offsite_restore_test_fails_nonzero_on_corrupt_snapshot(cli, tmp_path):
    run, offsite, _ = cli
    write_conf(offsite)
    # A real backup whose database is altered after the manifest was written, served as the "latest snapshot".
    res = run(backup_env(tmp_path) +
              'a="$(make_backup out 0)"; mkdir src; tar -xzf "$a" -C src\n'
              'echo corrupted >> src/tgyt.db; mkdir snap; tar -czf snap/tgyt-backup.tar.gz -C src .\n'
              'snap="$PWD/snap/tgyt-backup.tar.gz"\n'
              'offsite_fetch_latest() { cp "$snap" "$1/"; echo "$1/tgyt-backup.tar.gz"; }\n'
              'offsite_restore_test')
    assert res.returncode != 0
    assert "Restore test passed" not in res.stdout + res.stderr
    assert "./tgyt.db: FAILED" in res.stderr
    assert "Checksum mismatch inside the downloaded off-site backup" in res.stderr


def test_offsite_restore_test_passes_on_good_snapshot(cli, tmp_path):
    run, offsite, _ = cli
    write_conf(offsite)
    res = run(backup_env(tmp_path) +
              'a="$PWD/$(make_backup out 0)"\n'
              'offsite_fetch_latest() { cp "$a" "$1/tgyt-backup.tar.gz"; echo "$1/tgyt-backup.tar.gz"; }\n'
              'offsite_restore_test')
    assert res.returncode == 0, res.stderr
    assert "Restore test passed" in res.stdout + res.stderr
