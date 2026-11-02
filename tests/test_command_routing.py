"""Which handler does Telegram actually run for each command?

Regression: /jobs and /cancel got no reply on the live bot. Within a dispatcher group Kurigram runs only
the FIRST handler whose filter matches, and the caption step's catch-all text handler was registered
before them, so it swallowed both commands. Calling handlers directly (as the other tests do) can't see
that; these tests register everything exactly like bot/main.py and resolve each message the way
Kurigram's dispatcher does.
"""
from __future__ import annotations

import asyncio

import pyrogram
import pytest
from pyrogram.enums import ChatType
from pyrogram.handlers import MessageHandler
from pyrogram.types import Chat, Message, User

from bot.handlers import register_all

COMMANDS = {
    "/start": "start_handler", "/help": "help_handler", "/id": "id_handler", "/status": "status_handler",
    "/channels": "channels_handler", "/addyt": "addyt_handler", "/removeyt": "removeyt_handler",
    "/jobs": "jobs_handler", "/cancel 8": "cancel_handler",
}


@pytest.fixture
async def bot(store):
    app = pyrogram.Client("routing-test", api_id=1, api_hash="0" * 32, bot_token="1:test", in_memory=True)
    app.me = User(id=42, is_bot=True, first_name="Test bot", username="test_bot")
    register_all(app, store, queue=object())
    for _ in range(50):                      # add_handler schedules tasks on the loop
        await asyncio.sleep(0)
    return app


def message(app, text, user_id=1):
    return Message(id=1, chat=Chat(id=user_id, type=ChatType.PRIVATE), text=text, client=app,
                   from_user=User(id=user_id, is_bot=False, first_name="Tester"))


async def first_handler(app, msg):
    """The callback Kurigram's dispatcher would run: first matching MessageHandler per group."""
    for group in app.dispatcher.groups.values():
        for handler in group:
            if isinstance(handler, MessageHandler) and await handler.check(app, msg):
                return handler.callback
    return None


async def test_all_handlers_registered(bot):
    names = {h.callback.__name__ for g in bot.dispatcher.groups.values() for h in g}
    assert set(COMMANDS.values()) <= names and "caption_text" in names


@pytest.mark.parametrize("text, expected", COMMANDS.items())
async def test_every_command_reaches_its_own_handler(bot, text, expected):
    callback = await first_handler(bot, message(bot, text))
    assert callback is not None and callback.__name__ == expected


async def test_command_addressed_to_the_bot_by_name(bot):
    callback = await first_handler(bot, message(bot, "/jobs@test_bot"))
    assert callback.__name__ == "jobs_handler"


async def test_plain_text_still_reaches_the_caption_step(bot):
    callback = await first_handler(bot, message(bot, "My holiday video"))
    assert callback.__name__ == "caption_text"


async def test_commands_work_during_the_caption_step(bot, store):
    """Even while the bot waits for a title, /jobs and /cancel must not be taken as the title."""
    await store.save_flow_session(1, None, "awaiting_caption", {})   # routing depends on filters only
    for text, expected in (("/jobs", "jobs_handler"), ("/cancel 8", "cancel_handler")):
        callback = await first_handler(bot, message(bot, text))
        assert callback.__name__ == expected
