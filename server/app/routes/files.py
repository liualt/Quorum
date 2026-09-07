"""Candidate source snapshots: saving a file set and reading one back.

Every run and every piece of code evidence points at a snapshot id, so a save
is append-only: the candidate's earlier work is never overwritten.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app import ids
from app.routes.deps import require_candidate, require_participant, require_same_origin
from app.storage import repo
from app.storage.events import emit
from app.storage.snapshots import SnapshotError, content_hash, validate_files, write_snapshot

router = APIRouter(prefix="/api/interviews", tags=["files"])
mutations = APIRouter(
    prefix="/api/interviews", tags=["files"], dependencies=[Depends(require_same_origin)]
)

EDITABLE_STATUSES = ("created", "live")


class SaveFilesRequest(BaseModel):
    files: dict[str, str]


@mutations.put("/{interview_id}/files")
async def save_files(
    interview_id: str,
    body: SaveFilesRequest,
    request: Request,
    row=Depends(require_candidate),
) -> dict:
    app = request.app
    settings = app.state.settings

    if row["status"] not in EDITABLE_STATUSES:
        raise HTTPException(409, "this interview is no longer accepting code")

    try:
        validate_files(body.files, settings.SOURCE_LIMIT_BYTES)
    except SnapshotError as error:
        raise HTTPException(400, str(error)) from error

    snapshot_id = ids.new_id("snap")
    write_snapshot(settings.SNAPSHOT_DIR, interview_id, snapshot_id, body.files)
    saved = repo.insert_snapshot(
        app.state.db,
        id=snapshot_id,
        interview_id=interview_id,
        files_json=json.dumps(body.files),
        content_hash=content_hash(body.files),
        byte_size=sum(len(content.encode("utf-8")) for content in body.files.values()),
    )

    emit(
        app.state.db,
        app.state.bus,
        interview_id,
        "snapshot_saved",
        {
            "snapshot_id": saved["id"],
            "content_hash": saved["content_hash"],
            "files": sorted(body.files),
        },
    )
    return {
        "snapshot_id": saved["id"],
        "content_hash": saved["content_hash"],
        "created_at": saved["created_at"],
    }


@router.get("/{interview_id}/snapshots/{snapshot_id}")
async def get_snapshot(
    interview_id: str,
    snapshot_id: str,
    request: Request,
    participant=Depends(require_participant),
) -> dict:
    row = repo.get_snapshot(request.app.state.db, snapshot_id)
    if row is None or row["interview_id"] != interview_id:
        raise HTTPException(404, "snapshot not found")
    return {
        "id": row["id"],
        "files": repo.row_json(row, "files_json"),
        "content_hash": row["content_hash"],
        "byte_size": row["byte_size"],
        "created_at": row["created_at"],
    }
