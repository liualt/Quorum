"""Evidence links: validated rows between records, never free-form model output.

A run speaks to the claims its checks test: `SCOPE_TO_CHECK` says which check
covers which claim scope, and a run supports the claims of a scope whose check
passed and challenges those whose check failed. A hint or scenario notice
challenges the claims the candidate made in answer to it. Revision links are
written by `claims`, from the model's own `revises_claim_id`, once the id has
been checked against this interview's claims.
"""

from app import ids
from app.storage import repo

SCOPE_TO_CHECK = {
    "cross_company": "cross_company_isolation",
    "revocation": "revocation_next_request",
    "efficiency": "repeat_search_efficiency",
    "access": "access_filtering",
}
CHECK_TO_SCOPE = {check_id: scope for scope, check_id in SCOPE_TO_CHECK.items()}

# A run bears on what the candidate said was wrong, what they changed, and
# whether it should ship. It says nothing about a plan, a question, or a doubt.
LINKED_CLAIM_TYPES = frozenset({"diagnosis", "fix_description", "release_decision"})

LINK_VIEW_COLUMNS = ("id", "source_type", "source_id", "target_type", "target_id", "relation")


def link_view(row) -> dict:
    return {column: row[column] for column in LINK_VIEW_COLUMNS}


def link_run_to_claims(conn, interview_id: str, run_row) -> list:
    """Link a completed run to the claims made before it that its checks bear on.

    A claim counts as made before the run when its source segment was recorded
    no later than the run was requested: the claim row itself is written after a
    model call and may postdate a run the candidate started as they spoke.
    """
    results = repo.row_json(run_row, "results_json") or []
    if not results:
        return []
    spoken_at = {row["id"]: row["created_at"] for row in repo.list_segments(conn, interview_id)}
    claims = [
        claim
        for claim in repo.list_claims(conn, interview_id)
        if claim["claim_type"] in LINKED_CLAIM_TYPES
        and claim["segment_id"] in spoken_at
        and spoken_at[claim["segment_id"]] <= run_row["created_at"]
    ]
    linked = _linked_targets(conn, interview_id, "run", run_row["id"])
    inserted = []
    for result in results:
        scope = CHECK_TO_SCOPE.get(result.get("check_id"))
        if scope is None:
            continue
        relation = "supports" if result.get("passed") else "challenges"
        for claim in claims:
            if claim["scope"] != scope or claim["id"] in linked:
                continue
            inserted.append(_insert(conn, interview_id, "run", run_row["id"], claim["id"], relation))
            linked.add(claim["id"])
    return inserted


def link_challenge(conn, interview_id: str, role_segment_id: str, scopes: list[str]) -> list:
    """Link a hint or scenario notice to the claims of `scopes` in the candidate's answer to it.

    The answer is the first candidate segment after the role segment; claims
    from any later turn are the candidate's own development, not a response.
    """
    role = repo.get_segment(conn, role_segment_id)
    if role is None or role["interview_id"] != interview_id:
        return []
    answer = next(
        (
            row
            for row in repo.list_segments(conn, interview_id)
            if row["seq"] > role["seq"] and row["speaker"] == "candidate"
        ),
        None,
    )
    if answer is None:
        return []
    linked = _linked_targets(conn, interview_id, "segment", role_segment_id)
    inserted = []
    for claim in repo.list_claims(conn, interview_id):
        if claim["segment_id"] != answer["id"] or claim["scope"] not in scopes or claim["id"] in linked:
            continue
        inserted.append(_insert(conn, interview_id, "segment", role_segment_id, claim["id"], "challenges"))
        linked.add(claim["id"])
    return inserted


def _linked_targets(conn, interview_id: str, source_type: str, source_id: str) -> set[str]:
    return {
        row["target_id"]
        for row in repo.list_links(conn, interview_id)
        if row["source_type"] == source_type and row["source_id"] == source_id
    }


def _insert(conn, interview_id: str, source_type: str, source_id: str, claim_id: str, relation: str):
    return repo.insert_link(
        conn,
        id=ids.new_id("lnk"),
        interview_id=interview_id,
        source_type=source_type,
        source_id=source_id,
        target_type="claim",
        target_id=claim_id,
        relation=relation,
    )
