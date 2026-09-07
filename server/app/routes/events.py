"""The session event stream.

A client reconnects with the last sequence number it saw, so the stream replays
from the database before it hands over to the live bus. Subscribing happens
first and the replay's high-water mark then suppresses the overlap, because
losing an event to that gap is worse than sending one twice.
"""

import json

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.routes.deps import require_participant
from app.storage import repo

router = APIRouter(prefix="/api/interviews", tags=["events"])

PING_SECONDS = 15


@router.get("/{interview_id}/events")
async def stream_events(
    interview_id: str,
    request: Request,
    after: int = 0,
    participant=Depends(require_participant),
) -> EventSourceResponse:
    app = request.app
    bus = app.state.bus
    queue = bus.subscribe(interview_id)

    async def publish():
        try:
            last_seq = after
            for event in repo.list_events(app.state.db, interview_id, after):
                last_seq = event["seq"]
                yield _message(event)
            while True:
                event = await queue.get()
                if event["seq"] <= last_seq:
                    continue  # already sent from the replay
                last_seq = event["seq"]
                yield _message(event)
        finally:
            bus.unsubscribe(interview_id, queue)

    return EventSourceResponse(publish(), ping=PING_SECONDS)


def _message(event: dict) -> dict:
    return {"event": event["type"], "data": json.dumps(event)}
