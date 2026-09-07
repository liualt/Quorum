"""The interview controller: turns, stage and role bookkeeping, interruption,
run follow-ups, and the text routes that drive it.

The app runs with `ScriptedLLM`, whose spoken turns name the speaking role, cite
a pending run, and use fixed sentences for the hint and the scenario notice, so
the assertions below are about what the controller decided, not about prose.
"""

import asyncio
import json

import pytest

from app import ids
from app.interview import controller as controller_module
from app.interview.controller import ENDED_TEXT, RECOVERY_TEXT, InterviewController
from app.interview.llm_client import LLMError
from app.interview.state import ControllerState
from app.storage import repo
from tests.conftest import (
    CHANGED_CHECK,
    INITIAL_CHECK,
    ORIGIN,
    completed_run,
    create_interview,
    drain,
    event_types,
    seed_interview,
)


# --- helpers ---------------------------------------------------------------------


def controller(app) -> InterviewController:
    return app.state.controller


def make_live(app, interview_id: str):
    return repo.update_interview(app.state.db, interview_id, status="live", started_at=ids.now_iso())


def seed_state(app, state: ControllerState):
    """An interview whose controller state (and mirrored columns) is `state`."""
    row = seed_interview(app, state_json=state.to_json())
    return repo.update_interview(
        app.state.db, row["id"], stage=state.stage, active_role=state.active_role
    )


def segments(app, interview_id: str) -> list:
    return repo.list_segments(app.state.db, interview_id)


async def turn(app, interview_id: str, text: str) -> dict:
    return await controller(app).run_turn_collect(interview_id, text, source="candidate")


# --- the first turn --------------------------------------------------------------


async def test_the_first_turn_opens_the_initial_review_with_the_technical_interviewer(live_app):
    interview = seed_interview(live_app)

    result = await turn(live_app, interview["id"], "I have finished reading the brief.")

    assert result["stage"] == "initial_review"
    assert result["role"] == "technical"
    assert "Technical interviewer" in result["text"]
    assert result["segment_id"].startswith("seg_")

    stored = segments(live_app, interview["id"])
    assert [(row["speaker"], row["kind"], row["status"]) for row in stored] == [
        ("candidate", "turn", "complete"),
        ("technical", "turn", "complete"),
    ]
    assert stored[0]["text"] == "I have finished reading the brief."
    assert stored[0]["stage"] == "briefing"
    assert stored[1]["id"] == result["segment_id"]
    assert stored[1]["text"] == result["text"]
    assert stored[1]["stage"] == "initial_review"
    assert stored[0]["generation"] == stored[1]["generation"] == 1

    row = repo.get_interview(live_app.state.db, interview["id"])
    assert row["stage"] == "initial_review"
    assert row["active_role"] == "technical"
    state = controller(live_app).load_state(interview["id"])
    assert state.stage == "initial_review"
    assert state.turns_total == 1
    assert state.candidate_turns_in_stage == 0  # the turn was a briefing turn; counters reset
    assert state.role_turns_in_stage == {"technical": 1}
    assert state.last_candidate_segment_id == stored[0]["id"]
    assert state.last_role_segment_id == stored[1]["id"]
    assert event_types(live_app, interview["id"]) == [
        "transcript_segment",
        "stage_changed",
        "transcript_segment",
    ]


async def test_a_finished_interview_only_says_goodbye(live_app):
    interview = seed_interview(live_app)
    repo.update_interview(live_app.state.db, interview["id"], status="finished")

    result = await turn(live_app, interview["id"], "One more thing.")

    assert result == {"segment_id": None, "role": "technical", "text": ENDED_TEXT, "stage": "briefing"}
    assert segments(live_app, interview["id"]) == []


async def test_a_turn_streams_in_pieces(live_app):
    interview = seed_interview(live_app)

    chunks = [
        chunk
        async for chunk in controller(live_app).run_turn(interview["id"], "Done reading.", source="candidate")
    ]

    assert len(chunks) > 3
    assert "Technical interviewer" in "".join(chunks)


# --- runs ------------------------------------------------------------------------


