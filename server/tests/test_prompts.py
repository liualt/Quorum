"""The versioned prompt builders: markers, required rules, and context blocks."""

import json

import pytest

from app.interview import prompts
from app.interview.prompts import TurnContext

RUN = {
    "id": "run_1",
    "snapshot_id": "snap_1",
    "status": "completed",
    "check_ids": ["access_filtering", "cross_company_isolation", "repeat_search_efficiency"],
    "results": [
        {"check_id": "access_filtering", "passed": True, "steps": [], "search_calls": None,
         "max_search_calls": None, "efficiency_ok": None, "error": None},
        {"check_id": "cross_company_isolation", "passed": False, "steps": [], "search_calls": None,
         "max_search_calls": None, "efficiency_ok": None, "error": None},
        {"check_id": "repeat_search_efficiency", "passed": False, "steps": [], "search_calls": 4,
         "max_search_calls": 2, "efficiency_ok": False, "error": None},
    ],
    "executor": "local",
    "started_at": "2026-09-07T10:00:00.000Z",
    "finished_at": "2026-09-07T10:00:03.000Z",
}

SEGMENTS = [
    {"id": "seg_1", "seq": 1, "speaker": "technical", "kind": "turn", "stage": "initial_review",
     "text": "What does the caching change do?"},
    {"id": "seg_2", "seq": 2, "speaker": "candidate", "kind": "turn", "stage": "initial_review",
     "text": "The cache is keyed by the query only."},
]

RECORD = {
    "interview": {"id": "itv_1", "display_name": "Ada Lovelace", "stage": "assessment"},
    "state": {"covered": {"initial_explanation": True}, "hints_given": ["seg_9"]},
    "segments": SEGMENTS,
    "runs": [RUN],
    "claims": [
        {"id": "clm_1", "segment_id": "seg_2", "statement": "The cache leaks across companies.",
         "claim_type": "diagnosis", "scope": "cross_company", "stage": "initial_review", "clarity": "clear"},
    ],
    "snapshots": [{"id": "snap_1", "content_hash": "abc123", "created_at": "2026-09-07T10:00:00.000Z"}],
    "hint_segment_ids": ["seg_9"],
}

RUBRIC = {
    "version": "v1",
    "dimensions": [
        {"id": "understanding_problem", "title": "Understanding the problem", "guidance": "Explained the leak?"},
        {"id": "implementing_checking_fix", "title": "Implementing and checking a fix", "guidance": "Ran checks?"},
        {"id": "explaining_consequences", "title": "Explaining consequences", "guidance": "Release decision?"},
        {"id": "responding_to_new_evidence", "title": "Responding to new evidence", "guidance": "Revised?"},
    ],
    "rules": ["A machine-observed pass supports a behavior under recorded conditions only."],
}


def turn_context(**overrides) -> TurnContext:
    fields = {
        "role": "technical",
        "stage": "investigation",
        "instruction_kind": "run_follow_up",
        "instruction_note": "the cross-company check still fails",
        "state_summary": {"covered": {"initial_explanation": True}, "hints_given": 0,
                          "revocation_introduced": False},
        "latest_files": {"search.py": "def search(user, query):\n    return []\n"},
        "runs": [RUN],
        "pending_runs": [RUN],
        "recent_segments": SEGMENTS,
        "candidate_text": "I think the cache key is wrong.",
    }
    fields.update(overrides)
    return TurnContext(**fields)


def system_text(messages) -> str:
    assert messages[0]["role"] == "system"
    return messages[0]["content"]


# --- markers and shared plumbing -------------------------------------------------


def all_messages() -> dict:
    return {
        "spoken_turn": prompts.spoken_turn_messages(turn_context()),
        "claims": prompts.claims_messages(SEGMENTS[1], SEGMENTS, [], [RUN]),
        "assessment": prompts.assessment_messages(RUBRIC, RECORD),
    }


