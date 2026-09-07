"""Claims: what the model read into one candidate segment, stored as interpretations.

The model is asked once per candidate segment, after the panel has replied, and
its answer is checked before anything is written: a claim outside the vocabulary
is dropped, a revision pointing at a claim that is not this interview's loses
the pointer but keeps the statement, and never more than six claims are kept.
The controller's own bookkeeping (`covered`, `last_clarity`, `contradiction_note`)
is updated from the same answer under the interview's lock, read fresh after
the model call, so a turn recorded while the model was thinking is never
overwritten. Nothing here raises: a model that fails leaves no record at all.
"""

import logging

from app import ids
from app.evidence.links import link_challenge, link_run_to_claims
from app.execution.runs import run_view
from app.interview.controller import segment_view
from app.interview.llm_client import LLMError
from app.interview.prompts import claims_messages
from app.storage import repo

logger = logging.getLogger(__name__)

RECENT_SEGMENTS = 6
RECENT_RUNS = 3
MAX_CLAIMS = 6

CLAIM_TYPES = frozenset(
    {"diagnosis", "release_decision", "fix_description", "test_plan", "uncertainty", "question", "other"}
)
SCOPES = frozenset({"cross_company", "revocation", "efficiency", "access", "general"})
CLARITIES = frozenset({"clear", "vague"})
# The role turns that put something to the candidate, and so challenge the answer.
CHALLENGE_KINDS = ("hint", "scenario_notice")

CLAIM_VIEW_COLUMNS = (
    "id", "segment_id", "statement", "claim_type", "scope", "stage", "clarity",
    "interpretation_status", "created_at",
)


def claim_view(row) -> dict:
    return {column: row[column] for column in CLAIM_VIEW_COLUMNS}


async def extract_and_store_claims(app, interview_id: str, segment_id: str) -> list:
    """Read one candidate segment into claim rows; returns the rows stored."""
    conn = app.state.db
    segment = repo.get_segment(conn, segment_id)
    if segment is None or segment["interview_id"] != interview_id:
        return []
    prior = repo.list_claims(conn, interview_id)
    messages = claims_messages(
        segment_view(segment),
        _segments_before(conn, interview_id, segment),
        [_prior_claim(row) for row in prior],
        _recent_runs(conn, interview_id),
    )

    try:
        payload = await app.state.llm.complete_json(messages)
    except LLMError as error:
        logger.warning("claims for %s: %s", segment_id, error)
        return []
    accepted = _accepted_claims(payload, {row["id"] for row in prior}, segment_id)
    if accepted is None:
        return []

    controller = app.state.controller
    # Read, change, and write the state without an await in between: a turn
    # that landed during the model call is already in the row being read.
    async with controller.interview_lock(interview_id):
        stored = _store(conn, interview_id, segment, accepted)
        state = controller.load_state(interview_id)
        _apply_to_state(state, payload, stored)
        controller.save_state(interview_id, state)

    if stored:
        challenger = _challenger(conn, interview_id, segment)
        if challenger is not None:
            link_challenge(conn, interview_id, challenger["id"], sorted({row["scope"] for row in stored}))
        # A run the candidate started right after speaking may have landed before
        # the model answered; its own completion hook ran before these claims existed.
        for run in _runs_since(conn, interview_id, segment):
            link_run_to_claims(conn, interview_id, run)
    return stored


# --- the prompt's inputs --------------------------------------------------------------


def _segments_before(conn, interview_id: str, segment) -> list[dict]:
    rows = [row for row in repo.list_segments(conn, interview_id) if row["seq"] < segment["seq"]]
    return [segment_view(row) for row in rows[-RECENT_SEGMENTS:]]


def _recent_runs(conn, interview_id: str) -> list[dict]:
    rows = [row for row in repo.list_runs(conn, interview_id) if not row["replay_of"]]
    return [run_view(row) for row in rows[-RECENT_RUNS:]]


def _runs_since(conn, interview_id: str, segment) -> list:
    """The candidate's completed runs requested no earlier than the segment was spoken."""
    return [
        row
        for row in repo.list_runs(conn, interview_id)
        if row["status"] == "completed"
        and not row["replay_of"]
        and row["created_at"] >= segment["created_at"]
    ]


def _prior_claim(row) -> dict:
    return {
        "id": row["id"],
        "statement": row["statement"],
        "scope": row["scope"],
        "claim_type": row["claim_type"],
    }


# --- the model's answer -----------------------------------------------------------------


def _accepted_claims(payload, prior_ids: set[str], segment_id: str) -> list[dict] | None:
    """The claims worth storing, or None when the answer is not even the right shape."""
    if not isinstance(payload, dict) or not isinstance(payload.get("claims"), list):
        logger.warning("claims for %s: the model's answer had the wrong shape", segment_id)
        return None
    accepted = []
    for item in payload["claims"]:
        if not _well_formed(item):
            continue
        revises = item.get("revises_claim_id")
        accepted.append(
            {
                "statement": item["statement"].strip(),
                "claim_type": item["claim_type"],
                "scope": item["scope"],
                "clarity": item["clarity"],
                # A pointer to a claim this interview never made is an invention.
                "revises_claim_id": revises if revises in prior_ids else None,
            }
        )
    dropped = len(payload["claims"]) - len(accepted)
    if dropped:
        logger.warning("claims for %s: dropped %d malformed claim(s)", segment_id, dropped)
    return accepted[:MAX_CLAIMS]


def _well_formed(item) -> bool:
    return (
        isinstance(item, dict)
        and isinstance(item.get("statement"), str)
        and bool(item["statement"].strip())
        and item.get("claim_type") in CLAIM_TYPES
        and item.get("scope") in SCOPES
        and item.get("clarity") in CLARITIES
    )


def _store(conn, interview_id: str, segment, accepted: list[dict]) -> list:
    stored = []
    for item in accepted:
        row = repo.insert_claim(
            conn,
            id=ids.new_id("clm"),
            interview_id=interview_id,
            segment_id=segment["id"],
            statement=item["statement"],
            claim_type=item["claim_type"],
            scope=item["scope"],
            stage=segment["stage"],
            clarity=item["clarity"],
        )
        if item["revises_claim_id"]:
            repo.insert_link(
                conn,
                id=ids.new_id("lnk"),
                interview_id=interview_id,
                source_type="claim",
                source_id=row["id"],
                target_type="claim",
                target_id=item["revises_claim_id"],
                relation="revises",
            )
        stored.append(row)
    return stored


def _apply_to_state(state, payload: dict, stored: list) -> None:
    """What the answer tells the controller. Coverage is only ever gained."""
    covered = payload.get("covered")
    if isinstance(covered, dict):
        for key in state.covered:
            if covered.get(key) is True:
                state.covered[key] = True
    state.last_clarity = "vague" if any(row["clarity"] == "vague" for row in stored) else "clear"
    note = payload.get("contradiction_note")
    if isinstance(note, str) and note.strip():
        state.contradiction_note = note.strip()


def _challenger(conn, interview_id: str, segment):
    """The hint or scenario notice this segment answers: the latest one since the
    candidate last spoke, and only one the candidate heard in full."""
    earlier = [row for row in repo.list_segments(conn, interview_id) if row["seq"] < segment["seq"]]
    for row in reversed(earlier):
        if row["speaker"] == "candidate":
            return None
        if row["kind"] in CHALLENGE_KINDS and row["status"] == "complete":
            return row
    return None