async def test_a_completed_run_is_raised_on_the_next_turn(live_app):
    interview = seed_interview(live_app)
    await turn(live_app, interview["id"], "The cache is keyed by the query only.")
    run = completed_run(live_app, interview["id"], [INITIAL_CHECK])

    await controller(live_app).on_run_completed(interview["id"], run["id"])
    state = controller(live_app).load_state(interview["id"])
    assert state.pending_run_ids == [run["id"]]

    result = await turn(live_app, interview["id"], "I ran the isolation check.")

    assert "your latest run" in result["text"]
    assert INITIAL_CHECK in result["text"]
    state = controller(live_app).load_state(interview["id"])
    assert state.pending_run_ids == []
    assert state.discussed_run_ids == [run["id"]]


async def test_a_replay_is_never_raised_with_the_candidate(live_app):
    interview = seed_interview(live_app)
    original = completed_run(live_app, interview["id"], [INITIAL_CHECK])
    replay = completed_run(live_app, interview["id"], [INITIAL_CHECK], replay_of=original["id"])

    await controller(live_app).on_run_completed(interview["id"], replay["id"])

    assert controller(live_app).load_state(interview["id"]).pending_run_ids == []


async def test_on_run_completed_hands_the_run_to_the_evidence_linker(live_app):
    interview = seed_interview(live_app)
    run = completed_run(live_app, interview["id"], [INITIAL_CHECK])
    linked = []
    live_app.state.link_run = lambda interview_id, row: linked.append((interview_id, row["id"]))

    await controller(live_app).on_run_completed(interview["id"], run["id"])

    assert linked == [(interview["id"], run["id"])]


async def test_facts_come_from_the_rows(live_app):
    interview = seed_interview(live_app)
    assert controller(live_app).facts(interview["id"]).elapsed_minutes == 0.0

    make_live(live_app, interview["id"])
    completed_run(live_app, interview["id"], [INITIAL_CHECK], {INITIAL_CHECK: False})
    completed_run(live_app, interview["id"], [INITIAL_CHECK], status="timeout")
    completed_run(live_app, interview["id"], [INITIAL_CHECK, CHANGED_CHECK], {INITIAL_CHECK: True})

    facts = controller(live_app).facts(interview["id"])

    assert facts.completed_runs == 2
    assert facts.revocation_run_completed is True
    assert facts.latest_run_passed == {INITIAL_CHECK: True, CHANGED_CHECK: False}
    assert facts.latest_run_id == repo.list_runs(live_app.state.db, interview["id"])[-1]["id"]
    assert facts.pending_check_ids == []
    assert 0.0 <= facts.elapsed_minutes < 1.0


async def test_pending_check_ids_follow_the_newest_pending_run(live_app):
    interview = seed_interview(live_app)
    passing = completed_run(live_app, interview["id"], [INITIAL_CHECK], {INITIAL_CHECK: True})
    timed_out = completed_run(live_app, interview["id"], [CHANGED_CHECK], status="timeout")
    await controller(live_app).on_run_completed(interview["id"], passing["id"])
    await controller(live_app).on_run_completed(interview["id"], timed_out["id"])

    facts = controller(live_app).facts(interview["id"])

    assert facts.latest_run_id == passing["id"]
    assert facts.latest_run_passed == {INITIAL_CHECK: True}
    assert facts.pending_check_ids == [CHANGED_CHECK]


# --- interruption ----------------------------------------------------------------


async def test_a_newer_turn_interrupts_the_one_still_streaming(live_app):
    interview = seed_interview(live_app)
    first = controller(live_app).run_turn(interview["id"], "Let me think aloud.", source="candidate")
    first_chunk = await anext(first)
    assert first_chunk

    second = await turn(live_app, interview["id"], "Actually, the cache key is the problem.")
    rest = [chunk async for chunk in first]

    assert rest == []
    stored = segments(live_app, interview["id"])
    by_status = {row["id"]: row["status"] for row in stored if row["speaker"] != "candidate"}
    interrupted = [row for row in stored if row["status"] == "interrupted"]
    assert len(interrupted) == 1
    assert interrupted[0]["text"] == first_chunk
    assert interrupted[0]["generation"] == 1
    assert by_status[second["segment_id"]] == "complete"
    assert repo.get_segment(live_app.state.db, second["segment_id"])["generation"] == 2
    assert controller(live_app).current_generation(interview["id"]) == 2


