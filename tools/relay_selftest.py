#!/usr/bin/env python3
"""Large-file download self-test: proves the bot -> relay channel -> relay account path works.

It runs the SAME ``bot.downloader.download_job`` the service uses, but never touches YouTube,
Google or the real job database. Stop the service first (the relay session must not be used by
two processes at once), then, as the service user:

    sudo tgyt relay-test

Send videos/files to your bot from the owner account. For each one this prints which path was
used, the size, the time and the speed, checks the file on disk, then deletes it.
Only sizes, timings and ids are printed; the bot token and session string never are.
"""
from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TWENTY_MB = 20 * 1024 * 1024


def describe_path(size_bytes: int, have_relay: bool) -> str:
    """Which download route ``download_job`` takes for a file of this size."""
    if size_bytes <= TWENTY_MB:
        return "bot client (<= 20 MB)"
    return "relay: bot forward -> relay account (MTProto)" if have_relay else "REJECTED: no relay configured"


def format_result(name: str, expected: int, actual: int, seconds: float, path: str) -> str:
    mb = actual / 1024 / 1024
    rate = mb / seconds if seconds > 0 else 0.0
    verdict = "PASS" if expected and abs(actual - expected) <= 4096 else "SIZE MISMATCH"
    return (f"{verdict}: {name} expected={expected} actual={actual} ({mb:.1f} MB) "
            f"time={seconds:.1f}s speed={rate:.1f} MB/s via {path}")


async def run(idle_exit_s: int) -> int:
    import pyrogram
    from pyrogram import filters

    from bot import downloader
    from bot.config import settings
    from bot.ui import ProgressReporter
    from db.store import Store

    if not settings.user_session or not settings.relay_chat_id:
        print("USER_SESSION / RELAY_CHAT_ID are not set: run `sudo tgyt relay` first.")
        return 2

    Path(settings.jobs_dir).mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="relay-selftest-", dir=settings.jobs_dir))
    settings.jobs_dir = str(work / "jobs")
    store = Store(str(work / "selftest.db"))
    await store.connect()

    bot = pyrogram.Client("selftest-bot", api_id=settings.api_id, api_hash=settings.api_hash,
                          bot_token=settings.bot_token, in_memory=True)
    user = pyrogram.Client("selftest-relay", api_id=settings.api_id, api_hash=settings.api_hash,
                           session_string=settings.user_session, in_memory=True, no_updates=True)
    lock = asyncio.Lock()
    results: list[str] = []
    last_activity = time.monotonic()

    @bot.on_message(filters.private & (filters.video | filters.document) & filters.user(settings.owner_tg_id))
    async def on_media(_client, message):
        nonlocal last_activity
        async with lock:
            media = message.video or message.document
            size = media.file_size or 0
            name = getattr(media, "file_name", None) or "video"
            route = describe_path(size, True)
            print(f"RECEIVED: {name} {size} bytes -> {route}", flush=True)
            status = await message.reply(f"Self-test: {name} ({size / 1024 / 1024:.0f} MB) via {route}")
            job_id = await store.create_job(
                settings.owner_tg_id, message.chat.id, tg_file_id=media.file_id,
                tg_file_unique_id=media.file_unique_id, source_chat_id=message.chat.id,
                source_message_id=message.id, file_name=name, size_bytes=size)
            reporter = ProgressReporter(bot, message.chat.id, status.id)
            reporter.start()
            started = time.monotonic()
            try:
                dest = await downloader.download_job(bot, user, store, job_id, reporter)
                line = format_result(name, size, dest.stat().st_size, time.monotonic() - started, route)
            except Exception as exc:  # report every failure kind; the type name is the useful part
                line = f"FAIL: {name} {size} bytes via {route}: {type(exc).__name__}: {str(exc)[:200]}"
            finally:
                await reporter.stop()
                downloader.cleanup_job_dir(job_id)
            free_gb = shutil.disk_usage(settings.jobs_dir).free / 1024**3
            results.append(line)
            print(f"{line} | disk free {free_gb:.1f} GB", flush=True)
            await message.reply(line)
            last_activity = time.monotonic()

    await bot.start()
    await user.start()
    try:
        me = await user.get_me()
        print(f"Relay account premium: {bool(getattr(me, 'is_premium', False))}")
        print(f"Max file size setting: {settings.max_file_bytes} bytes")
        print(f"Ready. Send test files to the bot from the owner account. Exits after {idle_exit_s}s idle "
              "(or Ctrl-C).", flush=True)
        while lock.locked() or time.monotonic() - last_activity < idle_exit_s:
            await asyncio.sleep(5)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await bot.stop()
        await user.stop()
        await store.close()
        shutil.rmtree(work, ignore_errors=True)
    print("\n== SUMMARY ==")
    for line in results:
        print(line)
    return 0 if results and all(r.startswith("PASS") for r in results) else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--idle-exit", type=int, default=1800, help="exit after this many idle seconds (default 1800)")
    args = ap.parse_args()
    try:
        sys.exit(asyncio.run(run(args.idle_exit)))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
