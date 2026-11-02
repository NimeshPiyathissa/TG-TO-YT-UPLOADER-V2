"""A startup failure must end the process, so systemd's Restart=always can act.

Regression: after a bot token was revoked, Kurigram raised SESSION_REVOKED during start,
but the open aiosqlite connection (a non-daemon thread) kept the interpreter alive, so the
service looked "active" while the bot was dead.
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCRIPT = textwrap.dedent("""
    import sys
    sys.path.insert(0, sys.argv[1])
    import pyrogram

    async def failing_start(self, *a, **kw):
        raise RuntimeError("simulated SESSION_REVOKED")

    pyrogram.Client.start = failing_start
    from bot import main
    main.main()
""")


def test_startup_failure_exits_instead_of_hanging(tmp_path):
    env = dict(os.environ)
    env.update({
        "API_ID": "1", "API_HASH": "0" * 32, "BOT_TOKEN": "1:test", "OWNER_TG_ID": "1",
        "SESSION_SECRET": "test-secret", "TGYT_ENV_FILE": str(tmp_path / "none.env"),
        "DB_PATH": str(tmp_path / "tgyt.db"), "ADMIN_USERNAME": "admin", "ADMIN_PASSWORD": "a-long-test-password",
    })
    proc = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(ROOT)], env=env, cwd=tmp_path,
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode != 0
    assert "simulated SESSION_REVOKED" in proc.stderr
