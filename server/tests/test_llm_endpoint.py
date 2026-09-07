"""The Agora custom-LLM endpoint: bearer auth, OpenAI-shaped streaming, spoken text only.

The disconnect tests drive the ASGI app directly, the way `test_sse.py` does,
because `TestClient` cannot hang up halfway through a response.
"""

import asyncio
import json

import pytest
from starlette.requests import ClientDisconnect

from app.routes.deps import llm_token
from app.storage import repo
from tests.conftest import ORIGIN, seed_interview


@pytest.fixture
def settings(settings):
    settings.CUSTOM_LLM_AUTH_SECRET = "llm-secret"
    settings.CUSTOM_LLM_PUBLIC_BASE_URL = "https://quorum.example"
    return settings


@pytest.fixture
def interview_id(client, candidate):
    client.cookies.clear()  # the agent has no cookie; the bearer is its whole credential
    return candidate["id"]


def bearer(app, interview_id: str, token: str | None = None) -> dict:
    return {"Authorization": f"Bearer {token or llm_token(app.state.settings, interview_id)}"}


def completion_request(text, *, stream=True) -> dict:
    return {
        "model": "whatever-agora-sends",
        "stream": stream,
        "messages": [
            {"role": "system", "content": "You are the panel."},
            {"role": "assistant", "content": "Hello there."},
            {"role": "user", "content": text},
        ],
    }


def sse_payloads(body: str) -> list:
    """Every `data:` payload in order; the JSON ones parsed, `[DONE]` kept as is."""
    payloads = []
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        raw = line[len("data:"):].strip()
        payloads.append(raw if raw == "[DONE]" else json.loads(raw))
    return payloads


def test_a_wrong_bearer_is_401(client, app, interview_id):
    response = client.post(
        f"/llm/{interview_id}/chat/completions",
        json=completion_request("Done reading."),
        headers=bearer(app, interview_id, "not-the-token"),
    )

    assert response.status_code == 401


def test_a_missing_bearer_is_401(client, interview_id):
    response = client.post(
        f"/llm/{interview_id}/chat/completions", json=completion_request("Done reading.")
    )

    assert response.status_code == 401


def test_a_non_ascii_bearer_is_401_not_500(client, interview_id):
    response = client.post(
        f"/llm/{interview_id}/chat/completions",
        json=completion_request("Done reading."),
        headers={"Authorization": "Bearer tökén".encode()},  # bytes: httpx will not ASCII-encode it
    )

    assert response.status_code == 401


def test_a_bearer_for_another_interview_is_401(client, app, interview_id):
    response = client.post(
        f"/llm/{interview_id}/chat/completions",
        json=completion_request("Done reading."),
        headers=bearer(app, "itv_other"),
    )

    assert response.status_code == 401


def test_the_endpoint_is_503_when_not_configured(client, app, interview_id):
    app.state.settings.CUSTOM_LLM_AUTH_SECRET = ""

    response = client.post(
        f"/llm/{interview_id}/chat/completions",
        json=completion_request("Done reading."),
        headers={"Authorization": "Bearer anything"},
    )

    assert response.status_code == 503


def test_a_non_streaming_request_is_400(client, app, interview_id):
    response = client.post(
        f"/llm/{interview_id}/chat/completions",
        json=completion_request("Done reading.", stream=False),
        headers=bearer(app, interview_id),
    )

    assert response.status_code == 400


@pytest.mark.parametrize("content", ["", "   ", [{"type": "text", "text": " "}]])
def test_a_blank_transcript_is_400_and_records_nothing(client, app, interview_id, content):
    body = completion_request("")
    body["messages"][-1]["content"] = content

    response = client.post(
        f"/llm/{interview_id}/chat/completions", json=body, headers=bearer(app, interview_id)
    )

    assert response.status_code == 400
    assert repo.list_segments(app.state.db, interview_id) == []


def test_an_unknown_interview_is_404(client, app):
    response = client.post(
        "/llm/itv_missing/chat/completions",
        json=completion_request("Done reading."),
        headers=bearer(app, "itv_missing"),
    )

    assert response.status_code == 404