async def test_an_abandoned_stream_is_recorded_as_interrupted(live_app):
    interview = seed_interview(live_app)
    stream = controller(live_app).run_turn(interview["id"], "Done reading.", source="candidate")
    first_chunk = await anext(stream)

    await stream.aclose()

    role_rows = [row for row in segments(live_app, interview["id"]) if row["speaker"] != "candidate"]
    assert [(row["status"], row["text"]) for row in role_rows] == [("interrupted", first_chunk)]


# --- hints and the scenario notice -----------------------------------------------


async def test_a_stuck_candidate_gets_a_recorded_hint(live_app):
    interview = seed_state(live_app, ControllerState(stage="initial_review", candidate_turns_in_stage=1))

    result = await turn(live_app, interview["id"], "I am not sure what to look at.")

    assert result["text"].startswith("Here is a narrower question:")
    row = repo.get_segment(live_app.state.db, result["segment_id"])
    assert row["kind"] == "hint"
    state = controller(live_app).load_state(interview["id"])
    assert state.hints_given == [result["segment_id"]]
    assert state.hints_in_stage == 1


async def test_the_scenario_notice_unlocks_the_revocation_check(live_app):
    interview = seed_state(live_app, ControllerState(stage="investigation", candidate_turns_in_stage=5))
    assert CHANGED_CHECK not in controller(live_app).allowed_check_ids(interview["id"])

    result = await turn(live_app, interview["id"], "I would ship it.")

    assert result["stage"] == "changed_condition"
    assert result["role"] == "customer"
    assert result["text"].startswith("Customer administrator here.")
    row = repo.get_segment(live_app.state.db, result["segment_id"])
    assert row["kind"] == "scenario_notice"

    state = controller(live_app).load_state(interview["id"])
    assert state.revocation_introduced is True
    assert state.revocation_segment_id == result["segment_id"]
    assert CHANGED_CHECK in controller(live_app).allowed_check_ids(interview["id"])
    assert repo.get_interview(live_app.state.db, interview["id"])["active_role"] == "customer"

    events = repo.list_events(live_app.state.db, interview["id"], 0)
    assert [event["type"] for event in events] == [
        "transcript_segment",
        "stage_changed",
        "role_changed",
        "transcript_segment",
        "scenario_notice",
    ]
    assert events[1]["payload"] == {"stage": "changed_condition"}
    assert events[2]["payload"] == {"role": "customer"}
    assert events[4]["payload"] == {
        "segment_id": result["segment_id"],
        "text": result["text"],
        "checks_unlocked": [CHANGED_CHECK],
    }


async def test_a_clarification_consumes_the_contradiction_note(live_app):
    interview = seed_state(
        live_app,
        ControllerState(stage="investigation", candidate_turns_in_stage=1,
                        contradiction_note="earlier they said the cache was per user",
                        last_clarity="vague"),
    )

    result = await turn(live_app, interview["id"], "Maybe it is per company.")

    assert "clarify" in result["text"]
    assert repo.get_segment(live_app.state.db, result["segment_id"])["kind"] == "clarification"
    state = controller(live_app).load_state(interview["id"])
    assert state.contradiction_note is None
    assert state.last_clarity == "clear"


# --- the proactive follow-up -----------------------------------------------------


async def test_a_quiet_candidate_hears_about_the_run(live_app):
    live_app.state.settings.FOLLOW_UP_DELAY_SECONDS = 0.05
    interview = seed_state(live_app, ControllerState(stage="investigation", candidate_turns_in_stage=1))
    make_live(live_app, interview["id"])
    run = completed_run(live_app, interview["id"], [INITIAL_CHECK])

    await controller(live_app).on_run_completed(interview["id"], run["id"])
    await drain(live_app)

    rows = segments(live_app, interview["id"])
    assert [(row["speaker"], row["kind"], row["status"]) for row in rows] == [
        ("technical", "follow_up", "complete")
    ]
    assert "your latest run" in rows[0]["text"]
    state = controller(live_app).load_state(interview["id"])
    assert state.pending_run_ids == []
    assert state.discussed_run_ids == [run["id"]]
    assert state.candidate_turns_in_stage == 1
    assert state.turns_total == 0
    assert state.role_turns_in_stage == {"technical": 1}
    assert state.generation == 1


