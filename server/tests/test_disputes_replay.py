"""Candidate corrections and reviewer replays: both change a finding's review
state and neither touches the record it was made from."""

import json

import pytest

from app import ids
from app.evidence.disputes import (
    clear_review_reason,
    create_dispute,
    mark_findings_needing_review,
    resolve_dispute,
)
from app.execution import runs as runs_module
from app.storage import repo
from tests.conftest import (
    INITIAL_CHECK,
    ORIGIN,
    become_reviewer,
    completed_run,
    create_interview,
    event_types,
    run_full_interview,
    seed_interview,
    wait_for_run,
)


def finding_state(conn, finding_id):
    row = repo.get_finding(conn, finding_id)
    return row["review_status"], repo.row_json(row, "review_reasons_json")


@pytest.fixture
def evidence(live_app):
    """An assessed interview: a segment, a claim from it, a run, and findings on each."""
    interview = seed_interview(live_app)
    conn = live_app.state.db
    iid = interview["id"]

    def segment(text):
        return repo.insert_segment(
            conn, id=ids.new_id("seg"), interview_id=iid, speaker="candidate", kind="turn",
            text=text, stage="investigation", generation=1, status="complete",
        )

    disputed = segment("The cache is per company already.")
    other = segment("Something else entirely.")
    claim = repo.insert_claim(
        conn, id=ids.new_id("clm"), interview_id=iid, segment_id=disputed["id"],
        statement=disputed["text"], claim_type="diagnosis", scope="cross_company",
        stage="investigation", clarity="clear",
    )
    run = completed_run(live_app, iid, [INITIAL_CHECK], {INITIAL_CHECK: True})
    assessment = repo.insert_assessment(
        conn, id=ids.new_id("asm"), interview_id=iid, status="complete", rubric_version="v1",
        prompt_version="v1", model_id="scripted-test-double", summary="A summary.",
    )

    def finding(position, ref_type, ref_id, *, is_dimension=1, role="supports"):
        row = repo.insert_finding(
            conn, id=ids.new_id("fnd"), interview_id=iid, assessment_id=assessment["id"],
            dimension="understanding_problem", is_dimension=is_dimension, title=f"Finding {position}",
            observation_level="demonstrated", explanation="An explanation long enough to pass.",
            assistance="", uncertainty="", follow_up="", position=position,
        )
        repo.insert_finding_ref(conn, finding_id=row["id"], ref_type=ref_type, ref_id=ref_id, role=role)
        return row

    return {
        "interview": interview,
        "segment": disputed,
        "other_segment": other,
        "claim": claim,
        "run": run,
        "on_segment": finding(0, "segment", disputed["id"]),
        "on_claim": finding(1, "claim", claim["id"], role="challenges"),
        "on_run": finding(0, "run", run["id"], is_dimension=0),
        "on_other": finding(1, "segment", other["id"], is_dimension=0),
    }


# --- disputes, at the service level ----------------------------------------------


async def test_a_dispute_marks_the_findings_that_lean_on_the_segment(live_app, evidence):
    conn, bus = live_app.state.db, live_app.state.bus
    iid = evidence["interview"]["id"]

    dispute = create_dispute(
        conn, bus, iid, evidence["segment"]["id"], "The cache is per query only.", "Misheard."
    )

    assert dispute["id"].startswith("dsp_")
    assert dispute["status"] == "open"
    assert dispute["original_text"] == "The cache is per company already."
    assert dispute["proposed_text"] == "The cache is per query only."
    assert dispute["reason"] == "Misheard."
    assert dispute["resolution"] is None and dispute["resolved_at"] is None
    assert repo.row_json(dispute, "affected_finding_ids_json") == [
        evidence["on_segment"]["id"], evidence["on_claim"]["id"]
    ]
    reason = f"dispute:{dispute['id']}"
    assert finding_state(conn, evidence["on_segment"]["id"]) == ("needs_review", [reason])
    assert finding_state(conn, evidence["on_claim"]["id"]) == ("needs_review", [reason])
    assert finding_state(conn, evidence["on_run"]["id"]) == ("ok", [])
    assert finding_state(conn, evidence["on_other"]["id"]) == ("ok", [])
    # The record is never rewritten by a correction.
    assert repo.get_segment(conn, evidence["segment"]["id"])["text"] == "The cache is per company already."

    events = repo.list_events(conn, iid, 0)
    assert [event["type"] for event in events] == ["dispute_updated"]
    view = events[0]["payload"]["dispute"]
    assert view["id"] == dispute["id"]
    assert view["affected_finding_ids"] == [evidence["on_segment"]["id"], evidence["on_claim"]["id"]]
    assert view["status"] == "open"


