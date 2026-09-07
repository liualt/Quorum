"""Claim extraction and evidence links.

A claim is what the model read into one candidate segment, stored as an
interpretation; a link is a validated row between two records. `ScriptedLLM`
answers the claims prompt from keyword tables, so the assertions are about what
gets stored, what gets dropped, and which rows point at which.
"""

import json

import pytest

from app import ids
from app.evidence.claims import extract_and_store_claims
from app.evidence.links import SCOPE_TO_CHECK, link_challenge, link_run_to_claims
from app.interview.llm_client import LLMError
from app.interview.state import ControllerState
from app.storage import repo
from tests.conftest import CHANGED_CHECK, INITIAL_CHECK, completed_run, seed_interview

CROSS_COMPANY_TEXT = "The cache key only uses the query, so another company can see our documents"
REVOCATION_TEXT = "Revocation is handled: permissions are re-read on every request."
REVISION_TEXT = "Actually I was wrong, revocation still returns stale results"
VAGUE_TEXT = "I think the cache key might be shared across companies, not sure."
PLAIN_TEXT = "I have finished reading the brief."


def say(app, interview_id, text, *, speaker="candidate", kind="turn", stage="investigation"):
    return repo.insert_segment(
        app.state.db, id=ids.new_id("seg"), interview_id=interview_id, speaker=speaker,
        kind=kind, text=text, stage=stage, generation=1, status="complete",
    )


def link_tuples(app, interview_id):
    return [
        (row["source_type"], row["source_id"], row["relation"], row["target_type"], row["target_id"])
        for row in repo.list_links(app.state.db, interview_id)
    ]


def state_of(app, interview_id) -> ControllerState:
    return app.state.controller.load_state(interview_id)


def scripted_payload(claims, covered=None, contradiction_note=None):
    return {"claims": claims, "covered": covered or {}, "contradiction_note": contradiction_note}


def claim(statement="A claim.", claim_type="diagnosis", scope="cross_company", clarity="clear",
          revises_claim_id=None):
    return {"statement": statement, "claim_type": claim_type, "scope": scope, "clarity": clarity,
            "revises_claim_id": revises_claim_id}


def answer_with(app, monkeypatch, payload):
    async def complete_json(messages, **kwargs):
        return payload

    monkeypatch.setattr(app.state.llm, "complete_json", complete_json)


# --- extraction ------------------------------------------------------------------


async def test_a_diagnosis_becomes_a_claim_and_marks_the_topic_covered(live_app):
    interview = seed_interview(live_app)
    segment = say(live_app, interview["id"], CROSS_COMPANY_TEXT)

    stored = await extract_and_store_claims(live_app, interview["id"], segment["id"])

    assert len(stored) == 1
    row = stored[0]
    assert row["id"].startswith("clm_")
    assert row["segment_id"] == segment["id"]
    assert row["statement"] == CROSS_COMPANY_TEXT
    assert row["claim_type"] == "diagnosis"
    assert row["scope"] == "cross_company"
    assert row["stage"] == "investigation"
    assert row["clarity"] == "clear"
    assert row["interpretation_status"] == "interpretation"
    assert [c["id"] for c in repo.list_claims(live_app.state.db, interview["id"])] == [row["id"]]
    assert link_tuples(live_app, interview["id"]) == []

    state = state_of(live_app, interview["id"])
    assert state.covered["cross_company"] is True
    assert state.covered["initial_explanation"] is True
    assert state.covered["release_decision"] is False
    assert state.last_clarity == "clear"
    assert state.contradiction_note is None


async def test_a_hedged_claim_marks_the_last_answer_vague(live_app):
    interview = seed_interview(live_app)
    segment = say(live_app, interview["id"], VAGUE_TEXT)

    stored = await extract_and_store_claims(live_app, interview["id"], segment["id"])

    assert stored and all(row["clarity"] == "vague" for row in stored)
    assert state_of(live_app, interview["id"]).last_clarity == "vague"


async def test_a_segment_without_claims_stores_nothing_and_clears_vagueness(live_app):
    interview = seed_interview(live_app, state_json=json.dumps({"last_clarity": "vague"}))
    segment = say(live_app, interview["id"], PLAIN_TEXT)

    assert await extract_and_store_claims(live_app, interview["id"], segment["id"]) == []

    assert repo.list_claims(live_app.state.db, interview["id"]) == []
    assert state_of(live_app, interview["id"]).last_clarity == "clear"


