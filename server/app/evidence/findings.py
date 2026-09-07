"""The assessment: the model's evidence-linked report, or the machine observations
when the report cannot be trusted.

`build_assessment` assembles the interview record, asks the model once, checks
the answer with `validate`, and asks once more with the errors spelled out when
the first answer fails (PRD section 9). An answer that still fails, or a model
that does not answer, produces a `pending` assessment whose findings are only
what the checks observed; nothing interpretive is invented in its place.
Whatever is stored records the rubric, prompt, and model versions it came from
(PRD section 10). `assessment_view` is the reviewer's and candidate's read of
the stored rows, with every referenced record alongside.
"""

import logging
from dataclasses import asdict

from app import ids
from app.evidence.claims import claim_view
from app.evidence.disputes import dispute_view
from app.evidence.links import link_view
from app.evidence.validate import validate_assessment_payload
from app.execution.runs import run_view
from app.interview.controller import segment_view
from app.interview.llm_client import LLMError
from app.interview.prompts import DIMENSIONS, PROMPT_VERSION, assessment_messages
from app.interview.state import ControllerState
from app.storage import repo
from app.storage.events import emit

logger = logging.getLogger(__name__)

PENDING_SUMMARY = (
    "Assessment pending: the model response could not be validated. "
    "Machine observations are shown."
)
NOT_ASSESSED_TEXT = "Not assessed: model response invalid"
RETRY_NOTE = "The previous response was rejected for these reasons; return a corrected assessment:"
# Where a check's observed outcome is filed when there is no report to file it under.
OBSERVATION_DIMENSION = "implementing_checking_fix"

ROLE_FOR_REFS = {"supporting_refs": "supports", "opposing_refs": "challenges"}
EVIDENCE_KEY = {"segment": "segments", "run": "runs", "claim": "claims", "snapshot": "snapshots"}


async def build_assessment(app, interview_id: str):
    """Store the interview's assessment, complete or pending, and return its row."""
    conn, bus, llm = app.state.db, app.state.bus, app.state.llm
    rubric = app.state.scenario.rubric
    messages = assessment_messages(rubric, assessment_record(app, interview_id))
    payload = await _validated_payload(app, interview_id, messages)

    versions = {
        "rubric_version": rubric.get("version"),
        "prompt_version": PROMPT_VERSION,
        "model_id": llm.model_id,
    }
    if payload is None:
        assessment = repo.insert_assessment(
            conn, id=ids.new_id("asm"), interview_id=interview_id, status="pending",
            summary=PENDING_SUMMARY, **versions,
        )
        entries = fallback_observations(app, interview_id)
    else:
        assessment = repo.insert_assessment(
            conn, id=ids.new_id("asm"), interview_id=interview_id, status="complete",
            summary=payload["summary"], **versions,
        )
        entries = _entries_from_payload(payload)
    _store_findings(conn, interview_id, assessment["id"], entries)

    repo.update_interview(conn, interview_id, model_id=llm.model_id)
    emit(
        conn, bus, interview_id, "assessment_completed",
        {"assessment_id": assessment["id"], "status": assessment["status"]},
    )
    return assessment


