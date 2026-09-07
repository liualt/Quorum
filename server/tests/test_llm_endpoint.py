"""The Agora custom-LLM endpoint: bearer auth, OpenAI-shaped streaming, spoken text only."""

import json

import pytest

from app.routes.deps import llm_token
from app.storage import repo
from tests.conftest import ORIGIN


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