async def test_the_follow_up_yields_to_a_candidate_who_spoke_first(live_app):
    live_app.state.settings.FOLLOW_UP_DELAY_SECONDS = 0.05
    interview = seed_state(live_app, ControllerState(stage="investigation", candidate_turns_in_stage=1))
    make_live(live_app, interview["id"])
    run = completed_run(live_app, interview["id"], [INITIAL_CHECK])

    await controller(live_app).on_run_completed(interview["id"], run["id"])
    await turn(live_app, interview["id"], "The run failed, so the key is still shared.")
    await drain(live_app)

    rows = segments(live_app, interview["id"])
    assert [(row["speaker"], row["kind"]) for row in rows] == [("candidate", "turn"), ("technical", "follow_up")]
    assert "your latest run" in rows[1]["text"]
    assert controller(live_app).load_state(interview["id"]).generation == 1


async def test_the_follow_up_waits_while_the_interview_is_paused(live_app):
    live_app.state.settings.FOLLOW_UP_DELAY_SECONDS = 0.05
    interview = seed_state(live_app, ControllerState(stage="investigation", candidate_turns_in_stage=1))
    make_live(live_app, interview["id"])
    repo.update_interview(live_app.state.db, interview["id"], paused=1, paused_at=ids.now_iso())
    run = completed_run(live_app, interview["id"], [INITIAL_CHECK])

    await controller(live_app).on_run_completed(interview["id"], run["id"])
    await drain(live_app)

    assert segments(live_app, interview["id"]) == []
    assert controller(live_app).load_state(interview["id"]).pending_run_ids == [run["id"]]


async def test_the_follow_up_is_spoken_through_the_voice_agent(live_app):
    live_app.state.settings.FOLLOW_UP_DELAY_SECONDS = 0.05
    spoken = []

    class StubVoice:
        enabled = True

        async def say(self, agent_id, text, *, interrupt=False):
            spoken.append((agent_id, text))

    live_app.state.voice = StubVoice()
    interview = seed_state(live_app, ControllerState(stage="investigation", candidate_turns_in_stage=1))
    make_live(live_app, interview["id"])
    repo.update_interview(live_app.state.db, interview["id"], agora_agent_id="agent_1")
    run = completed_run(live_app, interview["id"], [INITIAL_CHECK])

    await controller(live_app).on_run_completed(interview["id"], run["id"])
    await drain(live_app)

    rows = segments(live_app, interview["id"])
    assert spoken == [("agent_1", rows[0]["text"])]


@pytest.fixture
def held_stream(live_app, monkeypatch):
    """A model whose first chunk arrives at once and whose rest waits on `release`."""
    release = asyncio.Event()

    async def slow_stream(messages, **kwargs):
        yield "Technical"
        await release.wait()
        yield " interviewer here. What would you check next?"

    monkeypatch.setattr(live_app.state.llm, "stream_text", slow_stream)
    return release


async def test_the_follow_up_waits_for_the_panel_to_finish_speaking(live_app, held_stream, monkeypatch):
    live_app.state.settings.FOLLOW_UP_DELAY_SECONDS = 0.05
    monkeypatch.setattr(controller_module, "FOLLOW_UP_ATTEMPTS", 1000)  # patience, not the bound
    interview = seed_state(live_app, ControllerState(stage="investigation", candidate_turns_in_stage=1))
    make_live(live_app, interview["id"])
    stream = controller(live_app).run_turn(interview["id"], "Let me run it.", source="candidate")
    assert await anext(stream) == "Technical"
    run = completed_run(live_app, interview["id"], [INITIAL_CHECK])

    await controller(live_app).on_run_completed(interview["id"], run["id"])
    await asyncio.sleep(0.15)  # the delay expires while the panel is mid-sentence

    assert [row["speaker"] for row in segments(live_app, interview["id"])] == ["candidate"]
    assert controller(live_app).current_generation(interview["id"]) == 1

    held_stream.set()
    rest = "".join([chunk async for chunk in stream])
    await drain(live_app)

    rows = segments(live_app, interview["id"])
    assert [(row["speaker"], row["kind"], row["status"]) for row in rows] == [
        ("candidate", "turn", "complete"),
        ("technical", "turn", "complete"),
        ("technical", "follow_up", "complete"),
    ]
    assert rows[1]["text"] == "Technical" + rest
    assert (rows[1]["generation"], rows[2]["generation"]) == (1, 2)
    assert controller(live_app).load_state(interview["id"]).discussed_run_ids == [run["id"]]