def test_the_correct_bearer_streams_openai_chunks_of_the_role_segment(client, app, interview_id):
    response = client.post(
        f"/llm/{interview_id}/chat/completions",
        json=completion_request("I have finished reading the brief."),
        headers=bearer(app, interview_id),
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")

    payloads = sse_payloads(response.text)
    assert payloads[-1] == "[DONE]"
    chunks = payloads[:-1]
    assert all(chunk["object"] == "chat.completion.chunk" for chunk in chunks)
    assert all(chunk["model"] == "quorum-controller" for chunk in chunks)
    assert len({chunk["id"] for chunk in chunks}) == 1
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert all(chunk["choices"][0]["finish_reason"] is None for chunk in chunks[:-1])

    spoken = "".join(chunk["choices"][0]["delta"].get("content") or "" for chunk in chunks)
    rows = repo.list_segments(app.state.db, interview_id)
    assert [row["speaker"] for row in rows] == ["candidate", "technical"]
    assert rows[0]["text"] == "I have finished reading the brief."
    assert rows[1]["text"] == spoken
    assert "Technical interviewer" in spoken
    assert "seg_" not in spoken
    assert "run_" not in spoken


def test_the_user_message_may_be_a_list_of_text_parts(client, app, interview_id):
    body = completion_request("")
    body["messages"][-1]["content"] = [
        {"type": "text", "text": "I have finished "},
        {"type": "text", "text": "reading the brief."},
    ]

    response = client.post(
        f"/llm/{interview_id}/chat/completions", json=body, headers=bearer(app, interview_id)
    )

    assert response.status_code == 200
    rows = repo.list_segments(app.state.db, interview_id)
    assert rows[0]["text"] == "I have finished reading the brief."


def test_a_finished_interview_streams_the_goodbye(client, app, interview_id):
    repo.update_interview(app.state.db, interview_id, status="finished")

    response = client.post(
        f"/llm/{interview_id}/chat/completions",
        json=completion_request("One more thing."),
        headers=bearer(app, interview_id),
    )

    assert response.status_code == 200
    chunks = sse_payloads(response.text)[:-1]
    spoken = "".join(chunk["choices"][0]["delta"].get("content") or "" for chunk in chunks)
    assert spoken == "The interview has ended. Thank you."
    assert repo.list_segments(app.state.db, interview_id) == []


def test_a_malformed_body_is_400(client, app, interview_id):
    response = client.post(
        f"/llm/{interview_id}/chat/completions",
        content=b"not json",
        headers={**bearer(app, interview_id), "content-type": "application/json"},
    )

    assert response.status_code == 400


# --- disconnect mid-stream -------------------------------------------------------


async def drive_completion(app, interview_id, *, spec_version, hang_up_after_bodies):
    """POST the completion at the ASGI layer and hang up after N body messages.

    Under ASGI spec 2.4 (the path Starlette takes for servers that declare it)
    the hang-up is an `OSError` from `send`; under 2.3 (what uvicorn declares)
    it is an `http.disconnect` message, which Starlette turns into a cancel.
    Returns the body messages that were sent before the hang-up.
    """
    body = json.dumps(completion_request("I have finished reading the brief.")).encode()
    sent = []
    hung_up = asyncio.Event()
    calls = 0

    async def receive():
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"type": "http.request", "body": body, "more_body": False}
        await hung_up.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body":
            sent.append(message)
            if len(sent) >= hang_up_after_bodies:
                hung_up.set()
                if spec_version == "2.4":
                    raise OSError("connection reset by peer")
        await asyncio.sleep(0)  # a real transport yields to the loop

    token = llm_token(app.state.settings, interview_id)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": f"/llm/{interview_id}/chat/completions",
        "raw_path": f"/llm/{interview_id}/chat/completions".encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"test"),
            (b"authorization", f"Bearer {token}".encode()),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    await asyncio.wait_for(app(scope, receive, send), 5.0)
    return sent


@pytest.fixture
def tracked_stream(live_app, monkeypatch):
    """The scripted model, recording when its stream is closed."""
    closed = []
    real = live_app.state.llm.stream_text

    async def tracked(messages, **kwargs):
        try:
            async for chunk in real(messages, **kwargs):
                yield chunk
        finally:
            closed.append(True)

    monkeypatch.setattr(live_app.state.llm, "stream_text", tracked)
    return closed


async def test_a_hang_up_under_spec_2_4_records_the_interruption_before_returning(live_app, tracked_stream):
    interview = seed_interview(live_app)

    with pytest.raises(ClientDisconnect):
        await drive_completion(live_app, interview["id"], spec_version="2.4", hang_up_after_bodies=3)

    assert_interrupted_now(live_app, interview["id"], tracked_stream)


async def test_a_hang_up_under_spec_2_3_records_the_interruption_before_returning(live_app, tracked_stream):
    interview = seed_interview(live_app)

    sent = await drive_completion(live_app, interview["id"], spec_version="2.3", hang_up_after_bodies=3)

    assert sent[-1]["more_body"] is True  # the response never finished
    assert_interrupted_now(live_app, interview["id"], tracked_stream)


def assert_interrupted_now(app, interview_id, closed):
    """The turn was recorded and the model stream closed by the time the app returned."""
    rows = repo.list_segments(app.state.db, interview_id)
    assert [row["speaker"] for row in rows] == ["candidate", "technical"]
    assert rows[1]["status"] == "interrupted"
    assert rows[1]["text"].startswith("Technical")  # what was said so far, not the whole reply
    assert closed == [True]
    assert app.state.controller.current_generation(interview_id) == 1


def test_cookies_and_origin_play_no_part(client, app, candidate):
    """A candidate cookie without the bearer is refused; the bearer alone, without Origin, is enough."""
    interview_id = candidate["id"]

    with_cookie_only = client.post(
        f"/llm/{interview_id}/chat/completions",
        json=completion_request("hi"),
        headers=ORIGIN,
    )
    assert with_cookie_only.status_code == 401

    client.cookies.clear()
    with_bearer_only = client.post(
        f"/llm/{interview_id}/chat/completions",
        json=completion_request("hi"),
        headers=bearer(app, interview_id),
    )
    assert with_bearer_only.status_code == 200
