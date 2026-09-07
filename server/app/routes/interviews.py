"""Interview lifecycle: create, read, start, pause, finish, delete."""

import logging
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app import ids
from app.execution import runs as run_service
from app.interview import prompts
from app.interview.controller import segment_view
from app.interview.state import ControllerState
from app.routes.deps import (
    COOKIE_CANDIDATE,
    hash_token,
    llm_token,
    new_token,
    require_candidate,
    require_participant,
    require_same_origin,
    set_capability_cookie,
)
from app.scenario import public_check
from app.storage import repo, snapshots
from app.storage.events import emit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/interviews", tags=["interviews"])
mutations = APIRouter(
    prefix="/api/interviews", tags=["interviews"], dependencies=[Depends(require_same_origin)]
)

#: Everything `/start` records about the conversation the agent joins.
AGORA_COLUMNS = ("agora_channel", "agora_agent_id", "agora_uid", "agora_agent_uid")


def initial_state_json() -> str:
    """The controller state a new interview starts from."""
    return ControllerState().to_json()


async def delete_interview(app, interview_id: str) -> None:
    """Remove every trace of an interview: its agent, its rows, its snapshots.

    Task 8 relocates this to `app/cleanup.py`, where expiry reuses it.
    """
    row = repo.get_interview(app.state.db, interview_id)
    voice = getattr(app.state, "voice", None)
    if row is not None and row["agora_agent_id"] and voice is not None:
        # Before the rows go, while the agent id is still readable. `stop_agent`
        # never raises, so a deletion is never blocked by Agora.
        await voice.stop_agent(row["agora_agent_id"])
    repo.delete_interview_rows(app.state.db, interview_id)
    snapshots.delete_interview_dir(app.state.settings.SNAPSHOT_DIR, interview_id)


class CreateInterviewRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    consent: Literal[True]


class SetPausedRequest(BaseModel):
    paused: bool


@mutations.post("", status_code=201)
async def create_interview(
    body: CreateInterviewRequest, request: Request, response: Response
) -> dict:
    app = request.app
    settings = app.state.settings
    scenario = app.state.scenario

    interview_id = ids.new_id("itv")
    repo.create_interview(
        app.state.db,
        id=interview_id,
        display_name=body.display_name.strip(),
        scenario_id=scenario.id,
        scenario_version=scenario.version,
        consent_at=ids.now_iso(),
        expires_at=_expiry(settings.RETENTION_DAYS),
        state_json=initial_state_json(),
        stage="briefing",
        active_role="technical",
    )

    tokens = {kind: new_token() for kind in ("candidate", "reviewer")}
    for kind, token in tokens.items():
        repo.create_capability(
            app.state.db,
            id=ids.new_id("cap"),
            interview_id=interview_id,
            kind=kind,
            token_hash=hash_token(settings, token),
        )

    set_capability_cookie(response, COOKIE_CANDIDATE, tokens["candidate"], settings)
    return {
        "id": interview_id,
        "candidate_path": f"/interview/{interview_id}",
        # Shown once, and never stored in a form anyone can read back.
        "reviewer_token": tokens["reviewer"],
        "reviewer_path": f"/review/{tokens['reviewer']}",
    }


@router.get("/{interview_id}")
async def get_interview(request: Request, participant=Depends(require_participant)) -> dict:
    row, me = participant
    return interview_view(request.app, row, me)


@mutations.post("/{interview_id}/start")
async def start_interview(
    interview_id: str, request: Request, row=Depends(require_candidate)
) -> dict:
    app = request.app
    # A double click, or a reload landing while the first start is still in
    # flight, must not put two agents in one channel or two greetings in the
    # transcript. Whether an agent already exists is read and acted on here.
    async with app.state.controller.interview_lock(interview_id):
        # The row the dependency read can predate a start that just finished.
        current = repo.get_interview(app.state.db, interview_id) or row
        greeting = prompts.greeting_text(current["display_name"])
        join, voice_status, agora = await _join_voice(app, interview_id, current, greeting)

        repo.update_interview(
            app.state.db,
            interview_id,
            status="live",
            # A second start must not restart the clock the session cap runs on.
            started_at=current["started_at"] or ids.now_iso(),
            voice_status=voice_status,
            **agora,
        )
        _ensure_greeting(app, interview_id, greeting)
        emit(app.state.db, app.state.bus, interview_id, "voice_status", {"status": voice_status})
        return {"voice": join}