async def test_the_follow_up_gives_up_after_its_attempts_and_leaves_the_run_pending(
    live_app, held_stream, monkeypatch, caplog
):
    live_app.state.settings.FOLLOW_UP_DELAY_SECONDS = 0.05
    monkeypatch.setattr(controller_module, "FOLLOW_UP_ATTEMPTS", 1)
    interview = seed_state(live_app, ControllerState(stage="investigation", candidate_turns_in_stage=1))
    make_live(live_app, interview["id"])
    stream = controller(live_app).run_turn(interview["id"], "Let me run it.", source="candidate")
    await anext(stream)
    run = completed_run(live_app, interview["id"], [INITIAL_CHECK])

    await controller(live_app).on_run_completed(interview["id"], run["id"])
    with caplog.at_level("INFO"):
        await drain(live_app)
    held_stream.set()
    [chunk async for chunk in stream]

    assert "leaving it pending" in caplog.text
    assert controller(live_app).load_state(interview["id"]).pending_run_ids == [run["id"]]
    assert [(row["kind"], row["status"]) for row in segments(live_app, interview["id"])] == [
        ("turn", "complete"),
        ("turn", "complete"),
    ]


async def test_a_failing_follow_up_is_logged_not_raised(live_app, monkeypatch, caplog):
    live_app.state.settings.FOLLOW_UP_DELAY_SECONDS = 0.05
    interview = seed_state(live_app, ControllerState(stage="investigation", candidate_turns_in_stage=1))
    make_live(live_app, interview["id"])
    run = completed_run(live_app, interview["id"], [INITIAL_CHECK])

    async def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(controller(live_app), "run_turn_collect", explode)

    await controller(live_app).on_run_completed(interview["id"], run["id"])
    with caplog.at_level("ERROR"):
        await drain(live_app)

    assert "boom" in caplog.text


# --- model failure ---------------------------------------------------------------


async def test_a_model_failure_speaks_the_fixed_sentence_and_records_it_pending(live_app, monkeypatch):
    interview = seed_interview(live_app)

    async def failing(messages, **kwargs):
        raise LLMError("upstream down")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(live_app.state.llm, "stream_text", failing)

    result = await turn(live_app, interview["id"], "Done reading.")

    assert result["text"] == RECOVERY_TEXT
    row = repo.get_segment(live_app.state.db, result["segment_id"])
    assert row["status"] == "pending"
    assert row["text"] == RECOVERY_TEXT
    assert row["speaker"] == "technical"
    state = controller(live_app).load_state(interview["id"])
    assert state.role_turns_in_stage == {}
    assert state.stage == "initial_review"


async def test_a_model_failure_mid_stream_keeps_what_was_already_said(live_app, monkeypatch):
    interview = seed_interview(live_app)

    async def failing_after_one(messages, **kwargs):
        yield "Technical"
        raise LLMError("upstream down")

    monkeypatch.setattr(live_app.state.llm, "stream_text", failing_after_one)

    result = await turn(live_app, interview["id"], "Done reading.")

    assert result["text"] == f"Technical {RECOVERY_TEXT}"
    row = repo.get_segment(live_app.state.db, result["segment_id"])
    assert row["status"] == "pending"
    assert row["text"] == result["text"]


# --- claims extraction hook ------------------------------------------------------


async def test_a_candidate_segment_is_handed_to_the_claims_extractor(live_app):
    interview = seed_interview(live_app)
    extracted = []

    async def extractor(app, interview_id, segment_id):
        extracted.append((interview_id, segment_id))

    live_app.state.claims_extractor = extractor

    await turn(live_app, interview["id"], "The cache leaks across companies.")
    await drain(live_app)

    state = controller(live_app).load_state(interview["id"])
    assert extracted == [(interview["id"], state.last_candidate_segment_id)]


# --- transcript status -----------------------------------------------------------


async def test_the_browser_can_mark_the_latest_role_segment_interrupted(live_app):
    interview = seed_interview(live_app)
    result = await turn(live_app, interview["id"], "Done reading.")
    heard = " ".join(result["text"].split(" ")[:3])

    segment_id = await controller(live_app).apply_transcript_status(
        interview["id"], speaker="agent", status="interrupted", text=heard, turn_id=1
    )

    assert segment_id == result["segment_id"]
    row = repo.get_segment(live_app.state.db, segment_id)
    assert row["status"] == "interrupted"
    assert row["spoken_text"] == heard
    assert row["text"] == result["text"]
    assert event_types(live_app, interview["id"])[-1] == "segment_updated"


