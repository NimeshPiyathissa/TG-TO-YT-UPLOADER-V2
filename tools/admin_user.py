#!/usr/bin/env python3
"""Create an admin-panel user, or reset a forgotten password / lost authenticator.

Used by the installer (so the admin password never has to sit in the env file) and by
`sudo tgyt admin`. Run from the install directory as the service user, with TGYT_ENV_FILE
pointing at the env file:

    printf '%s' "$PASSWORD" | python tools/admin_user.py --username admin --password-stdin
    python tools/admin_user.py --username admin --reset-totp      # lost authenticator app

The password is read from stdin (or prompted, hidden) -- never from argv, so it can't leak
into `ps` output or shell history.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MIN_PASSWORD_LENGTH = 12
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def password_problem(password: str) -> str | None:
    """Return why ``password`` is too weak, or None if it is acceptable."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"must be at least {MIN_PASSWORD_LENGTH} characters"
    classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]"))
    if classes < 3:
        return "must mix at least 3 of: lowercase, uppercase, digits, symbols"
    if len(set(password)) < 6:
        return "uses too few different characters"
    return None


async def run(args: argparse.Namespace) -> int:
    from bot import security
    from bot.config import settings
    from db.store import Store

    store = Store(settings.db_path)
    await store.connect()
    try:
        row = await store.get_app_user_by_username(args.username)
        if args.reset_totp:
            if row is None:
                print(f"No such user: {args.username}", file=sys.stderr)
                return 1
            await store.set_totp_secret(row["id"], None)
            await store.conn.execute(
                "UPDATE app_users SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (row["id"],))
            await store.conn.commit()
            print(f"Authenticator removed for '{args.username}'. "
                  + ("They will be asked to enrol a new one at next login." if settings.require_totp
                     else "TOTP is now off for this user."))
            return 0

        if args.password_stdin:
            password = sys.stdin.readline().rstrip("\r\n")
        else:
            password = getpass.getpass("New password (hidden): ")
            if password != getpass.getpass("Repeat password: "):
                print("Passwords do not match.", file=sys.stderr)
                return 1
        problem = password_problem(password)
        if problem:
            print(f"Password rejected: {problem}.", file=sys.stderr)
            return 1
        pw_hash = security.hash_password(password)
        if row is None:
            await store.create_app_user(args.username, pw_hash, role="owner")
            print(f"Created admin user '{args.username}'.")
        else:
            await store.set_app_user_password(row["id"], pw_hash)
            await store.conn.execute(
                "UPDATE app_users SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (row["id"],))
            await store.conn.commit()
            print(f"Password updated for '{args.username}' (lockout cleared).")
        return 0
    finally:
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
    parser.add_argument("--reset-totp", action="store_true", help="remove the user's authenticator (2FA) secret")
    args = parser.parse_args()
    if not USERNAME_RE.match(args.username):
        sys.exit("Username must be 3-32 characters: letters, digits, dot, dash, underscore.")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
