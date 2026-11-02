"""Panel Restart button: no sudo (the unit's NoNewPrivileges blocks it); the app exits cleanly and
systemd's Restart=always starts it again."""
from __future__ import annotations

import os
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest

from web.routes import settings as settings_routes

ROOT = Path(__file__).resolve().parent.parent


class FakeStore:
    def __init__(self):
        self.audit = []

    async def write_audit(self, *args):
        self.audit.append(args)


def fake_request(store):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(store=store)),
                           session={"username": "admin"})


async def test_restart_under_systemd_schedules_a_clean_sigterm(monkeypatch):
    monkeypatch.setenv("INVOCATION_ID", "0123abcd")
    scheduled = []

    class FakeLoop:
        def call_later(self, delay, fn, *args):
            scheduled.append((delay, fn, args))

    monkeypatch.setattr(settings_routes.asyncio, "get_running_loop", lambda: FakeLoop())
    store = FakeStore()
    request = fake_request(store)
    resp = await settings_routes.restart_service(request, csrf_ok=None)

    assert resp.status_code in (302, 303)
    assert scheduled == [(settings_routes.RESTART_DELAY_SECONDS, os.kill, (os.getpid(), signal.SIGTERM))]
    assert store.audit and store.audit[0][-1] == "service_restart_requested"
    assert request.session["flash"][0]["level"] == "success"


async def test_restart_outside_systemd_refuses_instead_of_just_stopping(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    monkeypatch.setattr(settings_routes.asyncio, "get_running_loop",
                        lambda: pytest.fail("must not schedule a shutdown outside systemd"))
    request = fake_request(FakeStore())
    await settings_routes.restart_service(request, csrf_ok=None)
    assert request.session["flash"][0]["level"] == "error"


def test_restart_never_shells_out_to_sudo():
    body = (ROOT / "web" / "routes" / "settings.py").read_text(encoding="utf-8").split("def restart_service")[1].split("\ndef ")[0]
    assert '"sudo"' not in body and "create_subprocess" not in body


def test_unit_restarts_after_a_clean_exit():
    unit = (ROOT / "deploy" / "tgyt.service").read_text(encoding="utf-8")
    assert "Restart=always" in unit and "NoNewPrivileges=true" in unit


def test_installer_no_longer_grants_sudo_to_the_service():
    installer = (ROOT / "deploy" / "install.sh").read_text(encoding="utf-8")
    assert "NOPASSWD" not in installer
    assert "rm -f /etc/sudoers.d/tgyt-restart" in installer


def test_installer_uses_package_names_that_exist_on_26_04():
    installer = (ROOT / "deploy" / "install.sh").read_text(encoding="utf-8")
    assert " dnsutils" not in installer.replace("bind9-dnsutils", "")
