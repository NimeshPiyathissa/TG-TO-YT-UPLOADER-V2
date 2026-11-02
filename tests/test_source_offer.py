"""AGPL-3.0 section 13: everyone using the bot or the panel is offered the source code."""
from __future__ import annotations

import re
from pathlib import Path

import httpx

from bot import security
from bot.config import settings
from bot.handlers import start as start_handlers
from tests.test_premium_emoji import run_command
from web.app import create_app

ROOT = Path(__file__).resolve().parent.parent


async def test_help_links_to_the_source(store):
    text, kwargs = await run_command(start_handlers, store, "help")
    assert f'<a href="{settings.source_code_url}">' in text and "AGPL-3.0" in text
    assert kwargs["link_preview_options"].is_disabled


async def test_panel_offers_the_source_before_and_after_login(store):
    await store.create_app_user("admin", security.hash_password("a-long-test-password!"), role="owner")
    app = create_app(store)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        login = await c.get("/login")
        assert f'href="{settings.source_code_url}"' in login.text
        token = re.search(r'name="csrf_token" value="([^"]+)"', login.text).group(1)
        r = await c.post("/login", data={"csrf_token": token, "username": "admin", "password": "a-long-test-password!"})
        assert r.status_code == 303
        dashboard = await c.get("/")
    assert dashboard.status_code == 200
    assert dashboard.text.count(f'href="{settings.source_code_url}"') >= 1


def test_licence_files_agree():
    licence = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert licence.lstrip().startswith("GNU AFFERO GENERAL PUBLIC LICENSE") and "Version 3, 19 November 2007" in licence
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "license-AGPL--3.0--only" in readme and "AGPL-3.0-only" in readme and "GNU Affero General Public License" in readme
    assert "SOURCE_CODE_URL=https://github.com/NimeshPiyathissa/TG-TO-YT-UPLOADER-V2" in (ROOT / ".env.example").read_text(encoding="utf-8")