async def test_an_ended_agent_turn_stays_complete(live_app):
    interview = seed_interview(live_app)
    result = await turn(live_app, interview["id"], "Done reading.")

    segment_id = await controller(live_app).apply_transcript_status(
        interview["id"], speaker="agent", status="end", text=result["text"].upper(), turn_id=1
    )

    assert segment_id == result["segment_id"]
    row = repo.get_segment(live_app.state.db, segment_id)
    assert row["status"] == "complete"
    assert row["spoken_text"] == result["text"].upper()


async def test_candidate_transcript_status_is_ignored(live_app):
    interview = seed_interview(live_app)
    await turn(live_app, interview["id"], "Done reading.")

    assert await controller(live_app).apply_transcript_status(
        interview["id"], speaker="candidate", status="end", text="Done reading.", turn_id=1
    ) is None


async def test_an_unmatched_agent_transcript_is_ignored(live_app):
    interview = seed_interview(live_app)
    await turn(live_app, interview["id"], "Done reading.")

    assert await controller(live_app).apply_transcript_status(
        interview["id"], speaker="agent", status="end", text="Something never said", turn_id=1
    ) is None


# --- the text routes -------------------------------------------------------------


def test_post_turns_answers_with_the_role_segment(client, app, candidate):
    response = client.post(
        f"/api/interviews/{candidate['id']}/turns", json={"text": "Done reading."}, headers=ORIGIN
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stage"] == "initial_review"
    assert body["role"] == "technical"
    assert "Technical interviewer" in body["text"]
    assert repo.get_segment(app.state.db, body["segment_id"])["text"] == body["text"]

    view = client.get(f"/api/interviews/{candidate['id']}").json()
    assert view["stage"] == "initial_review"


def test_post_turns_rejects_blank_text(client, candidate):
    response = client.post(
        f"/api/interviews/{candidate['id']}/turns", json={"text": "   "}, headers=ORIGIN
    )

    assert response.status_code == 400


def test_post_turns_needs_the_candidate_cookie_and_the_origin(client, candidate):
    without_origin = client.post(f"/api/interviews/{candidate['id']}/turns", json={"text": "hi"})
    assert without_origin.status_code == 403

    other = create_interview(client)  # the cookie now belongs to `other`
    wrong_interview = client.post(
        f"/api/interviews/{candidate['id']}/turns", json={"text": "hi"}, headers=ORIGIN
    )
    assert wrong_interview.status_code == 403
    assert other["id"] != candidate["id"]


def test_post_transcript_updates_the_role_segment(client, app, candidate):
    spoken = client.post(
        f"/api/interviews/{candidate['id']}/turns", json={"text": "Done reading."}, headers=ORIGIN
    ).json()

    response = client.post(
        f"/api/interviews/{candidate['id']}/transcript",
        json={"speaker": "agent", "status": "interrupted", "text": spoken["text"][:20], "turn_id": 1},
        headers=ORIGIN,
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"segment_id": spoken["segment_id"]}
    assert repo.get_segment(app.state.db, spoken["segment_id"])["status"] == "interrupted"


def test_post_transcript_for_the_candidate_answers_null(client, candidate):
    response = client.post(
        f"/api/interviews/{candidate['id']}/transcript",
        json={"speaker": "candidate", "status": "end", "text": "hello", "turn_id": 1},
        headers=ORIGIN,
    )

    assert response.status_code == 200
    assert response.json() == {"segment_id": None}


def test_a_new_interview_starts_from_the_controller_state(client, app, candidate):
    row = repo.get_interview(app.state.db, candidate["id"])

    assert ControllerState.from_json(row["state_json"]) == ControllerState()
    assert json.loads(row["state_json"])["stage"] == "briefing"


@pytest.mark.parametrize("status", ["finishing", "finished"])
def test_post_turns_after_the_interview_ended_only_says_goodbye(client, app, candidate, status):
    repo.update_interview(app.state.db, candidate["id"], status=status)

    response = client.post(
        f"/api/interviews/{candidate['id']}/turns", json={"text": "hello"}, headers=ORIGIN
    )

    assert response.status_code == 200
    assert response.json()["text"] == ENDED_TEXT
    assert response.json()["segment_id"] is None
