"""The session event stream: replay from the database, then live from the bus.

`httpx.ASGITransport` buffers a whole response before it returns one, so it can
read the 401 but never an open stream. The stream itself is therefore driven at
the ASGI layer, which is also the only way to send the `http.disconnect` that a
browser closing an `EventSource` sends.
"""

import asyncio
import json

import httpx
import pytest

from app.storage.events import emit
from tests.conftest import ORIGIN

READ_TIMEOUT = 5.0
BLOCK_SEPARATORS = ("\r\n\r\n", "\n\n")


def _split_block(buffer: str) -> tuple[str | None, str]:
    """The first complete SSE block in `buffer`, and what is left after it."""
    ends = [(buffer.find(sep), sep) for sep in BLOCK_SEPARATORS]
    ends = [(index, sep) for index, sep in ends if index != -1]
    if not ends:
        return None, buffer
    index, sep = min(ends)
    return buffer[:index], buffer[index + len(sep):]


def _parse_block(block: str) -> tuple[str | None, dict] | None:
    """`(event, data)` for a block that carries data; None for a bare ping."""
    event_type = None
    data = None
    for line in block.replace("\r\n", "\n").split("\n"):
        if line.startswith("event:"):
            event_type = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data = json.loads(line[len("data:"):].strip())
    return None if data is None else (event_type, data)


class EventStream:
    """Reads an SSE endpoint by calling the ASGI app directly."""

    def __init__(self, app, path: str, query: str, cookie: str):
        self._app = app
        self._path = path
        self._query = query
        self._cookie = cookie
        self._messages: asyncio.Queue = asyncio.Queue()
        self._disconnected = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._buffer = ""
        self.status: int | None = None
        self.headers: dict[str, str] = {}

    async def _receive(self) -> dict:
        await self._disconnected.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: dict) -> None:
        await self._messages.put(message)

    async def __aenter__(self) -> "EventStream":
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": self._path,
            "raw_path": self._path.encode(),
            "query_string": self._query.encode(),
            "root_path": "",
            "headers": [(b"host", b"test"), (b"cookie", self._cookie.encode())],
            "client": ("127.0.0.1", 12345),
            "server": ("test", 80),
        }
        self._task = asyncio.create_task(self._app(scope, self._receive, self._send))
        start = await asyncio.wait_for(self._messages.get(), READ_TIMEOUT)
        assert start["type"] == "http.response.start", start
        self.status = start["status"]
        self.headers = {key.decode(): value.decode() for key, value in start["headers"]}
        return self

    async def __aexit__(self, *exc_info) -> None:
        self._disconnected.set()
        try:
            await asyncio.wait_for(self._task, READ_TIMEOUT)
        except TimeoutError:  # pragma: no cover - only on a stream that ignores disconnect
            self._task.cancel()
            raise

    async def next_event(self) -> tuple[str | None, dict]:
        async def read() -> tuple[str | None, dict]:
            while True:
                block, rest = _split_block(self._buffer)
                if block is not None:
                    self._buffer = rest
                    parsed = _parse_block(block)
                    if parsed is not None:
                        return parsed
                    continue
                message = await self._messages.get()
                assert message["type"] == "http.response.body", message
                self._buffer += message.get("body", b"").decode()

        return await asyncio.wait_for(read(), READ_TIMEOUT)


@pytest.fixture
async def streaming(live_app):
    """An interview created over HTTP, plus the cookie header for its stream."""
    transport = httpx.ASGITransport(app=live_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/interviews",
            json={"display_name": "Ada Lovelace", "consent": True},
            headers=ORIGIN,
        )
        assert created.status_code == 201, created.text
        cookie = f"quorum_candidate={client.cookies['quorum_candidate']}"
        yield client, created.json()["id"], cookie


async def test_the_stream_replays_stored_events_then_delivers_live_ones(live_app, streaming):
    _, interview_id, cookie = streaming
    conn, bus = live_app.state.db, live_app.state.bus
    emit(conn, bus, interview_id, "stage_changed", {"stage": "initial_review"})
    emit(conn, bus, interview_id, "pause_changed", {"paused": True})

    path = f"/api/interviews/{interview_id}/events"
    async with EventStream(live_app, path, "after=0", cookie) as stream:
        assert stream.status == 200
        assert stream.headers["content-type"].startswith("text/event-stream")

        event_type, event = await stream.next_event()
        assert event_type == "stage_changed"
        assert event["seq"] == 1
        assert event["type"] == "stage_changed"
        assert event["payload"] == {"stage": "initial_review"}
        assert event["ts"]

        event_type, event = await stream.next_event()
        assert (event_type, event["seq"], event["payload"]) == ("pause_changed", 2, {"paused": True})

        emit(conn, bus, interview_id, "run_started", {"run": {"id": "run_live"}})
        event_type, event = await stream.next_event()
        assert (event_type, event["seq"]) == ("run_started", 3)

    assert bus._subscribers == {}  # the stream unsubscribed on disconnect


async def test_after_skips_the_events_the_client_already_has(live_app, streaming):
    _, interview_id, cookie = streaming
    conn, bus = live_app.state.db, live_app.state.bus
    emit(conn, bus, interview_id, "stage_changed", {"stage": "initial_review"})
    emit(conn, bus, interview_id, "pause_changed", {"paused": True})

    path = f"/api/interviews/{interview_id}/events"
    async with EventStream(live_app, path, "after=1", cookie) as stream:
        event_type, event = await stream.next_event()

        assert (event_type, event["seq"]) == ("pause_changed", 2)


async def test_the_stream_needs_a_capability(live_app, streaming):
    client, interview_id, _ = streaming
    client.cookies.clear()

    response = await client.get(f"/api/interviews/{interview_id}/events?after=0")

    assert response.status_code == 401
