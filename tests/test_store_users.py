"""ensure_tg_user must be safe when one person's messages arrive at the same moment.

Regression: a new user sent several messages at once; each handler looked the user up, found nothing and
inserted, so all but one failed with "UNIQUE constraint failed: tg_users.tg_user_id".
"""
import asyncio


async def test_concurrent_first_contact_creates_one_row(store):
    rows = await asyncio.gather(*(store.ensure_tg_user(4242, "u", "First") for _ in range(8)))
    assert {r["tg_user_id"] for r in rows} == {4242}
    assert all(r["role"] == "blocked" for r in rows)
    cur = await store.conn.execute("SELECT count(*) FROM tg_users WHERE tg_user_id = 4242")
    assert (await cur.fetchone())[0] == 1


async def test_existing_user_keeps_role_and_gets_new_name(store):
    await store.ensure_tg_user(7, "old", "Old", default_role="user")
    await store.set_tg_user_role(7, "admin")
    row = await store.ensure_tg_user(7, "new", "New", default_role="blocked")
    assert (row["role"], row["username"], row["first_name"]) == ("admin", "new", "New")