async def test_covered_flags_are_only_ever_set_never_cleared(live_app, monkeypatch):
    interview = seed_interview(
        live_app, state_json=json.dumps({"covered": {"release_decision": True}})
    )
    segment = say(live_app, interview["id"], PLAIN_TEXT)
    answer_with(live_app, monkeypatch, scripted_payload(
        [], covered={"release_decision": False, "revocation": True, "not_a_flag": True}
    ))

    await extract_and_store_claims(live_app, interview["id"], segment["id"])

    covered = state_of(live_app, interview["id"]).covered
    assert covered["release_decision"] is True
    assert covered["revocation"] is True
    assert "not_a_flag" not in covered


async def test_the_contradiction_note_is_taken_only_when_it_says_something(live_app, monkeypatch):
    interview = seed_interview(live_app, state_json=json.dumps({"contradiction_note": "kept"}))
    segment = say(live_app, interview["id"], PLAIN_TEXT)

    answer_with(live_app, monkeypatch, scripted_payload([], contradiction_note="   "))
    await extract_and_store_claims(live_app, interview["id"], segment["id"])
    assert state_of(live_app, interview["id"]).contradiction_note == "kept"

    answer_with(live_app, monkeypatch, scripted_payload([], contradiction_note="earlier: per user"))
    await extract_and_store_claims(live_app, interview["id"], segment["id"])
    assert state_of(live_app, interview["id"]).contradiction_note == "earlier: per user"


async def test_the_extractor_never_clobbers_a_turn_recorded_during_its_model_call(live_app, monkeypatch):
    """The state is read after the model answers, under the lock, never before."""
    interview = seed_interview(live_app)
    segment = say(live_app, interview["id"], PLAIN_TEXT)

    async def complete_json(messages, **kwargs):
        # A turn lands while the model is thinking.
        state = live_app.state.controller.load_state(interview["id"])
        state.turns_total = 7
        live_app.state.controller.save_state(interview["id"], state)
        return scripted_payload([], covered={"revocation": True})

    monkeypatch.setattr(live_app.state.llm, "complete_json", complete_json)

    await extract_and_store_claims(live_app, interview["id"], segment["id"])

    state = state_of(live_app, interview["id"])
    assert state.turns_total == 7
    assert state.covered["revocation"] is True


# --- validation of the model's answer -------------------------------------------


async def test_claims_with_invalid_enums_are_dropped_and_at_most_six_are_kept(live_app, monkeypatch):
    interview = seed_interview(live_app)
    segment = say(live_app, interview["id"], PLAIN_TEXT)
    claims = [claim(statement=f"claim {n}") for n in range(7)]
    claims.insert(1, claim(statement="bad type", claim_type="verdict"))
    claims.insert(2, claim(statement="bad scope", scope="everything"))
    claims.insert(3, claim(statement="bad clarity", clarity="crisp"))
    claims.insert(4, {"claim_type": "diagnosis", "scope": "general", "clarity": "clear"})
    answer_with(live_app, monkeypatch, scripted_payload(claims))

    stored = await extract_and_store_claims(live_app, interview["id"], segment["id"])

    assert [row["statement"] for row in stored] == [f"claim {n}" for n in range(6)]


async def test_a_revision_of_a_claim_from_another_interview_is_dropped(live_app, monkeypatch):
    other = seed_interview(live_app)
    foreign = say(live_app, other["id"], REVOCATION_TEXT)
    [foreign_claim] = await extract_and_store_claims(live_app, other["id"], foreign["id"])

    interview = seed_interview(live_app)
    segment = say(live_app, interview["id"], REVISION_TEXT)
    answer_with(live_app, monkeypatch, scripted_payload([
        claim(statement=REVISION_TEXT, scope="revocation", revises_claim_id=foreign_claim["id"]),
        claim(statement="made up", scope="revocation", revises_claim_id="clm_invented"),
    ]))

    stored = await extract_and_store_claims(live_app, interview["id"], segment["id"])

    # The statements are kept; the invented relationships are not.
    assert [row["statement"] for row in stored] == [REVISION_TEXT, "made up"]
    assert link_tuples(live_app, interview["id"]) == []
    assert link_tuples(live_app, other["id"]) == []


