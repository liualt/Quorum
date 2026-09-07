"""The custom-model endpoint the Agora voice agent calls for every candidate turn.

This is not an `/api` route: no cookie, no Origin check. The agent's whole
credential is a per-interview bearer token, and what it gets back is an
OpenAI-shaped stream of spoken text only — the controller keeps ids and
state in the record, never in the words (PRD section 9).
"""

import hmac
import json
import time
from collections.abc import AsyncIterator
from contextlib import aclosing

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app import ids
from app.routes.deps import llm_token
from app.routes.events import STREAM_HEADERS
from app.storage import repo

router = APIRouter(prefix="/llm", tags=["llm"])

MODEL_NAME = "quorum-controller"


@router.post("/{interview_id}/chat/completions")
async def chat_completions(interview_id: str, request: Request) -> StreamingResponse:
    app = request.app
    settings = app.state.settings
    if not settings.llm_endpoint_enabled:
        raise HTTPException(503, "the model endpoint is not configured")
    expected = llm_token(settings, interview_id).encode()
    if not hmac.compare_digest(expected, _bearer(request).encode()):
        raise HTTPException(401, "invalid bearer token")
    if repo.get_interview(app.state.db, interview_id) is None:
        raise HTTPException(404, "interview not found")

    try:
        body = await request.json()
    except ValueError as error:
        raise HTTPException(400, "the request body is not JSON") from error
    if not isinstance(body, dict) or body.get("stream") is not True:
        raise HTTPException(400, "only streaming completions are served")
    text = _last_user_text(body.get("messages")).strip()
    if not text:
        raise HTTPException(400, "the transcript is empty")

    turn = app.state.controller.run_turn(interview_id, text, source="candidate")
    return ClosingStreamingResponse(
        _completion_chunks(turn), media_type="text/event-stream", headers=STREAM_HEADERS
    )


class ClosingStreamingResponse(StreamingResponse):
    """A streaming response that closes its iterator the moment the client is gone.

    Starlette leaves the body iterator suspended on a disconnect, so the turn
    behind it would be recorded whenever the garbage collector got to it. The
    interrupted segment has to land now, in order, and the model connection
    has to be released now, so the iterator is closed on every way out.
    """

    async def stream_response(self, send) -> None:
        try:
            await super().stream_response(send)
        finally:
            aclose = getattr(self.body_iterator, "aclose", None)
            if aclose is not None:
                await aclose()


def _bearer(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def _last_user_text(messages) -> str:
    """The newest user message, whether its content is a string or text parts."""
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        return ""
    return ""


async def _completion_chunks(turn: AsyncIterator[str]) -> AsyncIterator[str]:
    completion_id = ids.new_id("chatcmpl")
    created = int(time.time())

    def line(delta: dict, finish_reason: str | None = None) -> str:
        chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": MODEL_NAME,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
        return f"data: {json.dumps(chunk)}\n\n"

    yield line({"role": "assistant", "content": ""})
    async with aclosing(turn) as stream:
        async for piece in stream:
            yield line({"content": piece})
    yield line({}, "stop")
    yield "data: [DONE]\n\n"