async def test_a_second_dispute_adds_its_own_reason(live_app, evidence):
    conn, bus = live_app.state.db, live_app.state.bus
    iid = evidence["interview"]["id"]

    first = create_dispute(conn, bus, iid, evidence["segment"]["id"], "One.", "")
    second = create_dispute(conn, bus, iid, evidence["segment"]["id"], "Two.", "")

    assert finding_state(conn, evidence["on_segment"]["id"]) == (
        "needs_review", [f"dispute:{first['id']}", f"dispute:{second['id']}"]
    )


async def test_resolving_clears_the_reason_and_only_that_reason(live_app, evidence):
    conn, bus = live_app.state.db, live_app.state.bus
    iid = evidence["interview"]["id"]
    first = create_dispute(conn, bus, iid, evidence["segment"]["id"], "One.", "")
    second = create_dispute(conn, bus, iid, evidence["segment"]["id"], "Two.", "")

    resolved = resolve_dispute(conn, bus, iid, first["id"], "Accepted the correction.")

    assert resolved["status"] == "resolved"
    assert resolved["resolution"] == "Accepted the correction."
    assert resolved["resolved_at"]
    assert finding_state(conn, evidence["on_segment"]["id"]) == (
        "needs_review", [f"dispute:{second['id']}"]
    )

    resolve_dispute(conn, bus, iid, second["id"], "Noted.")

    assert finding_state(conn, evidence["on_segment"]["id"]) == ("ok", [])
    assert finding_state(conn, evidence["on_claim"]["id"]) == ("ok", [])
    assert event_types(live_app, iid) == ["dispute_updated"] * 4
    last = repo.list_events(conn, iid, 0)[-1]["payload"]["dispute"]
    assert last["status"] == "resolved" and last["resolution"] == "Noted."


async def test_a_segment_of_another_interview_cannot_be_disputed(live_app, evidence):
    other = seed_interview(live_app)

    with pytest.raises(LookupError):
        create_dispute(live_app.state.db, live_app.state.bus, other["id"], evidence["segment"]["id"], "x", "")
    with pytest.raises(LookupError):
        create_dispute(live_app.state.db, live_app.state.bus, other["id"], "seg_missing", "x", "")
    assert repo.list_disputes(live_app.state.db, other["id"]) == []


async def test_an_unknown_dispute_cannot_be_resolved(live_app, evidence):
    conn, bus = live_app.state.db, live_app.state.bus
    iid = evidence["interview"]["id"]
    dispute = create_dispute(conn, bus, iid, evidence["segment"]["id"], "x", "")
    other = seed_interview(live_app)

    with pytest.raises(LookupError):
        resolve_dispute(conn, bus, iid, "dsp_missing", "x")
    with pytest.raises(LookupError):
        resolve_dispute(conn, bus, other["id"], dispute["id"], "x")


async def test_a_dispute_before_any_assessment_affects_nothing(live_app):
    interview = seed_interview(live_app)
    conn = live_app.state.db
    segment = repo.insert_segment(
        conn, id=ids.new_id("seg"), interview_id=interview["id"], speaker="candidate", kind="turn",
        text="Early words.", stage="briefing", generation=1, status="complete",
    )

    dispute = create_dispute(conn, live_app.state.bus, interview["id"], segment["id"], "Later words.", "")

    assert repo.row_json(dispute, "affected_finding_ids_json") == []


