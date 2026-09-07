"""Finishing an interview and the assessment it produces.

The full flow runs through the real routes with the local executor and the
scripted model: what these tests check is that every reference the report makes
resolves to a stored record, that an answer the validator rejects never becomes
a report, and that the finish route settles the interview's work before it asks
for one.
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app import ids
from app.evidence import findings as findings_module
from app.evidence.findings import NOT_ASSESSED_TEXT, PENDING_SUMMARY, build_assessment
from app.evidence.validate import validate_assessment_payload
from app.interview import prompts
from app.interview.llm_client import INVALID_REFS_MARKER, LLMError
from app.interview.prompts import DIMENSIONS, PROMPT_VERSION
from app.routes import interviews as interviews_module
from app.storage import repo
from tests.conftest import (
    COMPLETE_SOLUTION,
    INITIAL_CHECK,
    INITIAL_CHECKS,
    ORIGIN,
    become_reviewer,
    completed_run,
    create_interview,
    event_types,
    run_full_interview,
    save_files,
    seed_interview,
    seed_snapshot,
)

EVIDENCE_KEY = {"segment": "segments", "run": "runs", "claim": "claims", "snapshot": "snapshots"}


def get_assessment(client, interview_id):
    response = client.get(f"/api/interviews/{interview_id}/assessment")
    assert response.status_code == 200, response.text
    return response.json()


def all_refs(body):
    for finding in body["dimensions"] + body["findings"]:
        yield from finding["supporting_refs"]
        yield from finding["opposing_refs"]


def with_invalid_refs(monkeypatch):
    """Make every assessment prompt carry the marker that makes the double invent an id."""
    original = prompts.assessment_messages

    def marked(rubric, record):
        messages = original(rubric, record)
        messages[0]["content"] += f"\n{INVALID_REFS_MARKER}"
        return messages

    monkeypatch.setattr(findings_module, "assessment_messages", marked)


def failing_assessments(app, monkeypatch):
    """A model that still extracts claims but cannot write the assessment."""
    original = app.state.llm.complete_json

    async def complete_json(messages, **kwargs):
        if prompts.read_task(messages) == prompts.TASK_ASSESSMENT:
            raise LLMError("upstream down")
        return await original(messages, **kwargs)

    monkeypatch.setattr(app.state.llm, "complete_json", complete_json)


# --- the full flow ----------------------------------------------------------------


def test_the_full_flow_yields_a_complete_assessment_whose_every_ref_resolves(client, app, scenario):
    flow = run_full_interview(client, scenario)
    interview_id = flow["candidate"]["id"]

    assert flow["finish"]["status"] == "complete"
    body = get_assessment(client, interview_id)
    assert body["id"] == flow["finish"]["assessment_id"]
    assert body["status"] == "complete"
    assert body["model_id"] == "scripted-test-double"
    assert body["rubric_version"] == "v1"
    assert body["prompt_version"] == PROMPT_VERSION
    assert body["summary"]
    assert body["me"] == "candidate"
    assert body["disputes"] == []
    assert body["interview"]["id"] == interview_id
    assert body["interview"]["display_name"] == "Ada Lovelace"
    assert body["interview"]["finished_at"]

    assert [d["dimension"] for d in body["dimensions"]] == list(DIMENSIONS)
    assert all(d["is_dimension"] is True for d in body["dimensions"])
    assert 0 < len(body["findings"]) <= 6
    assert all(f["is_dimension"] is False for f in body["findings"])
    for finding in body["dimensions"] + body["findings"]:
        assert finding["id"].startswith("fnd_")
        assert finding["observation_level"] in ("demonstrated", "partly_demonstrated", "not_observed")
        assert finding["review_status"] == "ok"
        assert finding["review_reasons"] == []
        assert finding["has_run_ref"] is True
        assert finding["supporting_refs"]
    refs = list(all_refs(body))
    for ref in refs:
        assert ref["id"] in body["evidence"][EVIDENCE_KEY[ref["type"]]], ref
    assert {ref["type"] for ref in refs} >= {"segment", "run", "claim"}
    # The claim extractions were awaited before the record was assembled.
    assert body["evidence"]["claims"]
    assert flow["run"]["id"] in body["evidence"]["runs"]
    assert body["evidence"]["runs"][flow["run"]["id"]]["status"] == "completed"
    assert any(
        link["source_type"] == "run" and link["relation"] == "supports"
        for link in body["evidence"]["links"]
    )
    for link in body["evidence"]["links"]:
        assert link["source_id"] in body["evidence"][EVIDENCE_KEY[link["source_type"]]]
        assert link["target_id"] in body["evidence"][EVIDENCE_KEY[link["target_type"]]]

    row = repo.get_interview(app.state.db, interview_id)
    assert row["status"] == "finished"
    assert row["stage"] == "assessment"
    assert row["finished_at"]
    assert row["model_id"] == "scripted-test-double"
    events = repo.list_events(app.state.db, interview_id, 0)
    tail = [(event["type"], event["payload"]) for event in events[-3:]]
    assert tail == [
        ("stage_changed", {"stage": "assessment"}),
        ("assessment_completed", {"assessment_id": body["id"], "status": "complete"}),
        ("interview_finished", {}),
    ]


def test_finish_is_idempotent_once_finished(client, app, scenario):
    flow = run_full_interview(client, scenario)
    interview_id = flow["candidate"]["id"]
    before = event_types(app, interview_id)

    again = client.post(f"/api/interviews/{interview_id}/finish", headers=ORIGIN)

    assert again.status_code == 200
    assert again.json() == flow["finish"]
    assert event_types(app, interview_id) == before
    assert app.state.db.execute(
        "SELECT COUNT(*) AS n FROM assessments WHERE interview_id = ?", (interview_id,)
    ).fetchone()["n"] == 1


def test_a_failure_after_finishing_started_is_resumed_by_the_next_finish(client, app, scenario, monkeypatch):
    calls = []
    original = interviews_module.build_assessment

    async def flaky(app_, interview_id):
        calls.append(interview_id)
        if len(calls) == 1:
            raise RuntimeError("sqlite went away")
        return await original(app_, interview_id)

    monkeypatch.setattr(interviews_module, "build_assessment", flaky)
    flow = run_full_interview(client, scenario, finish=False)
    interview_id = flow["candidate"]["id"]

    with pytest.raises(RuntimeError):
        client.post(f"/api/interviews/{interview_id}/finish", headers=ORIGIN)

    assert repo.get_interview(app.state.db, interview_id)["status"] == "finishing"
    assert client.get(f"/api/interviews/{interview_id}/assessment").status_code == 404

    second = client.post(f"/api/interviews/{interview_id}/finish", headers=ORIGIN)

    assert second.status_code == 200, second.text
    assert second.json()["status"] == "complete"
    assert calls == [interview_id, interview_id]
    row = repo.get_interview(app.state.db, interview_id)
    assert row["status"] == "finished"
    assert row["finished_at"]
    types = event_types(app, interview_id)
    assert types.count("assessment_completed") == 1
    assert types[-1] == "interview_finished"
    assert get_assessment(client, interview_id)["id"] == second.json()["assessment_id"]


def test_a_crash_after_the_assessment_was_stored_is_recovered_without_rebuilding(client, app, scenario):
    flow = run_full_interview(client, scenario)
    interview_id = flow["candidate"]["id"]
    # The attempt got as far as the assessment and died before the row was marked.
    repo.update_interview(app.state.db, interview_id, status="finishing", finished_at=None)
    before = event_types(app, interview_id)

    response = client.post(f"/api/interviews/{interview_id}/finish", headers=ORIGIN)

    assert response.status_code == 200, response.text
    assert response.json() == flow["finish"]
    row = repo.get_interview(app.state.db, interview_id)
    assert row["status"] == "finished"
    assert row["finished_at"]
    assert event_types(app, interview_id) == [*before, "interview_finished"]
    assert app.state.db.execute(
        "SELECT COUNT(*) AS n FROM assessments WHERE interview_id = ?", (interview_id,)
    ).fetchone()["n"] == 1


def test_a_hanging_voice_agent_does_not_hold_up_finish(client, app, candidate, monkeypatch, caplog):
    class HangingVoice:
        enabled = True

        async def stop_agent(self, agent_id):
            await asyncio.sleep(30)

    app.state.voice = HangingVoice()
    monkeypatch.setattr(interviews_module, "VOICE_STOP_TIMEOUT_SECONDS", 0.1)
    repo.update_interview(app.state.db, candidate["id"], status="live", agora_agent_id="agent_9")
    started = time.monotonic()

    with caplog.at_level("WARNING"):
        response = client.post(f"/api/interviews/{candidate['id']}/finish", headers=ORIGIN)

    assert response.status_code == 200, response.text
    assert time.monotonic() - started < 5
    assert "agent_9 did not stop" in caplog.text
    assert repo.get_interview(app.state.db, candidate["id"])["status"] == "finished"


def test_two_finishes_at_once_share_one_assessment(client, app, scenario, monkeypatch):
    original = interviews_module.build_assessment

    async def slow(app_, interview_id):
        await asyncio.sleep(0.3)
        return await original(app_, interview_id)

    monkeypatch.setattr(interviews_module, "build_assessment", slow)
    flow = run_full_interview(client, scenario, finish=False)
    interview_id = flow["candidate"]["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(
            lambda _: client.post(f"/api/interviews/{interview_id}/finish", headers=ORIGIN), range(2)
        ))

    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    assert app.state.db.execute(
        "SELECT COUNT(*) AS n FROM assessments WHERE interview_id = ?", (interview_id,)
    ).fetchone()["n"] == 1


def test_the_reviewer_reads_the_same_assessment(client, scenario):
    flow = run_full_interview(client, scenario)
    become_reviewer(client, flow["candidate"])

    body = get_assessment(client, flow["candidate"]["id"])

    assert body["me"] == "reviewer"
    assert body["id"] == flow["finish"]["assessment_id"]


def test_there_is_no_assessment_before_finish(client, candidate):
    response = client.get(f"/api/interviews/{candidate['id']}/assessment")

    assert response.status_code == 404


def test_finish_waits_for_the_run_in_flight(client, app, scenario):
    class SlowExecutor:
        name = "local"

        def __init__(self, inner):
            self.inner = inner

        async def run(self, files, script, **kwargs):
            await asyncio.sleep(0.4)
            return await self.inner.run(files, script, **kwargs)

    app.state.executor = SlowExecutor(app.state.executor)
    candidate = create_interview(client)
    interview_id = candidate["id"]
    client.post(f"/api/interviews/{interview_id}/start", headers=ORIGIN)
    files = {**scenario.editable_files, "search.py": COMPLETE_SOLUTION.read_text(encoding="utf-8")}
    saved = save_files(client, interview_id, files)
    run = client.post(
        f"/api/interviews/{interview_id}/runs",
        json={"snapshot_id": saved["snapshot_id"], "check_ids": [INITIAL_CHECK]},
        headers=ORIGIN,
    ).json()

    response = client.post(f"/api/interviews/{interview_id}/finish", headers=ORIGIN)

    assert response.status_code == 200, response.text
    body = get_assessment(client, interview_id)
    assert body["evidence"]["runs"][run["id"]]["status"] == "completed"
    types = event_types(app, interview_id)
    assert types.index("run_completed") < types.index("assessment_completed")


def test_finish_stops_the_voice_agent_first(client, app, candidate):
    stopped = []

    class StubVoice:
        enabled = True

        async def stop_agent(self, agent_id):
            stopped.append(agent_id)

    app.state.voice = StubVoice()
    repo.update_interview(app.state.db, candidate["id"], status="live", agora_agent_id="agent_9")

    response = client.post(f"/api/interviews/{candidate['id']}/finish", headers=ORIGIN)

    assert response.status_code == 200, response.text
    assert stopped == ["agent_9"]


# --- when the model's answer cannot be trusted ------------------------------------


def test_invalid_refs_are_retried_once_then_shown_as_pending_observations(client, app, scenario, monkeypatch):
    with_invalid_refs(monkeypatch)
    asked = []
    original = app.state.llm.complete_json

    async def counting(messages, **kwargs):
        if prompts.read_task(messages) == prompts.TASK_ASSESSMENT:
            asked.append(messages)
        return await original(messages, **kwargs)

    monkeypatch.setattr(app.state.llm, "complete_json", counting)

    flow = run_full_interview(client, scenario)

    assert flow["finish"]["status"] == "pending"
    assert len(asked) == 2
    assert "seg_nope" in asked[1][-1]["content"]  # the retry is told what was wrong
    assert "seg_nope" not in asked[0][-1]["content"]

    body = get_assessment(client, flow["candidate"]["id"])
    assert body["status"] == "pending"
    assert body["summary"] == PENDING_SUMMARY
    assert body["model_id"] == "scripted-test-double"
    assert body["rubric_version"] == "v1"
    assert [d["dimension"] for d in body["dimensions"]] == list(DIMENSIONS)
    for dimension in body["dimensions"]:
        assert dimension["observation_level"] == "not_observed"
        assert dimension["explanation"] == NOT_ASSESSED_TEXT
        assert dimension["supporting_refs"] == dimension["opposing_refs"] == []
        assert dimension["has_run_ref"] is False

    checks = {check.id: check for check in scenario.checks}
    observed = body["findings"]
    assert [f["title"] for f in observed] == [checks[c].name for c in INITIAL_CHECKS]
    for finding in observed:
        assert finding["dimension"] == "implementing_checking_fix"
        assert finding["is_dimension"] is False
        assert finding["observation_level"] == "demonstrated"
        assert finding["supporting_refs"] == [{"type": "run", "id": flow["run"]["id"]}]
        assert finding["opposing_refs"] == []
        assert flow["run"]["id"] in finding["explanation"]
        assert finding["has_run_ref"] is True
    assert "seg_nope" not in {ref["id"] for ref in all_refs(body)}
    assert flow["run"]["id"] in body["evidence"]["runs"]

    row = repo.get_interview(app.state.db, flow["candidate"]["id"])
    assert row["status"] == "finished"
    assert row["model_id"] == "scripted-test-double"
    assert event_types(app, row["id"])[-2:] == ["assessment_completed", "interview_finished"]


def test_a_model_failure_yields_the_pending_assessment(client, app, scenario, monkeypatch):
    failing_assessments(app, monkeypatch)

    flow = run_full_interview(client, scenario)

    assert flow["finish"]["status"] == "pending"
    body = get_assessment(client, flow["candidate"]["id"])
    assert body["summary"] == PENDING_SUMMARY
    assert len(body["findings"]) == len(INITIAL_CHECKS)


async def test_fallback_observations_name_the_failing_checks_and_skip_replays(live_app, monkeypatch):
    failing_assessments(live_app, monkeypatch)
    interview = seed_interview(live_app)
    completed_run(live_app, interview["id"], [INITIAL_CHECK], {INITIAL_CHECK: True})
    latest = completed_run(
        live_app, interview["id"], ["access_filtering", INITIAL_CHECK], {"access_filtering": True}
    )
    completed_run(live_app, interview["id"], [INITIAL_CHECK], {INITIAL_CHECK: True}, replay_of=latest["id"])
    completed_run(live_app, interview["id"], [INITIAL_CHECK], status="timeout")

    assessment = await build_assessment(live_app, interview["id"])

    assert assessment["status"] == "pending"
    rows = repo.list_findings(live_app.state.db, assessment["id"])
    observed = [row for row in rows if not row["is_dimension"]]
    assert [(row["title"], row["observation_level"]) for row in observed] == [
        ("Permission filtering", "demonstrated"),
        ("Cross-company isolation", "not_observed"),
    ]
    refs = [repo.list_finding_refs(live_app.state.db, row["id"]) for row in observed]
    assert [(r[0]["ref_type"], r[0]["ref_id"], r[0]["role"]) for r in refs] == [
        ("run", latest["id"], "supports"),
        ("run", latest["id"], "challenges"),
    ]
    assert [event["type"] for event in repo.list_events(live_app.state.db, interview["id"], 0)] == [
        "assessment_completed"
    ]


async def test_fallback_without_a_run_has_only_the_four_dimensions(live_app, monkeypatch):
    failing_assessments(live_app, monkeypatch)
    interview = seed_interview(live_app)

    assessment = await build_assessment(live_app, interview["id"])

    rows = repo.list_findings(live_app.state.db, assessment["id"])
    assert [(row["dimension"], row["is_dimension"], row["observation_level"]) for row in rows] == [
        (dimension, 1, "not_observed") for dimension in DIMENSIONS
    ]


# --- the validator ------------------------------------------------------------------


@pytest.fixture
async def record(live_app):
    """An interview with one of each referenceable record, and a valid payload for it."""
    interview = seed_interview(live_app)
    conn = live_app.state.db
    segment = repo.insert_segment(
        conn, id=ids.new_id("seg"), interview_id=interview["id"], speaker="candidate",
        kind="turn", text="The cache key is shared.", stage="investigation", generation=1,
        status="complete",
    )
    snapshot = seed_snapshot(live_app, interview["id"], dict(live_app.state.scenario.editable_files))
    run = completed_run(live_app, interview["id"], [INITIAL_CHECK], {INITIAL_CHECK: True})
    claim = repo.insert_claim(
        conn, id=ids.new_id("clm"), interview_id=interview["id"], segment_id=segment["id"],
        statement="The cache key is shared.", claim_type="diagnosis", scope="cross_company",
        stage="investigation", clarity="clear",
    )
    foreign = seed_interview(live_app)
    foreign_segment = repo.insert_segment(
        conn, id=ids.new_id("seg"), interview_id=foreign["id"], speaker="candidate", kind="turn",
        text="Someone else's words.", stage="investigation", generation=1, status="complete",
    )
    refs = [
        {"type": "segment", "id": segment["id"]},
        {"type": "run", "id": run["id"]},
        {"type": "claim", "id": claim["id"]},
        {"type": "snapshot", "id": snapshot["id"]},
    ]

    def entry(dimension, **overrides):
        return {
            "dimension": dimension,
            "title": "A finding title",
            "observation_level": "demonstrated",
            "explanation": "An explanation that is comfortably long enough.",
            "supporting_refs": list(refs),
            "opposing_refs": [],
            "assistance": "No assistance was recorded.",
            "uncertainty": "The record settles little.",
            "follow_up": "",
            **overrides,
        }

    def payload(**overrides):
        return {
            "summary": "A summary of the interview.",
            "dimensions": [entry(dimension) for dimension in DIMENSIONS],
            "findings": [entry("understanding_problem", title="Expanded")],
            **overrides,
        }

    return {
        "interview_id": interview["id"], "conn": conn, "payload": payload, "entry": entry,
        "refs": refs, "foreign_segment_id": foreign_segment["id"],
    }


async def test_a_finding_citing_a_claim_carries_the_segment_it_was_read_from(live_app, record):
    """A claim is the model's reading; the drawer has to show the words behind it."""
    from app.evidence.findings import assessment_view

    claim_id = next(ref["id"] for ref in record["refs"] if ref["type"] == "claim")
    payload = record["payload"](
        findings=[record["entry"]("understanding_problem", supporting_refs=[
            {"type": "claim", "id": claim_id}
        ])],
    )
    from app.evidence import findings as findings_module

    assessment = repo.insert_assessment(
        record["conn"], id=ids.new_id("asm"), interview_id=record["interview_id"],
        status="complete", rubric_version="v1", prompt_version="v1", model_id="scripted",
        summary="A summary of the interview.",
    )
    findings_module._store_findings(
        record["conn"], record["interview_id"], assessment["id"],
        findings_module._entries_from_payload(payload),
    )

    view = assessment_view(record["conn"], record["interview_id"], "reviewer")

    segment_id = record["conn"].execute(
        "SELECT segment_id FROM claims WHERE id = ?", (claim_id,)
    ).fetchone()[0]
    finding = view["findings"][0]
    assert finding["supporting_refs"] == [{"type": "claim", "id": claim_id}]
    assert segment_id in view["evidence"]["segments"]