async def _join_voice(app, interview_id: str, row, greeting: str) -> tuple[dict, str, dict]:
    """Put an agent in the interview's channel, and say what to record about it.

    Voice is the medium, not the interview: every failure here — a malformed
    Agora credential, an agent Agora will not start — degrades to text mode
    instead of refusing to begin.
    """
    voice = getattr(app.state, "voice", None)
    if voice is None or not voice.enabled:
        return {"enabled": False}, "off", {}

    try:
        if row["agora_agent_id"]:
            # A reload rejoins the conversation in progress rather than
            # replacing it: same channel, same identities, a fresh token, and
            # the agent keeps the history it already has.
            join = voice.make_join(
                interview_id,
                uid=row["agora_uid"],
                agent_uid=row["agora_agent_uid"],
                agent_id=row["agora_agent_id"],
            )
        else:
            join = voice.make_join(interview_id)
            join.agent_id = await voice.start_agent(
                join,
                llm_url=_llm_url(app.state.settings, interview_id),
                llm_token=llm_token(app.state.settings, interview_id),
                greeting=greeting,
                instructions=prompts.agent_instructions(),
            )
    except Exception as failure:
        # Never the message: a pydantic ValidationError quotes the input it
        # rejected, and the input here carries the agent's bearer token.
        logger.error(
            "voice is unavailable for %s: %s", interview_id, type(failure).__name__
        )
        logger.debug("voice failed to start for %s", interview_id, exc_info=failure)
        # A start that failed left nothing behind. A rejoin that failed left the
        # agent it could not rejoin, and `/finish` still has to stop that one.
        cleared = {} if row["agora_agent_id"] else dict.fromkeys(AGORA_COLUMNS)
        return (
            {"enabled": False, "reason": "the voice agent could not be reached"},
            "disconnected",
            cleared,
        )

    return (
        asdict(join),
        "connecting",
        {
            "agora_channel": join.channel,
            "agora_agent_id": join.agent_id,
            "agora_uid": join.uid,
            "agora_agent_uid": join.agent_uid,
        },
    )


def _llm_url(settings, interview_id: str) -> str:
    """Where the voice agent reaches this backend for every candidate turn."""
    return f"{settings.CUSTOM_LLM_PUBLIC_BASE_URL}/llm/{interview_id}/chat/completions"


def _ensure_greeting(app, interview_id: str, greeting: str) -> None:
    """Open the transcript with the disclosure, spoken or not, exactly once.

    With voice, Agora says this line from its own greeting configuration rather
    than asking the model endpoint for it; the segment is the written record of
    the same words. A second `/start` must not repeat either.
    """
    existing = repo.list_segments(app.state.db, interview_id)
    if any(segment["kind"] == "greeting" for segment in existing):
        return
    row = repo.insert_segment(
        app.state.db,
        id=ids.new_id("seg"),
        interview_id=interview_id,
        speaker="technical",
        kind="greeting",
        text=greeting,
        stage="briefing",
        generation=0,
        status="complete",
    )
    emit(
        app.state.db,
        app.state.bus,
        interview_id,
        "transcript_segment",
        {"segment": segment_view(row)},
    )


@mutations.post("/{interview_id}/pause")
async def set_paused(
    interview_id: str,
    body: SetPausedRequest,
    request: Request,
    row=Depends(require_candidate),
) -> dict:
    app = request.app
    if body.paused == bool(row["paused"]):
        return {"paused": body.paused}

    fields = {
        "paused": int(body.paused),
        "paused_at": ids.now_iso() if body.paused else None,
    }
    if not body.paused:
        # Paused time is excluded from the session cap, so it is banked here.
        fields["paused_ms"] = (row["paused_ms"] or 0) + _elapsed_ms(row["paused_at"])

    repo.update_interview(app.state.db, interview_id, **fields)
    emit(app.state.db, app.state.bus, interview_id, "pause_changed", {"paused": body.paused})
    return {"paused": body.paused}


@mutations.post("/{interview_id}/finish")
async def finish_interview(row=Depends(require_candidate)) -> dict:
    raise HTTPException(501, "finish is implemented in a later task")


@mutations.delete("/{interview_id}", status_code=204, response_class=Response)
async def delete_interview_route(
    interview_id: str, request: Request, participant=Depends(require_participant)
) -> Response:
    await delete_interview(request.app, interview_id)
    return Response(status_code=204)


def interview_view(app, row, me: str) -> dict:
    settings = app.state.settings
    scenario = app.state.scenario
    available = set(run_service.allowed_check_ids(app, row["id"]))
    latest = repo.latest_snapshot(app.state.db, row["id"])
    voice = getattr(app.state, "voice", None)

    return {
        "id": row["id"],
        "display_name": row["display_name"],
        "status": row["status"],
        "stage": row["stage"],
        "active_role": row["active_role"],
        "paused": bool(row["paused"]),
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "me": me,
        "model_id": row["model_id"],
        "voice_enabled": voice.enabled if voice is not None else settings.voice_configured,
        "voice_status": row["voice_status"] or "off",
        "scenario": {
            "id": scenario.id,
            "version": scenario.version,
            "brief": scenario.brief,
            "editable_files": scenario.editable_files,
            "readonly_files": scenario.readonly_files,
            "checks": [public_check(check, check.id in available) for check in scenario.checks],
        },
        "latest_snapshot_id": latest["id"] if latest is not None else None,
        "runs_used": repo.count_runs(app.state.db, row["id"]),
        "run_limit": settings.MAX_RUNS_PER_INTERVIEW,
        "session_cap_minutes": settings.SESSION_CAP_MINUTES,
    }


def _expiry(days: int) -> str:
    moment = datetime.now(UTC) + timedelta(days=days)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _elapsed_ms(since: str | None) -> int:
    if not since:
        return 0
    delta = datetime.now(UTC) - datetime.fromisoformat(since)
    return max(0, int(delta.total_seconds() * 1000))
