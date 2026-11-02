"""HTML message-formatting helpers.

Kurigram's HTML parser is used for every bot message. Custom emoji use the Bot API
spelling ``<tg-emoji emoji-id="...">`` (Kurigram 2.2+; 2.1 only knew ``<emoji id>``).
Entity offsets are computed by the parser in UTF-16 units. Anything user- or
Google-supplied must go through ``esc()``.

Telegram itself decides whether a bot may send custom emoji in message text: only if the
bot's owner has Telegram Premium or the bot has a Fragment username. When the bot isn't allowed, Telegram silently removes those entities and the client shows the
fallback glyph instead, so every fallback here is the emoji Telegram lists for that id.
``check_custom_emoji()`` notices that case and logs the reason once.
"""
from __future__ import annotations

import html

import structlog
from pyrogram.enums import MessageEntityType

log = structlog.get_logger(__name__)

# Custom emoji ids -> fallback unicode glyph shown when a client can't render them.
EMOJI_PLAY = (6141129078033358884, "▶️")      # TG -> YouTube Uploader
EMOJI_CHANNELS = (6140885579157479105, "📱")
EMOJI_UPLOADS = (5456140674028019486, "⚡️")
EMOJI_OTHER = (5341715473882955310, "⚙️")
EMOJI_LINKED = (6212828884115660309, "🔗")
EMOJI_QUOTA = (5422360266618707867, "📊")
EMOJI_WARN = (5420323339723881652, "⚠️")
EMOJI_OK = (6138698461551273388, "✅")
EMOJI_STATUS = (5899885107228971015, "⚡️")

# Inline button icons, sent as icon_custom_emoji_id (Kurigram 2.2+). The glyph is only a reference.
BTN_MY_CHANNELS = (5429277560557019280, "▶️")
BTN_STATUS = (5899885107228971015, "⚡️")
BTN_HELP = (5436113877181941026, "❓")


def esc(value: object) -> str:
    """Escape dynamic text for use inside an HTML-parsed message."""
    return html.escape(str(value), quote=False)


def b(value: object) -> str:
    return f"<b>{esc(value)}</b>"


def emoji(spec: tuple[int, str]) -> str:
    emoji_id, glyph = spec
    return f'<tg-emoji emoji-id="{emoji_id}">{glyph}</tg-emoji>'


def user_link(user_id: int, first_name: str | None) -> str:
    """Bold + clickable name linking to the user's Telegram profile."""
    return f'<b><a href="tg://user?id={int(user_id)}">{esc(first_name or "there")}</a></b>'

# /addyt and /channels
EMOJI_ADD = (5397916757333654639, "➕")
EMOJI_POINT = (6181244167067273165, "👉")
EMOJI_STAR = (5418017294473251153, "⭐")
EMOJI_CHANNEL_OK = (6156468734119642784, "✅")
EMOJI_SEP = (5972223227055836399, "🔻")


_stripped_reported = False
_kept_reported = False


def check_custom_emoji(sent: object, html_text: str) -> bool:
    """Whether Telegram kept the custom emoji of a message we just sent.

    Logs once per process which way it went. When the text had custom emoji but the message
    Telegram returned has none, the bot isn't allowed to send them and users see the fallbacks.
    """
    global _stripped_reported, _kept_reported
    if "<tg-emoji" not in html_text or sent is None:
        return True
    kept = any(getattr(e, "type", None) == MessageEntityType.CUSTOM_EMOJI for e in (getattr(sent, "entities", None) or []))
    if kept and not _kept_reported:
        _kept_reported = True
        log.info("fmt.custom_emoji_delivered")
    elif not kept and not _stripped_reported:
        _stripped_reported = True
        log.warning(
            "fmt.custom_emoji_removed_by_telegram",
            detail="Telegram dropped every custom emoji from a bot message, so users see the plain fallback emoji. "
                   "Telegram only allows it if the bot's owner (BotFather) has Telegram Premium or the bot has a "
                   "Fragment username; this app can't change that.",
        )
    return kept