def assessment_record(app, interview_id: str) -> dict:
    """Everything the assessment prompt may cite; `prompts.bounded_record` trims it."""
    conn = app.state.db
    row = repo.get_interview(conn, interview_id)
    state = ControllerState.from_json(row["state_json"])
    return {
        "interview": {
            "id": row["id"],
            "display_name": row["display_name"],
            "status": row["status"],
            "stage": row["stage"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        },
        "state": asdict(state),
        "segments": [segment_view(s) for s in repo.list_segments(conn, interview_id)],
        "runs": [run_view(r) for r in repo.list_runs(conn, interview_id) if not r["replay_of"]],
        "claims": [claim_view(c) for c in repo.list_claims(conn, interview_id)],
        "links": [link_view(l) for l in repo.list_links(conn, interview_id)],
        "snapshots": [_snapshot_view(s) for s in repo.list_snapshots(conn, interview_id)],
        "hint_segment_ids": list(state.hints_given),
        "scenario_notice_segment_id": state.revocation_segment_id,
    }


async def _validated_payload(app, interview_id: str, messages: list[dict]) -> dict | None:
    """The model's assessment once it validates, after at most one retry; else None."""
    conn = app.state.db
    try:
        payload = await app.state.llm.complete_json(messages)
        errors = validate_assessment_payload(conn, interview_id, payload)
        if not errors:
            return payload
        logger.warning("assessment for %s rejected, retrying once: %s", interview_id, "; ".join(errors))
        payload = await app.state.llm.complete_json(_with_errors(messages, errors))
        errors = validate_assessment_payload(conn, interview_id, payload)
        if not errors:
            return payload
        logger.warning("assessment for %s rejected again: %s", interview_id, "; ".join(errors))
    except LLMError as error:
        logger.warning("assessment for %s: %s", interview_id, error)
    return None


def _with_errors(messages: list[dict], errors: list[str]) -> list[dict]:
    """The same request, with the rejection spelled out at the end of the user message."""
    retry = [dict(message) for message in messages]
    note = "\n".join([RETRY_NOTE, *(f"- {error}" for error in errors)])
    retry[-1]["content"] = f"{retry[-1]['content']}\n\n{note}"
    return retry


# --- what gets stored --------------------------------------------------------------------


def _entries_from_payload(payload: dict) -> list[dict]:
    """The validated payload as finding entries: dimensions in rubric order, then findings."""
    by_dimension = {entry["dimension"]: entry for entry in payload["dimensions"]}
    entries = [_entry(by_dimension[dimension], is_dimension=1) for dimension in DIMENSIONS]
    entries.extend(_entry(finding, is_dimension=0) for finding in payload["findings"])
    return entries


def _entry(source: dict, *, is_dimension: int) -> dict:
    return {
        "dimension": source["dimension"],
        "is_dimension": is_dimension,
        "title": source.get("title") or "",
        "observation_level": source["observation_level"],
        "explanation": source["explanation"],
        "assistance": source.get("assistance") or "",
        "uncertainty": source.get("uncertainty") or "",
        "follow_up": source.get("follow_up") or "",
        "refs": [
            (ref["type"], ref["id"], role)
            for field, role in ROLE_FOR_REFS.items()
            for ref in source.get(field) or []
        ],
    }


def fallback_observations(app, interview_id: str) -> list[dict]:
    """What can be said without a report: the four dimensions unassessed, and one
    observation per check in the candidate's latest completed run."""
    titles = {entry["id"]: entry.get("title", entry["id"]) for entry in app.state.scenario.rubric.get("dimensions", [])}
    entries = [
        {
            "dimension": dimension, "is_dimension": 1, "title": titles.get(dimension, dimension),
            "observation_level": "not_observed", "explanation": NOT_ASSESSED_TEXT,
            "assistance": "", "uncertainty": "", "follow_up": "", "refs": [],
        }
        for dimension in DIMENSIONS
    ]
    latest = _latest_completed_run(app.state.db, interview_id)
    if latest is None:
        return entries
    names = {check.id: check.name for check in app.state.scenario.checks}
    for result in repo.row_json(latest, "results_json") or []:
        name = names.get(result["check_id"], result["check_id"])
        passed = bool(result.get("passed"))
        entries.append(
            {
                "dimension": OBSERVATION_DIMENSION, "is_dimension": 0, "title": name,
                "observation_level": "demonstrated" if passed else "not_observed",
                "explanation": f"Run {latest['id']} {'passed' if passed else 'did not pass'} the {name} check.",
                "assistance": "", "uncertainty": "", "follow_up": "",
                "refs": [("run", latest["id"], "supports" if passed else "challenges")],
            }
        )
    return entries


def _latest_completed_run(conn, interview_id: str):
    """The candidate's newest completed run; a replay is the reviewer's, not theirs."""
    for row in reversed(repo.list_runs(conn, interview_id)):
        if row["status"] == "completed" and not row["replay_of"]:
            return row
    return None


def _store_findings(conn, interview_id: str, assessment_id: str, entries: list[dict]) -> None:
    positions = {1: 0, 0: 0}
    for entry in entries:
        is_dimension = entry["is_dimension"]
        row = repo.insert_finding(
            conn,
            id=ids.new_id("fnd"),
            interview_id=interview_id,
            assessment_id=assessment_id,
            dimension=entry["dimension"],
            is_dimension=is_dimension,
            title=entry["title"],
            observation_level=entry["observation_level"],
            explanation=entry["explanation"],
            assistance=entry["assistance"],
            uncertainty=entry["uncertainty"],
            follow_up=entry["follow_up"],
            position=positions[is_dimension],
        )
        positions[is_dimension] += 1
        for ref_type, ref_id, role in entry["refs"]:
            repo.insert_finding_ref(conn, finding_id=row["id"], ref_type=ref_type, ref_id=ref_id, role=role)


# --- the view ----------------------------------------------------------------------------


def assessment_view(conn, interview_id: str, me: str) -> dict | None:
    """The latest assessment with every record it cites; None when there is none yet."""
    assessment = repo.latest_assessment(conn, interview_id)
    if assessment is None:
        return None
    interview = repo.get_interview(conn, interview_id)
    findings = [finding_view(conn, row) for row in repo.list_findings(conn, assessment["id"])]
    links = [link_view(row) for row in repo.list_links(conn, interview_id)]
    return {
        "id": assessment["id"],
        "status": assessment["status"],
        "model_id": assessment["model_id"],
        "rubric_version": assessment["rubric_version"],
        "prompt_version": assessment["prompt_version"],
        "summary": assessment["summary"],
        "created_at": assessment["created_at"],
        "dimensions": [view for view in findings if view["is_dimension"]],
        "findings": [view for view in findings if not view["is_dimension"]],
        "evidence": _evidence(conn, interview_id, findings, links),
        "disputes": [dispute_view(row) for row in repo.list_disputes(conn, interview_id)],
        "me": me,
        "interview": {
            "id": interview["id"],
            "display_name": interview["display_name"],
            "finished_at": interview["finished_at"],
        },
    }


def finding_view(conn, row) -> dict:
    refs = repo.list_finding_refs(conn, row["id"])
    return {
        "id": row["id"],
        "dimension": row["dimension"],
        "is_dimension": bool(row["is_dimension"]),
        "title": row["title"],
        "observation_level": row["observation_level"],
        "explanation": row["explanation"],
        "supporting_refs": [_ref(ref) for ref in refs if ref["role"] == "supports"],
        "opposing_refs": [_ref(ref) for ref in refs if ref["role"] == "challenges"],
        "assistance": row["assistance"],
        "uncertainty": row["uncertainty"],
        "follow_up": row["follow_up"],
        "review_status": row["review_status"],
        "review_reasons": repo.row_json(row, "review_reasons_json") or [],
        "has_run_ref": any(ref["ref_type"] == "run" for ref in refs),
    }


def _ref(row) -> dict:
    return {"type": row["ref_type"], "id": row["ref_id"]}


def _evidence(conn, interview_id: str, findings: list[dict], links: list[dict]) -> dict:
    """Every record a finding or a link points at, plus the replays of any run cited,
    so a reviewer can compare a replay with the original beside the finding."""
    wanted = {
        (ref["type"], ref["id"])
        for finding in findings
        for ref in finding["supporting_refs"] + finding["opposing_refs"]
    }
    for link in links:
        wanted.add((link["source_type"], link["source_id"]))
        wanted.add((link["target_type"], link["target_id"]))
    cited_runs = {ref_id for ref_type, ref_id in wanted if ref_type == "run"}
    for run in repo.list_runs(conn, interview_id):
        if run["replay_of"] in cited_runs:
            wanted.add(("run", run["id"]))

    evidence = {key: {} for key in EVIDENCE_KEY.values()}
    evidence["links"] = links
    for ref_type, ref_id in sorted(wanted):
        view = _record_view(conn, interview_id, ref_type, ref_id)
        if view is not None:
            evidence[EVIDENCE_KEY[ref_type]][ref_id] = view
    return evidence


def _record_view(conn, interview_id: str, ref_type: str, ref_id: str) -> dict | None:
    if ref_type == "segment":
        row, view = repo.get_segment(conn, ref_id), segment_view
    elif ref_type == "run":
        row, view = repo.get_run(conn, ref_id), run_view
    elif ref_type == "claim":
        row, view = repo.get_claim(conn, ref_id), claim_view
    else:
        row, view = repo.get_snapshot(conn, ref_id), _snapshot_view
    if row is None or row["interview_id"] != interview_id:
        return None
    return view(row)


def _snapshot_view(row) -> dict:
    return {"id": row["id"], "content_hash": row["content_hash"], "created_at": row["created_at"]}