async def test_marking_is_idempotent_per_reason_and_clearing_leaves_other_reasons(live_app, evidence):
    conn, bus = live_app.state.db, live_app.state.bus
    iid = evidence["interview"]["id"]
    run_id = evidence["run"]["id"]

    marked = mark_findings_needing_review(conn, bus, iid, "run", run_id, "replay_differs")
    again = mark_findings_needing_review(conn, bus, iid, "run", run_id, "replay_differs")
    mark_findings_needing_review(conn, bus, iid, "run", run_id, "dispute:dsp_x")

    assert marked == again == [evidence["on_run"]["id"]]
    assert finding_state(conn, evidence["on_run"]["id"]) == (
        "needs_review", ["replay_differs", "dispute:dsp_x"]
    )
    assert mark_findings_needing_review(conn, bus, iid, "run", "run_missing", "replay_differs") == []

    clear_review_reason(conn, bus, iid, "dispute:dsp_x")
    assert finding_state(conn, evidence["on_run"]["id"]) == ("needs_review", ["replay_differs"])
    clear_review_reason(conn, bus, iid, "replay_differs")
    assert finding_state(conn, evidence["on_run"]["id"]) == ("ok", [])
    assert event_types(live_app, iid) == []


# --- disputes, over HTTP -----------------------------------------------------------


def first_candidate_segment(app, interview_id):
    return next(
        row for row in repo.list_segments(app.state.db, interview_id) if row["speaker"] == "candidate"
    )


def test_the_candidate_disputes_a_segment_and_the_reviewer_resolves_it(client, app, scenario):
    flow = run_full_interview(client, scenario)
    iid = flow["candidate"]["id"]
    segment = first_candidate_segment(app, iid)

    created = client.post(
        f"/api/interviews/{iid}/disputes",
        json={"segment_id": segment["id"], "proposed_text": "I said the cache key only uses the query.",
              "reason": "The transcript dropped a word."},
        headers=ORIGIN,
    )

    assert created.status_code == 201, created.text
    dispute = created.json()
    assert dispute["segment_id"] == segment["id"]
    assert dispute["original_text"] == segment["text"]
    assert dispute["status"] == "open"
    # The scripted assessment cites the first claim, which came from this segment.
    assert dispute["affected_finding_ids"]
    body = client.get(f"/api/interviews/{iid}/assessment").json()
    assert [d["id"] for d in body["disputes"]] == [dispute["id"]]
    affected = {f["id"]: f for f in body["dimensions"] + body["findings"]}
    for finding_id in dispute["affected_finding_ids"]:
        assert affected[finding_id]["review_status"] == "needs_review"
        assert affected[finding_id]["review_reasons"] == [f"dispute:{dispute['id']}"]
    assert repo.get_segment(app.state.db, segment["id"])["text"] == segment["text"]

    refused = client.post(
        f"/api/interviews/{iid}/disputes/{dispute['id']}/resolve",
        json={"resolution": "Not for the candidate to decide."}, headers=ORIGIN,
    )
    assert refused.status_code == 403

    become_reviewer(client, flow["candidate"])
    resolved = client.post(
        f"/api/interviews/{iid}/disputes/{dispute['id']}/resolve",
        json={"resolution": "Listened again; the correction stands."}, headers=ORIGIN,
    )

    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolution"] == "Listened again; the correction stands."
    body = client.get(f"/api/interviews/{iid}/assessment").json()
    assert all(f["review_status"] == "ok" for f in body["dimensions"] + body["findings"])
    assert body["disputes"][0]["status"] == "resolved"
    assert event_types(app, iid)[-2:] == ["dispute_updated", "dispute_updated"]


