"""The panel must refuse to be framed by other sites (clickjacking), on every kind of response."""
import httpx

from web.app import create_app


async def test_every_response_forbids_framing(store):
    app = create_app(store)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        responses = [
            await c.get("/login"),                       # public page
            await c.get("/channels"),                    # redirect to login
            await c.get("/events"),                      # 401 for the live stream
            await c.get("/static/app.css"),              # static file
        ]
    assert [r.status_code for r in responses] == [200, 303, 401, 200]
    for r in responses:
        assert r.headers["x-frame-options"] == "DENY", r.request.url
        assert r.headers["content-security-policy"] == "frame-ancestors 'none'", r.request.url
        assert r.headers["referrer-policy"] == "same-origin", r.request.url