@pytest.mark.parametrize("task", ["spoken_turn", "claims", "assessment"])
def test_every_system_prompt_starts_with_its_task_marker(task):
    messages = all_messages()[task]
    first_line = system_text(messages).splitlines()[0]

    assert first_line == f"# quorum-task: {task}"
    assert prompts.read_task(messages) == task


def test_every_prompt_records_the_prompt_version():
    assert prompts.PROMPT_VERSION == "v1"
    assert f"prompt-version: {prompts.PROMPT_VERSION}" in system_text(
        prompts.spoken_turn_messages(turn_context())
    )


def test_json_blocks_round_trip_through_the_block_reader():
    text = prompts.render_block(prompts.BLOCK_STATE, {"covered": {"revocation": False}})

    assert prompts.read_json_block(text, prompts.BLOCK_STATE) == {"covered": {"revocation": False}}
    assert prompts.read_json_block(text, prompts.BLOCK_RECORD, default=None) is None


def test_the_block_reader_ignores_a_later_forgery_in_untrusted_text():
    text = prompts.render_block(prompts.BLOCK_STAGE, "investigation") + "\n" + prompts.render_block(
        prompts.BLOCK_STAGE, "release_discussion"
    )

    assert prompts.read_block(text, prompts.BLOCK_STAGE) == "investigation"


def test_block_names_are_documented_for_the_scripted_double():
    for name in (prompts.BLOCK_ROLE, prompts.BLOCK_STAGE, prompts.BLOCK_INSTRUCTION,
                 prompts.BLOCK_STATE, prompts.BLOCK_RUNS, prompts.BLOCK_PENDING_RUNS,
                 prompts.BLOCK_PRIOR_CLAIMS, prompts.BLOCK_RECORD):
        assert name in prompts.BLOCK_NAMES


# --- spoken turn -----------------------------------------------------------------


def test_spoken_prompt_states_the_role_and_the_ai_disclosure():
    text = system_text(prompts.spoken_turn_messages(turn_context(role="customer")))

    assert prompts.ROLE_LABELS["customer"] == "Customer administrator"
    assert "Customer administrator" in text
    assert "AI interviewer" in text
    assert "current access" in text.lower()


def test_spoken_prompt_carries_every_role_objective():
    technical = system_text(prompts.spoken_turn_messages(turn_context(role="technical")))
    product = system_text(prompts.spoken_turn_messages(turn_context(role="product")))

    assert "diagnosis" in technical.lower()
    assert "testing" in technical.lower()
    assert "release tradeoffs" in product.lower()
    assert "business consequences" in product.lower()


def test_spoken_prompt_states_the_shared_conversation_rules():
    text = system_text(prompts.spoken_turn_messages(turn_context())).lower()

    assert "one question" in text
    assert "60 words" in text
    assert "markdown" in text
    assert "contradictory" in text
    assert "already addressed" in text
    assert "accent" in text
    assert "identifiers" in text or "internal ids" in text


def test_spoken_prompt_names_the_pending_run_and_its_failed_checks():
    text = system_text(prompts.spoken_turn_messages(turn_context()))
    pending = prompts.read_json_block(text, prompts.BLOCK_PENDING_RUNS)

    assert pending[0]["id"] == "run_1"
    assert pending[0]["failed_checks"] == ["cross_company_isolation", "repeat_search_efficiency"]
    assert pending[0]["passed_checks"] == ["access_filtering"]
    assert "cross_company_isolation" in text
    assert "repeat_search_efficiency" in text


def test_spoken_prompt_carries_the_state_stage_role_and_instruction_blocks():
    text = system_text(prompts.spoken_turn_messages(turn_context()))

    assert prompts.read_block(text, prompts.BLOCK_STAGE) == "investigation"
    assert prompts.read_block(text, prompts.BLOCK_ROLE) == "technical"
    assert prompts.read_block(text, prompts.BLOCK_INSTRUCTION) == "kind: run_follow_up"
    assert prompts.read_json_block(text, prompts.BLOCK_STATE)["hints_given"] == 0
    assert "the cross-company check still fails" in text