async def test_a_revision_links_the_new_claim_to_the_one_it_changes(live_app):
    interview = seed_interview(live_app)
    first = say(live_app, interview["id"], REVOCATION_TEXT)
    [earlier] = await extract_and_store_claims(live_app, interview["id"], first["id"])
    assert earlier["scope"] == "revocation"

    second = say(live_app, interview["id"], REVISION_TEXT)
    stored = await extract_and_store_claims(live_app, interview["id"], second["id"])

    revised = [row for row in stored if row["scope"] == "revocation"]
    assert len(revised) == 1
    assert link_tuples(live_app, interview["id"]) == [
        ("claim", revised[0]["id"], "revises", "claim", earlier["id"])
    ]


@pytest.mark.parametrize("payload", [{"claims": "nope"}, ["a", "list"], {"claims": [["x"]]}])
async def test_a_malformed_answer_stores_nothing(live_app, monkeypatch, payload, caplog):
    interview = seed_interview(live_app)
    segment = say(live_app, interview["id"], CROSS_COMPANY_TEXT)
    answer_with(live_app, monkeypatch, payload)

    with caplog.at_level("WARNING"):
        assert await extract_and_store_claims(live_app, interview["id"], segment["id"]) == []

    assert repo.list_claims(live_app.state.db, interview["id"]) == []
    assert state_of(live_app, interview["id"]).covered["cross_company"] is False
    assert segment["id"] in caplog.text


async def test_a_model_failure_is_logged_and_stores_nothing(live_app, monkeypatch, caplog):
    interview = seed_interview(live_app)
    segment = say(live_app, interview["id"], CROSS_COMPANY_TEXT)

    async def failing(messages, **kwargs):
        raise LLMError("upstream down")

    monkeypatch.setattr(live_app.state.llm, "complete_json", failing)

    with caplog.at_level("WARNING"):
        assert await extract_and_store_claims(live_app, interview["id"], segment["id"]) == []

    assert repo.list_claims(live_app.state.db, interview["id"]) == []
    assert "upstream down" in caplog.text


async def test_an_unknown_or_foreign_segment_is_ignored(live_app):
    interview = seed_interview(live_app)
    other = seed_interview(live_app)
    segment = say(live_app, other["id"], CROSS_COMPANY_TEXT)

    assert await extract_and_store_claims(live_app, interview["id"], "seg_missing") == []
    assert await extract_and_store_claims(live_app, interview["id"], segment["id"]) == []

    assert repo.list_claims(live_app.state.db, other["id"]) == []


async def test_the_prompt_carries_the_prior_claims_the_recent_transcript_and_the_runs(live_app, monkeypatch):
    interview = seed_interview(live_app)
    first = say(live_app, interview["id"], REVOCATION_TEXT)
    [earlier] = await extract_and_store_claims(live_app, interview["id"], first["id"])
    run = completed_run(live_app, interview["id"], [INITIAL_CHECK], {INITIAL_CHECK: True})
    for n in range(8):
        say(live_app, interview["id"], f"filler {n}", speaker="technical")
    segment = say(live_app, interview["id"], PLAIN_TEXT)
    say(live_app, interview["id"], "a later reply", speaker="technical")
    seen = []

    async def complete_json(messages, **kwargs):
        seen.append(messages)
        return scripted_payload([])

    monkeypatch.setattr(live_app.state.llm, "complete_json", complete_json)
    await extract_and_store_claims(live_app, interview["id"], segment["id"])

    [messages] = seen
    system = messages[0]["content"]
    assert messages[-1]["content"] == PLAIN_TEXT
    assert earlier["id"] in system
    assert run["id"] in system
    assert "filler 7" in system and "filler 1" not in system  # the six before this segment
    assert "a later reply" not in system


# --- run links --------------------------------------------------------------------


