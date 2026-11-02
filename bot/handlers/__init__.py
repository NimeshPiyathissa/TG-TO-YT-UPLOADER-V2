"""Telegram handlers. ``register_all`` is the one place that decides their order.

Order matters: within a dispatcher group Kurigram runs only the FIRST handler whose filter matches.
The caption step's text handler must therefore never match commands (see caption.py), or every
command registered after it would be swallowed -- which is how /jobs and /cancel went silent.
"""
from __future__ import annotations


def register_all(app, store, queue) -> None:
    from bot.handlers import caption, channels, ingest, jobs, start

    start.register(app, store)
    channels.register(app, store)
    ingest.register(app, store, queue)
    caption.register(app, store, queue)
    jobs.register(app, store, queue)