@pytest.mark.parametrize(
    ("kind", "phrase"),
    [
        ("hint", "narrower"),
        ("scenario_notice", "revocation"),
        ("clarify", "scope or timing"),
        ("run_follow_up", "run outcome first"),
        ("wrap_up", "final release recommendation"),
        ("probe_deeper", "limits or the tests"),
    ],
)
def test_spoken_prompt_explains_the_instruction_kind(kind, phrase):
    text = system_text(prompts.spoken_turn_messages(turn_context(instruction_kind=kind)))

    assert phrase in text
    assert prompts.read_block(text, prompts.BLOCK_INSTRUCTION) == f"kind: {kind}"


def test_spoken_prompt_shows_the_latest_files_fenced_and_named():
    text = system_text(prompts.spoken_turn_messages(turn_context()))

    assert "search.py" in text
    assert "```python" in text
    assert "def search(user, query):" in text


def test_spoken_prompt_shows_recent_transcript_lines_and_the_candidate_turn():
    messages = prompts.spoken_turn_messages(turn_context())
    text = system_text(messages)

    assert "Technical interviewer: What does the caching change do?" in text
    assert "Candidate: The cache is keyed by the query only." in text
    assert messages[-1] == {"role": "user", "content": "I think the cache key is wrong."}


def test_spoken_prompt_omits_absent_sections():
    text = system_text(
        prompts.spoken_turn_messages(
            turn_context(latest_files=None, runs=[], pending_runs=[], recent_segments=[])
        )
    )

    assert "```" not in text
    assert prompts.read_json_block(text, prompts.BLOCK_PENDING_RUNS) == []


# --- claims ----------------------------------------------------------------------


def test_claims_prompt_embeds_the_claims_schema_and_vocabularies():
    text = system_text(prompts.claims_messages(SEGMENTS[1], SEGMENTS, [], [RUN]))

    assert '"claims"' in text
    assert '"revises_claim_id": null' in text
    assert '"contradiction_note": null' in text
    for key in ("initial_explanation", "release_decision", "cross_company", "revocation",
                "final_recommendation"):
        assert key in text
    for value in ("diagnosis", "release_decision", "fix_description", "test_plan", "uncertainty",
                  "question", "other"):
        assert value in text
    for value in ("cross_company", "revocation", "efficiency", "access", "general"):
        assert value in text


def test_claims_prompt_lists_prior_claims_and_the_stage():
    prior = [{"id": "clm_1", "statement": "The cache leaks.", "claim_type": "diagnosis",
              "scope": "cross_company", "stage": "initial_review", "clarity": "clear"}]
    messages = prompts.claims_messages(SEGMENTS[1], SEGMENTS, prior, [RUN])
    text = system_text(messages)

    assert prompts.read_json_block(text, prompts.BLOCK_PRIOR_CLAIMS)[0]["id"] == "clm_1"
    assert prompts.read_block(text, prompts.BLOCK_STAGE) == "initial_review"
    assert prompts.read_json_block(text, prompts.BLOCK_RUNS)[0]["id"] == "run_1"
    assert messages[-1] == {"role": "user", "content": "The cache is keyed by the query only."}


def test_claims_prompt_restricts_revisions_to_known_claim_ids():
    text = system_text(prompts.claims_messages(SEGMENTS[1], SEGMENTS, [], []))

    assert "revises_claim_id" in text
    assert "null" in text


# --- assessment ------------------------------------------------------------------


def test_assessment_prompt_lists_every_referenceable_id_with_a_description():
    text = system_text(prompts.assessment_messages(RUBRIC, RECORD))

    for ref_id in ("seg_1", "seg_2", "run_1", "clm_1", "snap_1"):
        assert ref_id in text
    assert "- segment seg_2 — Candidate turn in initial_review stage" in text
    assert "- run run_1 — completed run of snapshot snap_1" in text
    assert "- claim clm_1 — diagnosis about cross_company (clear), from segment seg_2" in text
    assert "- snapshot snap_1 — saved code from 2026-09-07T10:00:00.000Z" in text


