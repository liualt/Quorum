"""Text turns and the browser's report of what the voice agent actually said."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.routes.deps import require_candidate, require_same_origin

mutations = APIRouter(
    prefix="/api/interviews", tags=["turns"], dependencies=[Depends(require_same_origin)]
)

TURN_TEXT_LIMIT = 4000


class TurnRequest(BaseModel):
    text: str = Field(max_length=TURN_TEXT_LIMIT)


class TranscriptRequest(BaseModel):
    speaker: Literal["agent", "candidate"]
    status: Literal["end", "interrupted"]
    text: str
    turn_id: int


@mutations.post("/{interview_id}/turns")
async def post_turn(
    interview_id: str,
    body: TurnRequest,
    request: Request,
    row=Depends(require_candidate),
) -> dict:
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "say something first")
    return await request.app.state.controller.run_turn_collect(interview_id, text, source="candidate")


@mutations.post("/{interview_id}/transcript")
async def post_transcript(
    interview_id: str,
    body: TranscriptRequest,
    request: Request,
    row=Depends(require_candidate),
) -> dict:
    segment_id = await request.app.state.controller.apply_transcript_status(
        interview_id,
        speaker=body.speaker,
        status=body.status,
        text=body.text,
        turn_id=body.turn_id,
    )
    return {"segment_id": segment_id}
