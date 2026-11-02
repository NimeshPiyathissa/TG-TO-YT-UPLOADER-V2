"""Every keyword argument the app passes to Telegram (kurigram) methods must exist in the installed
kurigram version.

The handler tests use fake message objects, so a library upgrade that removes an argument would
otherwise only show up in production. That happened with kurigram 2.2, which dropped
`disable_web_page_preview` in favour of `link_preview_options` and broke /start.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

pyrogram = pytest.importorskip("pyrogram")
from pyrogram import Client, types  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# Method name as called in our code -> the kurigram callables it can resolve to.
TELEGRAM_METHODS = {
    "reply": [types.Message.reply],
    "reply_text": [types.Message.reply_text],
    "edit_text": [types.Message.edit_text],
    "edit_message_text": [types.CallbackQuery.edit_message_text, Client.edit_message_text],
    "send_message": [Client.send_message],
    "answer": [types.CallbackQuery.answer],
    "forward_messages": [Client.forward_messages],
    "download_media": [Client.download_media, types.Message.download],
}


def accepted(fns) -> tuple[set[str], bool]:
    names, var_kw = set(), False
    for fn in fns:
        for p in inspect.signature(fn).parameters.values():
            names.add(p.name)
            var_kw |= p.kind is inspect.Parameter.VAR_KEYWORD
    return names, var_kw


def telegram_calls():
    for folder in ("bot", "web", "tools"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in TELEGRAM_METHODS):
                    yield path.relative_to(ROOT).as_posix(), node.lineno, node.func.attr, \
                        [k.arg for k in node.keywords if k.arg is not None]


def test_finds_the_calls_it_is_meant_to_check():
    assert sum(1 for _ in telegram_calls()) > 30


def test_every_keyword_exists_in_the_installed_kurigram():
    problems = []
    for where, line, method, keywords in telegram_calls():
        names, var_kw = accepted(TELEGRAM_METHODS[method])
        if var_kw:
            continue
        problems += [f"{where}:{line} .{method}({kw}=...)" for kw in keywords if kw not in names]
    assert not problems, "kurigram does not accept:\n" + "\n".join(problems)