def errors_for(record, payload):
    return validate_assessment_payload(record["conn"], record["interview_id"], payload)


async def test_a_valid_payload_has_no_errors(record):
    assert errors_for(record, record["payload"]()) == []


async def test_a_missing_dimension_is_an_error(record):
    payload = record["payload"]()
    payload["dimensions"] = payload["dimensions"][1:]

    errors = errors_for(record, payload)

    assert len(errors) == 1
    assert "understanding_problem" in errors[0] and "missing" in errors[0]


async def test_an_extra_or_repeated_dimension_is_an_error(record):
    payload = record["payload"]()
    payload["dimensions"].append(record["entry"]("understanding_problem"))
    payload["dimensions"].append(record["entry"]("charisma"))

    errors = errors_for(record, payload)

    assert len(errors) == 2
    assert any("charisma" in error for error in errors)


async def test_a_finding_outside_the_four_dimensions_is_an_error(record):
    payload = record["payload"](findings=[record["entry"]("charisma")])

    assert any("charisma" in error for error in errors_for(record, payload))


async def test_an_invalid_observation_level_is_an_error(record):
    payload = record["payload"](findings=[record["entry"]("understanding_problem", observation_level="excellent")])

    errors = errors_for(record, payload)

    assert len(errors) == 1
    assert "excellent" in errors[0]