async def test_a_failing_check_challenges_the_claim_and_a_passing_one_supports_it(live_app):
    interview = seed_interview(live_app)
    segment = say(live_app, interview["id"], CROSS_COMPANY_TEXT)
    [diagnosis] = await extract_and_store_claims(live_app, interview["id"], segment["id"])
    check = SCOPE_TO_CHECK["cross_company"]
    failing = completed_run(live_app, interview["id"], [check], {check: False})
    passing = completed_run(live_app, interview["id"], [check], {check: True})

    first = link_run_to_claims(live_app.state.db, interview["id"], failing)
    second = link_run_to_claims(live_app.state.db, interview["id"], passing)

    assert [row["relation"] for row in first] == ["challenges"]
    assert [row["relation"] for row in second] == ["supports"]
    assert link_tuples(live_app, interview["id"]) == [
        ("run", failing["id"], "challenges", "claim", diagnosis["id"]),
        ("run", passing["id"], "supports", "claim", diagnosis["id"]),
    ]


async def test_only_diagnoses_fixes_and_release_decisions_of_the_checks_scope_are_linked(live_app):
    interview = seed_interview(live_app)
    conn = live_app.state.db
    segment = say(live_app, interview["id"], PLAIN_TEXT)

    def store(claim_type, scope):
        return repo.insert_claim(
            conn, id=ids.new_id("clm"), interview_id=interview["id"], segment_id=segment["id"],
            statement=f"{claim_type} about {scope}", claim_type=claim_type, scope=scope,
            stage="investigation", clarity="clear",
        )

    linked = [store("diagnosis", "revocation"), store("fix_description", "revocation"),
              store("release_decision", "revocation")]
    store("test_plan", "revocation")
    store("uncertainty", "revocation")
    store("diagnosis", "cross_company")
    store("diagnosis", "general")
    run = completed_run(live_app, interview["id"], [CHANGED_CHECK], {CHANGED_CHECK: True})

    rows = link_run_to_claims(conn, interview["id"], run)

    assert sorted(row["target_id"] for row in rows) == sorted(c["id"] for c in linked)
    assert all(row["relation"] == "supports" for row in rows)


async def test_a_claim_made_after_the_run_is_not_linked_and_links_are_not_duplicated(live_app):
    interview = seed_interview(live_app)
    conn = live_app.state.db
    before = say(live_app, interview["id"], CROSS_COMPANY_TEXT)
    [early] = await extract_and_store_claims(live_app, interview["id"], before["id"])
    run = completed_run(live_app, interview["id"], [INITIAL_CHECK], {INITIAL_CHECK: False})
    after = say(live_app, interview["id"], CROSS_COMPANY_TEXT)
    # What matters is when the candidate spoke relative to the run's request,
    # not when the claim row was written; the clock is pinned to say so.
    repo.update_segment(conn, before["id"], created_at="2026-09-07T10:00:00.000Z")
    run = repo.update_run(conn, run["id"], created_at="2026-09-07T10:00:01.000Z")
    repo.update_segment(conn, after["id"], created_at="2026-09-07T10:00:02.000Z")
    await extract_and_store_claims(live_app, interview["id"], after["id"])

    link_run_to_claims(conn, interview["id"], run)
    again = link_run_to_claims(conn, interview["id"], run)

    assert again == []
    assert link_tuples(live_app, interview["id"]) == [
        ("run", run["id"], "challenges", "claim", early["id"])
    ]


async def test_a_claim_spoken_as_the_run_was_requested_counts_as_before_it(live_app):
    interview = seed_interview(live_app)
    conn = live_app.state.db
    segment = say(live_app, interview["id"], CROSS_COMPANY_TEXT)
    [claim] = await extract_and_store_claims(live_app, interview["id"], segment["id"])
    run = completed_run(live_app, interview["id"], [INITIAL_CHECK], {INITIAL_CHECK: True})
    repo.update_segment(conn, segment["id"], created_at="2026-09-07T10:00:00.000Z")
    run = repo.update_run(conn, run["id"], created_at="2026-09-07T10:00:00.000Z")

    rows = link_run_to_claims(conn, interview["id"], run)

    assert [(row["relation"], row["target_id"]) for row in rows] == [("supports", claim["id"])]


