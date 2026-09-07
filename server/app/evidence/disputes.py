"""Candidate corrections, and the review state they and differing replays put findings in.

A correction never rewrites the record: the original text stays on the segment,
the proposed text goes on the dispute, and every finding that leans on the
segment — directly, or through a claim read from it — is marked as needing
review until a reviewer resolves the dispute (PRD sections 5 and 12). A
correction may be filed before there is an assessment; `apply_open_disputes`
puts the findings under its hold once they exist. A replay whose results differ
marks the findings that cite the original run the same way, under its own
reason, and both results are kept.
"""

import json

from app import ids
from app.storage import repo
from app.storage.events import emit


class DisputeError(Exception):
    """A refused dispute action, carrying the HTTP status the route should return."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail

DISPUTE_VIEW_COLUMNS = (
    "id", "segment_id", "original_text", "proposed_text", "reason", "status", "resolution",
    "created_at", "resolved_at",
)


def dispute_view(row) -> dict:
    view = {column: row[column] for column in DISPUTE_VIEW_COLUMNS}
    view["affected_finding_ids"] = repo.row_json(row, "affected_finding_ids_json") or []
    return view


def dispute_reason(dispute_id: str) -> str:
    return f"dispute:{dispute_id}"


def create_dispute(conn, bus, interview_id: str, segment_id: str, proposed_text: str, reason: str):
    """Attach a correction to a segment and mark what depends on it."""
    segment = repo.get_segment(conn, segment_id)
    if segment is None or segment["interview_id"] != interview_id:
        raise DisputeError(404, "segment not found")

    row = repo.insert_dispute(
        conn,
        id=ids.new_id("dsp"),
        interview_id=interview_id,
        segment_id=segment_id,
        original_text=segment["text"],
        proposed_text=proposed_text,
        reason=reason,
        affected_finding_ids_json="[]",
    )
    row = _hold_dependents(conn, bus, row)
    emit(conn, bus, interview_id, "dispute_updated", {"dispute": dispute_view(row)})
    return row


def apply_open_disputes(conn, bus, interview_id: str) -> None:
    """Put a fresh assessment's findings under every open dispute's hold.

    Called once the findings exist; a dispute filed during the interview had
    nothing to mark at the time. A dispute whose affected set changes is
    announced again.
    """
    for dispute in repo.list_disputes(conn, interview_id):
        if dispute["status"] != "open":
            continue
        before = repo.row_json(dispute, "affected_finding_ids_json") or []
        row = _hold_dependents(conn, bus, dispute)
        if (repo.row_json(row, "affected_finding_ids_json") or []) != before:
            emit(conn, bus, interview_id, "dispute_updated", {"dispute": dispute_view(row)})


def _hold_dependents(conn, bus, dispute):
    """Mark every finding that leans on the disputed segment, directly or through a
    claim read from it, and record them on the dispute."""
    interview_id, segment_id = dispute["interview_id"], dispute["segment_id"]
    review_reason = dispute_reason(dispute["id"])
    affected = mark_findings_needing_review(conn, bus, interview_id, "segment", segment_id, review_reason)
    for claim in repo.list_claims(conn, interview_id):
        if claim["segment_id"] != segment_id:
            continue
        for finding_id in mark_findings_needing_review(conn, bus, interview_id, "claim", claim["id"], review_reason):
            if finding_id not in affected:
                affected.append(finding_id)
    return repo.update_dispute(conn, dispute["id"], affected_finding_ids_json=json.dumps(affected))


def resolve_dispute(conn, bus, interview_id: str, dispute_id: str, resolution: str):
    """Record a reviewer's resolution and lift this dispute's hold on its findings."""
    dispute = repo.get_dispute(conn, dispute_id)
    if dispute is None or dispute["interview_id"] != interview_id:
        raise DisputeError(404, "dispute not found")
    if dispute["status"] == "resolved":
        raise DisputeError(409, "this dispute is already resolved")
    row = repo.update_dispute(
        conn, dispute_id, status="resolved", resolution=resolution, resolved_at=ids.now_iso()
    )
    clear_review_reason(conn, bus, interview_id, dispute_reason(dispute_id))
    emit(conn, bus, interview_id, "dispute_updated", {"dispute": dispute_view(row)})
    return row


def mark_findings_needing_review(conn, bus, interview_id: str, ref_type: str, ref_id: str, reason: str) -> list[str]:
    """Put every finding of the latest assessment that cites the record under review.

    Returns the ids of the findings that cite it. Emits nothing: a dispute emits
    its own update, and a differing replay is already announced by its run.
    """
    marked = []
    for finding in repo.findings_referencing(conn, interview_id, ref_type, ref_id):
        reasons = repo.row_json(finding, "review_reasons_json") or []
        if reason not in reasons:
            reasons.append(reason)
        repo.update_finding(
            conn, finding["id"], review_status="needs_review", review_reasons_json=json.dumps(reasons)
        )
        marked.append(finding["id"])
    return marked


def clear_review_reason(conn, bus, interview_id: str, reason: str) -> None:
    """Remove one reason from every finding; a finding with none left is `ok` again."""
    assessment = repo.latest_assessment(conn, interview_id)
    if assessment is None:
        return
    for finding in repo.list_findings(conn, assessment["id"]):
        reasons = repo.row_json(finding, "review_reasons_json") or []
        if reason not in reasons:
            continue
        remaining = [item for item in reasons if item != reason]
        repo.update_finding(
            conn,
            finding["id"],
            review_status="needs_review" if remaining else "ok",
            review_reasons_json=json.dumps(remaining),
        )
