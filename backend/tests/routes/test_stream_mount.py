"""Tests confirming the SSE stream router is mounted on the assembled app.

Note: httpx's ASGITransport (which backs fastapi.testclient.TestClient) runs
the entire ASGI application call to completion before returning a response —
it cannot signal a mid-stream client disconnect. Since `stream.py`'s
generator is intentionally infinite (it only stops when
`request.is_disconnected()` becomes true), driving it through TestClient
would hang forever. Instead, this test calls the app's ASGI callable
directly with a receive() that reports http.disconnect after the first
poll, which is exactly the signal the frozen stream generator watches for.
"""

from __future__ import annotations

import asyncio

from app.main import create_app


async def test_stream_endpoint_mounted():
    app = create_app()

    sent_messages: list[dict] = []
    call_count = 0

    async def receive() -> dict:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent_messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/api/stream/prices",
        "raw_path": b"/api/stream/prices",
        "query_string": b"",
        "headers": [],
        "server": ("testserver", 80),
        "client": ("testclient", 123),
        "scheme": "http",
        "root_path": "",
    }

    await asyncio.wait_for(app(scope, receive, send), timeout=5)

    start = next(m for m in sent_messages if m["type"] == "http.response.start")
    assert start["status"] == 200
    headers = dict(start["headers"])
    assert headers[b"content-type"].startswith(b"text/event-stream")

    body_messages = [m for m in sent_messages if m["type"] == "http.response.body"]
    assert any(m.get("body") for m in body_messages)
