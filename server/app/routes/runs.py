"""Starting and reading test runs. Every rule about them lives in app.execution.runs."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.execution import runs as run_service
from app.execution.runs import RunError, run_view
from app.routes.deps import require_candidate, require_participant, require_same_origin
from app.storage import repo

router = APIRouter(prefix="/api/interviews", tags=["runs"])
mutations = APIRouter(
    prefix="/api/interviews", tags=["runs"], dependencies=[Depends(require_same_origin)]
)


class StartRunRequest(BaseModel):
    snapshot_id: str
    check_ids: list[str]
    idempotency_key: str | None = None


@mutations.post("/{interview_id}/runs", status_code=202)
async def start_run(
    interview_id: str,
    body: StartRunRequest,
    request: Request,
    row=Depends(require_candidate),
) -> dict:
    try:
        created = await run_service.start_run(
            request.app, interview_id, body.snapshot_id, body.check_ids, body.idempotency_key
        )
    except RunError as error:
        raise HTTPException(error.status_code, error.detail) from error
    return run_view(created)


@router.get("/{interview_id}/runs")
async def list_runs(
    interview_id: str, request: Request, participant=Depends(require_participant)
) -> list[dict]:
    return [run_view(row) for row in repo.list_runs(request.app.state.db, interview_id)]


@router.get("/{interview_id}/runs/{run_id}")
async def get_run(
    interview_id: str,
    run_id: str,
    request: Request,
    participant=Depends(require_participant),
) -> dict:
    row = repo.get_run(request.app.state.db, run_id)
    if row is None or row["interview_id"] != interview_id:
        raise HTTPException(404, "run not found")
    return run_view(row)
