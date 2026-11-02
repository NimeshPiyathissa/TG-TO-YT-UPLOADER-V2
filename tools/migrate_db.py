#!/usr/bin/env python3
"""Apply database migrations without starting the bot.

`Store.connect()` creates missing tables (schema.sql is idempotent) and runs the additive column
migrations, so opening the store is the whole migration. `tgyt update` runs this while the service
is stopped, so a broken migration is caught before the new version starts.

    TGYT_ENV_FILE=/etc/tgyt/tgyt.env python tools/migrate_db.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def main() -> int:
    from bot.config import settings
    from db.store import Store

    store = Store(settings.db_path)
    await store.connect()
    try:
        cur = await store.conn.execute("PRAGMA integrity_check")
        verdict = (await cur.fetchone())[0]
        if verdict != "ok":
            print(f"Database integrity check failed: {verdict}", file=sys.stderr)
            return 1
        cur = await store.conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in await cur.fetchall()]
        print(f"Database OK ({len(tables)} tables) at {settings.db_path}")
        return 0
    finally:
        await store.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