def test_dispute_routes_refuse_what_is_not_theirs(client, app, scenario):
    flow = run_full_interview(client, scenario)
    iid = flow["candidate"]["id"]
    other = create_interview(client)  # the cookie now belongs to `other`
    segment = first_candidate_segment(app, iid)

    foreign = client.post(
        f"/api/interviews/{other['id']}/disputes",
        json={"segment_id": segment["id"], "proposed_text": "x", "reason": ""}, headers=ORIGIN,
    )
    assert foreign.status_code == 404

    blank = client.post(
        f"/api/interviews/{other['id']}/disputes",
        json={"segment_id": segment["id"], "proposed_text": "", "reason": ""}, headers=ORIGIN,
    )
    assert blank.status_code == 422

    become_reviewer(client, other)
    missing = client.post(
        f"/api/interviews/{other['id']}/disputes/dsp_missing/resolve",
        json={"resolution": "x"}, headers=ORIGIN,
    )
    assert missing.status_code == 404


# --- replays ----------------------------------------------------------------------------


def findings_referencing_run(client, iid, run_id):
    body = client.get(f"/api/interviews/{iid}/assessment").json()
    return [
        finding for finding in body["dimensions"] + body["findings"]
        if any(ref == {"type": "run", "id": run_id} for ref in finding["supporting_refs"] + finding["opposing_refs"])
    ]


def test_a_replay_that_agrees_leaves_the_original_and_the_findings_alone(client, app, scenario):
    flow = run_full_interview(client, scenario)
    iid = flow["candidate"]["id"]
    original = flow["run"]
    assert findings_referencing_run(client, iid, original["id"])

    started = client.post(f"/api/interviews/{iid}/replays", json={"run_id": original["id"]}, headers=ORIGIN)

    assert started.status_code == 202, started.text
    assert started.json()["replay_of"] == original["id"]
    assert started.json()["status"] == "queued"
    replay = wait_for_run(client, iid, started.json()["id"])
    assert replay["status"] == "completed"
    assert replay["differs_from_original"] is False
    assert replay["snapshot_id"] == original["snapshot_id"]
    assert replay["input_hash"] == original["input_hash"]
    assert client.get(f"/api/interviews/{iid}/runs/{original['id']}").json() == original
    for finding in findings_referencing_run(client, iid, original["id"]):
        assert finding["review_status"] == "ok"
        assert finding["review_reasons"] == []
    assert repo.count_runs(app.state.db, iid) == 2


def test_a_replay_that_differs_marks_the_findings_that_cite_the_original(client, app, scenario, monkeypatch):
    flow = run_full_interview(client, scenario)
    iid = flow["candidate"]["id"]
    original = flow["run"]
    monkeypatch.setattr(runs_module, "results_differ", lambda a, b: True)

    started = client.post(f"/api/interviews/{iid}/replays", json={"run_id": original["id"]}, headers=ORIGIN)
    replay = wait_for_run(client, iid, started.json()["id"])

    assert replay["differs_from_original"] is True
    assert client.get(f"/api/interviews/{iid}/runs/{original['id']}").json() == original
    cited = findings_referencing_run(client, iid, original["id"])
    assert cited
    for finding in cited:
        assert finding["review_status"] == "needs_review"
        assert finding["review_reasons"] == ["replay_differs"]
    body = client.get(f"/api/interviews/{iid}/assessment").json()
    assert replay["id"] in body["evidence"]["runs"]  # both results stay visible
    assert "replay_differs" not in json.dumps(
        [f for f in body["dimensions"] + body["findings"] if f not in cited]
    )
    assert event_types(app, iid).count("run_completed") == 2


def test_the_reviewer_may_replay_and_an_unknown_run_is_404(client, app, scenario):
    flow = run_full_interview(client, scenario)
    iid = flow["candidate"]["id"]
    become_reviewer(client, flow["candidate"])

    missing = client.post(f"/api/interviews/{iid}/replays", json={"run_id": "run_missing"}, headers=ORIGIN)
    assert missing.status_code == 404

    started = client.post(f"/api/interviews/{iid}/replays", json={"run_id": flow["run"]["id"]}, headers=ORIGIN)
    assert started.status_code == 202, started.text
    assert wait_for_run(client, iid, started.json()["id"])["status"] == "completed"
