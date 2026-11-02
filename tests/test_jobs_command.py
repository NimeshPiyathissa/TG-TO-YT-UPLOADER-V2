"""/jobs always answers an authorised user: active uploads with progress, recent history, or a clear
"nothing here" message -- never silence. Replies go through Kurigram's real HTML parser."""
from __future__ import annotations

from types import SimpleNamespace

from pyrogram.parser.html import HTML

from bot import progress_hub
from bot.handlers import jobs as jobs_handlers

OWNER = 1          # tests/conftest.py sets OWNER_TG_ID=1
STRANGER = 999


class FakeApp:
    def __init__(self):
        self.handlers = {}

    def on_message(self, _flt):
        def deco(fn):
            self.handlers[fn.__name__] = fn
            return fn
        return deco

    def on_callback_query(self, *_a, **_k):
        return lambda fn: fn


class FakeMessage:
    def __init__(self, user_id=OWNER, text="/jobs"):
        self.from_user = SimpleNamespace(id=user_id, username="u", first_name="Tester")
        self.text = text
        self.replies = []

    async def reply(self, text, **kwargs):
        self.replies.append(text)


async def run_jobs(store, user_id=OWNER) -> str:
    app = FakeApp()
    jobs_handlers.register(app, store, queue=object())
    msg = FakeMessage(user_id)
    await app.handlers["jobs_handler"](None, msg)
    assert len(msg.replies) == 1, "/jobs must answer exactly once"
    return msg.replies[0]


async def plain(html_text: str) -> str:
    return (await HTML(None).parse(html_text))["message"]


async def add_job(store, state, title=None, user=OWNER):
    job_id = await store.create_job(user, user, source_chat_id=user, source_message_id=1, size_bytes=1000)
    await store.conn.execute("UPDATE jobs SET state = ?, title = ? WHERE id = ?", (state, title, job_id))
    await store.conn.commit()
    return job_id


async def test_no_jobs_at_all(store):
    assert await run_jobs(store) == "No jobs yet -- send a video to get started."


async def test_only_finished_jobs_say_no_active_uploads_and_list_history(store):
    done = await add_job(store, "DONE", "Holiday")
    cancelled = await add_job(store, "CANCELLED")
    failed = await add_job(store, "FAILED", "Broken file")
    text = await plain(await run_jobs(store))
    assert text.startswith("No active uploads.")
    assert f"✅ #{done} DONE Holiday" in text
    assert f"#{cancelled} CANCELLED" in text
    assert f"#{failed} FAILED Broken file" in text
    assert "/cancel" not in text                     # nothing to cancel


async def test_active_job_shows_state_progress_and_cancel_hint(store):
    queued = await add_job(store, "QUEUED")
    running = await add_job(store, "DOWNLOADING")
    progress_hub.record(running, "download", 250, 1000)
    try:
        text = await plain(await run_jobs(store))
    finally:
        progress_hub.clear(running)
    assert text.startswith("Active uploads")
    assert f"🟢 #{queued} QUEUED" in text
    assert f"🟢 #{running} DOWNLOADING · download 25%" in text
    assert "Use /cancel <id> to cancel an active job." in text


async def test_titles_are_escaped(store):
    await add_job(store, "DONE", "<b>not bold</b> & co")
    raw = await run_jobs(store)
    parsed = await HTML(None).parse(raw)
    assert "<b>not bold</b> & co" in parsed["message"]
    assert not any(type(e).__name__ == "MessageEntityBold" and parsed["message"][e.offset:e.offset + e.length] == "not bold"
                   for e in parsed["entities"] or [])


async def test_only_the_senders_jobs_are_listed(store):
    await add_job(store, "DONE", "mine")
    await store.conn.execute("INSERT INTO tg_users (tg_user_id, role, added_by, added_at) VALUES (5, 'uploader', 'test', 'now')")
    await store.conn.commit()
    await add_job(store, "DONE", "someone else's", user=5)
    text = await plain(await run_jobs(store))
    assert "mine" in text and "someone else's" not in text


async def test_unauthorised_user_is_refused_not_ignored(store):
    await add_job(store, "DONE", "secret")
    text = await run_jobs(store, user_id=STRANGER)
    assert "not authorised" in text and str(STRANGER) in text and "secret" not in text


async def test_database_error_still_gets_a_reply(store, monkeypatch):
    async def broken(*_a, **_k):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(store, "list_jobs_for_user", broken)
    assert await run_jobs(store) == jobs_handlers.LOAD_FAILED