async def test_more_than_six_findings_is_an_error(record):
    payload = record["payload"](findings=[record["entry"]("understanding_problem")] * 7)

    assert any("6" in error for error in errors_for(record, payload))


async def test_an_unknown_or_foreign_ref_is_an_error(record):
    bad = [
        {"type": "segment", "id": "seg_nope"},
        {"type": "segment", "id": record["foreign_segment_id"]},
        {"type": "recording", "id": "rec_1"},
        "not a ref",
    ]
    payload = record["payload"](findings=[record["entry"]("understanding_problem", opposing_refs=bad)])

    errors = errors_for(record, payload)

    assert len(errors) == 4
    assert any("seg_nope" in error for error in errors)
    assert any(record["foreign_segment_id"] in error for error in errors)


async def test_a_short_explanation_is_an_error(record):
    payload = record["payload"](findings=[record["entry"]("understanding_problem", explanation="Too short.")])

    errors = errors_for(record, payload)

    assert len(errors) == 1
    assert "20" in errors[0]


@pytest.mark.parametrize(
    ("field", "text"),
    [
        ("summary", "Overall score: strong."),
        ("summary", "The candidate scores well on the release question."),
        ("title", "Rank among candidates"),
        ("title", "Ranked third of the week"),
        ("explanation", "Their personality came through in every answer."),
        ("explanation", "Two personalities were on show during the interview."),
        ("uncertainty", "Whether they were HONEST about the tests."),
        ("uncertainty", "They spoke honestly about the untested path, it seems."),
        ("follow_up", "Ask whether they were dishonest."),
        ("follow_up", "Ask whether the ranking of fixes was theirs."),
        # Inflections the first pass missed; each is the same promise broken.
        ("summary", "The rankings put them mid-pack."),
        ("explanation", "Their honesty was not in question at any point."),
        ("title", "A careful scorer of tradeoffs"),
    ],
)
async def test_forbidden_words_are_errors_wherever_they_appear(record, field, text):
    if field == "summary":
        payload = record["payload"](summary=text)
    else:
        payload = record["payload"](findings=[record["entry"]("understanding_problem", **{field: text})])

    errors = errors_for(record, payload)

    assert len(errors) == 1
    assert field in errors[0]


async def test_a_word_that_merely_contains_a_forbidden_one_is_fine(record):
    payload = record["payload"](
        summary="The candidate underscored the frank tradeoff and scorned the shortcut."
    )

    assert errors_for(record, payload) == []


async def test_a_payload_of_the_wrong_shape_is_an_error_not_a_crash(record):
    assert errors_for(record, ["not", "a", "dict"])
    assert errors_for(record, {"summary": 3, "dimensions": "x", "findings": None})
    assert errors_for(record, {"summary": "ok", "dimensions": ["not an entry"] * 4, "findings": []})
