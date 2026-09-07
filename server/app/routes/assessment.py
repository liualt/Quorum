"""Reading the assessment, and the candidate corrections attached to it."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.evidence import disputes
from app.evidence.disputes import DisputeError, dispute_view
from app.evidence.findings import assessment_view
from app.routes.deps import require_participant, require_reviewer, require_same_origin
from app.routes.turns import TURN_TEXT_LIMIT

router = APIRouter(prefix="/api/interviews", tags=["assessment"])
mutations = APIRouter(
    prefix="/api/interviews", tags=["assessment"], dependencies=[Depends(require_same_origin)]
)


class CreateDisputeRequest(BaseModel):
    segment_id: str
    proposed_text: str = Field(min_length=1, max_length=TURN_TEXT_LIMIT)
    reason: str = Field(default="", max_length=TURN_TEXT_LIMIT)


class ResolveDisputeRequest(BaseModel):
    resolution: str = Field(min_length=1, max_length=TURN_TEXT_LIMIT)


@router.get("/{interview_id}/assessment")
async def get_assessment(
    interview_id: str, request: Request, participant=Depends(require_participant)
) -> dict:
    _, me = participant
    view = assessment_view(request.app.state.db, interview_id, me)
    if view is None:
        raise HTTPException(404, "this interview has no assessment yet")
    return view


@mutations.post("/{interview_id}/disputes", status_code=201)
async def create_dispute(
    interview_id: str,
    body: CreateDisputeRequest,
    request: Request,
    participant=Depends(require_participant),
) -> dict:
    app = request.app
    try:
        row = disputes.create_dispute(
            app.state.db, app.state.bus, interview_id, body.segment_id, body.proposed_text, body.reason
        )
    except DisputeError as error:
        raise HTTPException(error.status_code, error.detail) from error
    return dispute_view(row)


@mutations.post("/{interview_id}/disputes/{dispute_id}/resolve")
async def resolve_dispute(
    interview_id: str,
    dispute_id: str,
    body: ResolveDisputeRequest,
    request: Request,
    row=Depends(require_reviewer),
) -> dict:
    app = request.app
    try:
        resolved = disputes.resolve_dispute(
            app.state.db, app.state.bus, interview_id, dispute_id, body.resolution
        )
    except DisputeError as error:
        raise HTTPException(error.status_code, error.detail) from error
    return dispute_view(resolved)