async def test_a_run_that_landed_before_the_claims_were_read_is_still_linked(live_app):
    """Extraction is asynchronous; a quick run completes before the model answers."""
    interview = seed_interview(live_app)
    conn = live_app.state.db
    earlier = completed_run(live_app, interview["id"], [INITIAL_CHECK], {INITIAL_CHECK: True})
    segment = say(live_app, interview["id"], CROSS_COMPANY_TEXT)
    later = completed_run(live_app, interview["id"], [INITIAL_CHECK], {INITIAL_CHECK: False})
    completed_run(live_app, interview["id"], [INITIAL_CHECK], {INITIAL_CHECK: True}, replay_of=later["id"])
    repo.update_run(conn, earlier["id"], created_at="2026-09-07T10:00:00.000Z")
    repo.update_segment(conn, segment["id"], created_at="2026-09-07T10:00:01.000Z")
    repo.update_run(conn, later["id"], created_at="2026-09-07T10:00:02.000Z")

    [diagnosis] = await extract_and_store_claims(live_app, interview["id"], segment["id"])

    assert link_tuples(live_app, interview["id"]) == [
        ("run", later["id"], "challenges", "claim", diagnosis["id"])
    ]


async def test_a_run_without_results_links_nothing(live_app):
    interview = seed_interview(live_app)
    segment = say(live_app, interview["id"], CROSS_COMPANY_TEXT)
    await extract_and_store_claims(live_app, interview["id"], segment["id"])
    run = completed_run(live_app, interview["id"], [INITIAL_CHECK], status="timeout")

    assert link_run_to_claims(live_app.state.db, interview["id"], run) == []


# --- challenge links ---------------------------------------------------------------


async def test_a_hint_challenges_the_claims_the_candidate_makes_next(live_app):
    interview = seed_interview(live_app)
    stale = say(live_app, interview["id"], "Hint nobody answered yet.", speaker="technical", kind="hint")
    say(live_app, interview["id"], PLAIN_TEXT)
    hint = say(live_app, interview["id"], "Look at the cache key.", speaker="technical", kind="hint")
    answer = say(live_app, interview["id"], CROSS_COMPANY_TEXT)

    [diagnosis] = await extract_and_store_claims(live_app, interview["id"], answer["id"])

    assert link_tuples(live_app, interview["id"]) == [
        ("segment", hint["id"], "challenges", "claim", diagnosis["id"])
    ]
    assert stale["id"] not in {row[1] for row in link_tuples(live_app, interview["id"])}


async def test_the_scenario_notice_challenges_the_answer_to_it(live_app):
    interview = seed_interview(live_app)
    say(live_app, interview["id"], PLAIN_TEXT)
    notice = say(live_app, interview["id"], "An administrator revoked access.",
                 speaker="customer", kind="scenario_notice")
    answer = say(live_app, interview["id"], REVISION_TEXT, stage="changed_condition")

    stored = await extract_and_store_claims(live_app, interview["id"], answer["id"])

    assert stored
    assert link_tuples(live_app, interview["id"]) == [
        ("segment", notice["id"], "challenges", "claim", row["id"]) for row in stored
    ]


async def test_a_hint_before_the_previous_candidate_turn_challenges_nothing(live_app):
    interview = seed_interview(live_app)
    say(live_app, interview["id"], "Look at the cache key.", speaker="technical", kind="hint")
    say(live_app, interview["id"], PLAIN_TEXT)
    say(live_app, interview["id"], "Go on.", speaker="technical")
    answer = say(live_app, interview["id"], CROSS_COMPANY_TEXT)

    await extract_and_store_claims(live_app, interview["id"], answer["id"])

    assert link_tuples(live_app, interview["id"]) == []


async def test_link_challenge_links_only_the_answering_segments_claims_of_the_given_scopes(live_app):
    interview = seed_interview(live_app)
    conn = live_app.state.db
    hint = say(live_app, interview["id"], "Look at the cache key.", speaker="technical", kind="hint")
    answer = say(live_app, interview["id"], "cross company and a test plan")
    later = say(live_app, interview["id"], "a later cross company claim")

    def store(segment, scope, claim_type="diagnosis"):
        return repo.insert_claim(
            conn, id=ids.new_id("clm"), interview_id=interview["id"], segment_id=segment["id"],
            statement=segment["text"], claim_type=claim_type, scope=scope,
            stage="investigation", clarity="clear",
        )

    wanted = store(answer, "cross_company")
    store(answer, "general", "test_plan")
    store(later, "cross_company")

    rows = link_challenge(conn, interview["id"], hint["id"], ["cross_company"])
    again = link_challenge(conn, interview["id"], hint["id"], ["cross_company"])

    assert [row["target_id"] for row in rows] == [wanted["id"]]
    assert again == []
