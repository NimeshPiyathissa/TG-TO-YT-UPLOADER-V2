"""Premium (custom) emoji in /start, /addyt and /channels.

The handlers run for real against a fake bot client; their HTML goes through Kurigram's real
parser, so these tests check the entities Telegram actually receives: custom emoji ids,
the bold clickable profile name, escaping, and the inline-button icons.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from pyrogram import types as tg_types
from pyrogram.enums import MessageEntityType
from pyrogram.parser.html import HTML

from bot import fmt
from bot.handlers import channels as channels_handlers
from bot.handlers import start as start_handlers

# The ids configured before the VPS rebuild (all verified with Telegram's getCustomEmojiStickers).
START_IDS = {
    "TG → YouTube Uploader": 6141129078033358884, "Channels": 6140885579157479105,
    "Uploads": 5456140674028019486, "Other": 5341715473882955310, "Linked channels": 6212828884115660309,
    "Uploads left today": 5422360266618707867, "Warning": 5420323339723881652, "Success": 6138698461551273388,
}
BUTTON_ICONS = {"MY CHANNELS": 5429277560557019280, "STATUS": 5899885107228971015, "HELP": 5436113877181941026}
EXP = "2099-01-01T00:00:00+00:00"


class FakeApp:
    """Collects the handlers a module registers, keyed by command name."""

    def __init__(self):
        self.commands = {}

    def on_message(self, flt):
        names = [c for c in getattr(flt, "commands", None) or _commands_of(flt)]

        def deco(fn):
            for n in names:
                self.commands[n] = fn
            return fn
        return deco

    def on_callback_query(self, *_a, **_k):
        return lambda fn: fn


def _commands_of(flt):
    # filters.command("x") & filters.private -> walk the combined filter for its command set
    for part in (getattr(flt, "base", None), getattr(flt, "other", None)):
        if part is not None and getattr(part, "commands", None):
            return part.commands
    return []


class FakeMessage:
    def __init__(self, user_id=1, first_name="Nimesh"):
        self.from_user = SimpleNamespace(id=user_id, username="someone", first_name=first_name)
        self.replies = []

    async def reply(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return SimpleNamespace(entities=[])


async def run_command(module, store, name, **msg_kwargs):
    app = FakeApp()
    module.register(app, store)
    message = FakeMessage(**msg_kwargs)
    await app.commands[name](None, message)
    assert message.replies, f"/{name} sent nothing"
    return message.replies[-1]


async def entities_of(html_text):
    parsed = await HTML(None).parse(html_text)
    return parsed["message"], parsed["entities"] or []


def custom_ids(entities):
    return [e.document_id for e in entities if type(e).__name__ == "MessageEntityCustomEmoji"]


async def add_channel(store, channel_id, title, *, default=False):
    pk = await store.upsert_yt_channel(channel_id, title, f"@{title}", None, b"r", b"a", EXP, "s", "tester")
    if default:
        await store.set_default_channel(pk)
    return pk


# ---------------------------------------------------------------------------------- /start

async def test_start_uses_every_original_premium_emoji(store, monkeypatch):
    monkeypatch.setattr(start_handlers.settings, "project_audited", False)
    text, _ = await run_command(start_handlers, store, "start")
    _, entities = await entities_of(text)
    ids = custom_ids(entities)
    for section, emoji_id in START_IDS.items():
        assert emoji_id in ids, f"{section} emoji ({emoji_id}) missing from /start"


async def test_start_name_is_bold_clickable_and_escaped(store):
    text, _ = await run_command(start_handlers, store, "start", first_name="<b>Eve</b> & co")
    plain, entities = await entities_of(text)
    assert "<b>Eve</b> & co" in plain              # shown literally, not interpreted as HTML
    mention = next(e for e in entities if type(e).__name__ == "InputMessageEntityMentionName")
    assert mention.user_id == 1
    bolds = [e for e in entities if type(e).__name__ == "MessageEntityBold"]
    assert any(b.offset <= mention.offset and b.offset + b.length >= mention.offset + mention.length for b in bolds)
    assert "**" not in plain                        # HTML formatting, never literal Markdown


async def test_start_buttons_have_premium_icons_and_plain_labels(store):
    _, kwargs = await run_command(start_handlers, store, "start")
    row = kwargs["reply_markup"].inline_keyboard[0]
    assert [(b.text, b.icon_custom_emoji_id, b.callback_data) for b in row] == [
        ("MY CHANNELS", BUTTON_ICONS["MY CHANNELS"], "menu:channels"),
        ("STATUS", BUTTON_ICONS["STATUS"], "menu:status"),
        ("HELP", BUTTON_ICONS["HELP"], "menu:help"),
    ]
    assert all("<" not in b.text for b in row)


async def test_start_buttons_serialize_the_icon_for_telegram(store):
    _, kwargs = await run_command(start_handlers, store, "start")
    raw_row = (await kwargs["reply_markup"].write(None)).rows[0].buttons
    assert [getattr(getattr(b, "style", None), "icon", None) for b in raw_row] == list(BUTTON_ICONS.values())


# ---------------------------------------------------------------------------------- /addyt

async def test_addyt_premium_emoji(store):
    await store.set_oauth_client("cid.apps.googleusercontent.com", b"enc", "web", "proj", "admin")
    text, kwargs = await run_command(channels_handlers, store, "addyt")
    plain, entities = await entities_of(text)
    assert "Add a YouTube Channel" in plain
    assert custom_ids(entities) == [5397916757333654639, 6181244167067273165]   # add, then the pointer
    assert kwargs["link_preview_options"].is_disabled is True


async def test_addyt_without_oauth_client_still_answers(store):
    text, _ = await run_command(channels_handlers, store, "addyt")
    assert "No OAuth client is configured yet" in text


# ---------------------------------------------------------------------------------- /channels

async def test_channels_list_numbering_default_star_and_separator(store):
    await add_channel(store, "UC1", "Alpha", default=True)
    await add_channel(store, "UC2", "Beta")
    text, _ = await run_command(channels_handlers, store, "channels")
    plain, entities = await entities_of(text)
    ids = custom_ids(entities)
    assert ids[0] == 6212828884115660309                  # "Linked channels" heading
    assert 5418017294473251153 in ids                     # star on the default channel
    assert ids.count(5972223227055836399) == 2            # one separator per channel
    assert ids.count(6156468734119642784) == 2            # success mark on each active channel
    assert "1." in plain and "2." in plain


# ---------------------------------------------------------------------------------- ids + fallback detection

def test_every_emoji_id_is_a_19_digit_telegram_id():
    specs = {n: v for n, v in vars(fmt).items() if n.startswith(("EMOJI_", "BTN_"))}
    assert len(specs) == 17
    for name, (emoji_id, glyph) in specs.items():
        assert len(str(emoji_id)) == 19, name
        assert glyph and "<" not in glyph, name


def test_emoji_markup_is_the_bot_api_spelling():
    assert fmt.emoji(fmt.EMOJI_OK) == '<tg-emoji emoji-id="6138698461551273388">✅</tg-emoji>'


def test_check_custom_emoji_reports_when_telegram_strips_them(monkeypatch):
    warnings = []
    infos = []
    monkeypatch.setattr(fmt, "_stripped_reported", False)
    monkeypatch.setattr(fmt, "_kept_reported", False)
    monkeypatch.setattr(fmt.log, "warning", lambda event, **kw: warnings.append(event))
    monkeypatch.setattr(fmt.log, "info", lambda event, **kw: infos.append(event))
    html_text = fmt.emoji(fmt.EMOJI_OK) + " hi"
    kept = SimpleNamespace(entities=[SimpleNamespace(type=MessageEntityType.CUSTOM_EMOJI)])
    stripped = SimpleNamespace(entities=[SimpleNamespace(type=MessageEntityType.BOLD)])

    assert fmt.check_custom_emoji(kept, html_text) is True
    assert fmt.check_custom_emoji(stripped, html_text) is False
    assert fmt.check_custom_emoji(stripped, html_text) is False
    assert warnings == ["fmt.custom_emoji_removed_by_telegram"]          # logged once, not per message
    assert fmt.check_custom_emoji(kept, html_text) is True
    assert infos == ["fmt.custom_emoji_delivered"]
    assert fmt.check_custom_emoji(stripped, "no premium emoji here") is True
    assert fmt.check_custom_emoji(None, html_text) is True


def test_inline_button_supports_icons_in_the_installed_kurigram():
    btn = tg_types.InlineKeyboardButton("X", callback_data="x", icon_custom_emoji_id=1)
    assert btn.icon_custom_emoji_id == 1