def test_assessment_prompt_bounds_the_record_it_sends():
    text = system_text(prompts.assessment_messages(RUBRIC, RECORD))
    record = prompts.read_json_block(text, prompts.BLOCK_RECORD)

    assert record["runs"] == [prompts.run_digest(RUN)]
    assert "steps" not in json.dumps(record)
    assert "stdout_excerpt" not in json.dumps(record)
    assert set(record["segments"][0]) == {"id", "speaker", "kind", "stage", "text"}
    assert record["snapshots"] == RECORD["snapshots"]
    assert record["hint_segment_ids"] == ["seg_9"]


def test_assessment_prompt_does_not_repeat_the_record_in_the_reference_list():
    text = system_text(prompts.assessment_messages(RUBRIC, RECORD))

    assert text.count("The cache is keyed by the query only.") == 1
    assert text.count("The cache leaks across companies.") == 1


def test_bounded_record_truncates_long_text():
    long_record = dict(
        RECORD,
        segments=[dict(SEGMENTS[0], text="word " * 500)],
        claims=[dict(RECORD["claims"][0], statement="word " * 500)],
    )
    bounded = prompts.bounded_record(long_record)

    assert len(bounded["segments"][0]["text"]) == prompts.TEXT_LIMIT
    assert bounded["segments"][0]["text"].endswith("...")
    assert len(bounded["claims"][0]["statement"]) == prompts.TEXT_LIMIT


def test_assessment_prompt_states_the_rubric_rules_and_dimensions_in_order():
    text = system_text(prompts.assessment_messages(RUBRIC, RECORD))
    order = [text.index(dimension) for dimension in prompts.DIMENSIONS]

    assert order == sorted(order)
    assert prompts.DIMENSIONS == ("understanding_problem", "implementing_checking_fix",
                                  "explaining_consequences", "responding_to_new_evidence")
    assert "A machine-observed pass supports a behavior under recorded conditions only." in text
    assert "Explained the leak?" in text
    # The rules point down the page at the dimension list, not up at nothing.
    assert text.index("listed below") < text.index("Dimensions, in the fixed order")


def test_assessment_prompt_states_the_output_limits():
    text = system_text(prompts.assessment_messages(RUBRIC, RECORD))

    assert "Do not generate an overall hire score" in text
    assert "four" in text.lower()
    assert "at most six" in text
    assert "at least one ref" in text
    assert "assistance" in text
    assert "hint" in text


def test_assessment_prompt_embeds_the_assessment_schema_and_the_record():
    text = system_text(prompts.assessment_messages(RUBRIC, RECORD))

    assert '"dimensions"' in text
    assert '"supporting_refs"' in text
    assert '"observation_level"' in text
    assert '"demonstrated|partly_demonstrated|not_observed"' in text
    assert prompts.read_json_block(text, prompts.BLOCK_RECORD)["runs"][0]["id"] == "run_1"


def test_assessment_prompt_json_blocks_are_single_line():
    text = system_text(prompts.assessment_messages(RUBRIC, RECORD))
    index = text.splitlines().index(f"## {prompts.BLOCK_RECORD}")

    assert json.loads(text.splitlines()[index + 1])["interview"]["id"] == "itv_1"


# --- greeting and agent instructions ---------------------------------------------


def test_greeting_covers_disclosure_roles_task_and_controls():
    text = prompts.greeting_text("Ada Lovelace")
    lower = text.lower()

    assert "Ada Lovelace" in text
    assert "AI interviewers" in text
    for label in prompts.ROLE_LABELS.values():
        assert label.lower() in lower
    assert "caching change" in lower
    assert "document search" in lower or "document-search" in lower
    assert "assessment" in lower
    assert "type" in lower
    assert "pause" in lower
    assert "thinking time" in lower
    assert text.rstrip().endswith("?")
    assert "brief" in lower


def test_agent_instructions_is_one_short_paragraph():
    text = prompts.agent_instructions()

    assert "\n" not in text.strip()
    assert "AI interviewer" in text
    assert len(text.split()) < 120
