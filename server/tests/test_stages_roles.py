"""The pure interview rules: which stage comes next, and who speaks with what instruction.

Both functions take the persisted controller state plus a few database-derived
facts, so every rule in the brief is pinned here as a table row.
"""

import pytest

from app.interview.roles import TurnInstruction, select_role
from app.interview.stages import STAGES, Facts, next_stage
from app.interview.state import ControllerState


def state(**overrides) -> ControllerState:
    covered = overrides.pop("covered", {})
    built = ControllerState(**overrides)
    built.covered.update(covered)
    return built


def facts(**overrides) -> Facts:
    fields = {
        "completed_runs": 0,
        "revocation_run_completed": False,
        "elapsed_minutes": 0.0,
        "latest_run_passed": {},
    }
    fields.update(overrides)
    return Facts(**fields)


# --- next_stage ------------------------------------------------------------------

STAGE_CASES = [
    ("briefing waits for a candidate turn", state(stage="briefing"), facts(), "briefing"),
    (
        "the first candidate turn opens the initial review",
        state(stage="briefing", candidate_turns_in_stage=1),
        facts(),
        "initial_review",
    ),
    (
        "explanation plus release decision opens the investigation",
        state(
            stage="initial_review",
            candidate_turns_in_stage=1,
            covered={"initial_explanation": True, "release_decision": True},
        ),
        facts(),
        "investigation",
    ),
    (
        "an explanation without a decision keeps reviewing",
        state(stage="initial_review", candidate_turns_in_stage=2, covered={"initial_explanation": True}),
        facts(),
        "initial_review",
    ),
    (
        "three review turns move on regardless",
        state(stage="initial_review", candidate_turns_in_stage=3),
        facts(),
        "investigation",
    ),
    (
        "a completed run, two turns, and nothing pending introduces the changed condition",
        state(stage="investigation", candidate_turns_in_stage=2),
        facts(completed_runs=1),
        "changed_condition",
    ),
    (
        "a pending run holds the investigation",
        state(stage="investigation", candidate_turns_in_stage=2, pending_run_ids=["run_1"]),
        facts(completed_runs=1),
        "investigation",
    ),
    (
        "a completed run with only one turn holds the investigation",
        state(stage="investigation", candidate_turns_in_stage=1),
        facts(completed_runs=1),
        "investigation",
    ),
    (
        "six investigation turns move on without a run",
        state(stage="investigation", candidate_turns_in_stage=6),
        facts(),
        "changed_condition",
    ),
    (
        "twelve minutes move the investigation on",
        state(stage="investigation", candidate_turns_in_stage=1),
        facts(elapsed_minutes=12.0),
        "changed_condition",
    ),
    (
        "under twelve minutes and no run keeps investigating",
        state(stage="investigation", candidate_turns_in_stage=5),
        facts(elapsed_minutes=11.9),
        "investigation",
    ),
    (
        "a revocation run after the notice and one turn opens the release discussion",
        state(stage="changed_condition", candidate_turns_in_stage=1, revocation_introduced=True),
        facts(revocation_run_completed=True),
        "release_discussion",
    ),
    (
        "a revocation run before any turn holds the changed condition",
        state(stage="changed_condition", candidate_turns_in_stage=0, revocation_introduced=True),
        facts(revocation_run_completed=True),
        "changed_condition",
    ),
    (
        "four changed-condition turns move on without the run",
        state(stage="changed_condition", candidate_turns_in_stage=4, revocation_introduced=True),
        facts(),
        "release_discussion",
    ),
    (
        "eighteen minutes move the changed condition on",
        state(stage="changed_condition", candidate_turns_in_stage=1, revocation_introduced=True),
        facts(elapsed_minutes=18.0),
        "release_discussion",
    ),
    (
        "the release discussion lasts until finish",
        state(stage="release_discussion", candidate_turns_in_stage=9),
        facts(elapsed_minutes=40.0, completed_runs=5, revocation_run_completed=True),
        "release_discussion",
    ),
    (
        "assessment is terminal",
        state(stage="assessment", candidate_turns_in_stage=1),
        facts(),
        "assessment",
    ),
]


@pytest.mark.parametrize(
    ("current", "known", "expected"),
    [case[1:] for case in STAGE_CASES],
    ids=[case[0] for case in STAGE_CASES],
)
def test_next_stage(current, known, expected):
    assert next_stage(current, known) == expected


def test_stages_are_listed_in_interview_order():
    assert STAGES == [
        "briefing",
        "initial_review",
        "investigation",
        "changed_condition",
        "release_discussion",
        "assessment",
    ]


# --- select_role -----------------------------------------------------------------

PASSING_ISOLATION = {"access_filtering": True, "cross_company_isolation": True}

ROLE_CASES = [
    (
        "a contradiction note keeps the current role and asks for clarification",
        state(stage="investigation", active_role="product", contradiction_note="scope changed"),
        facts(),
        ("product", "clarify", "scope changed"),
    ),
    (
        "a vague answer keeps the current role and asks for clarification",
        state(stage="changed_condition", active_role="customer", last_clarity="vague",
              revocation_introduced=True),
        facts(),
        ("customer", "clarify", ""),
    ),
    (
        "the initial review is the technical interviewer's",
        state(stage="initial_review", candidate_turns_in_stage=1),
        facts(),
        ("technical", "normal", ""),
    ),
    (
        "two review turns without the cross-company finding earn a hint",
        state(stage="initial_review", candidate_turns_in_stage=2),
        facts(),
        ("technical", "hint", "cache key"),
    ),
    (
        "two review turns with the finding get a normal question",
        state(stage="initial_review", candidate_turns_in_stage=2, covered={"cross_company": True}),
        facts(),
        ("technical", "normal", ""),
    ),
    (
        "a pending run is followed up by the technical interviewer",
        state(stage="investigation", pending_run_ids=["run_1"]),
        facts(latest_run_passed={"cross_company_isolation": False}),
        ("technical", "run_follow_up", ""),
    ),
    (
        "the product manager interjects once after a passing isolation run",
        state(stage="investigation", pending_run_ids=["run_1"]),
        facts(latest_run_passed=PASSING_ISOLATION),
        ("product", "run_follow_up", "slower safe version"),
    ),
    (
        "the product manager does not interject twice in a stage",
        state(stage="investigation", pending_run_ids=["run_2"], role_turns_in_stage={"product": 1}),
        facts(latest_run_passed=PASSING_ISOLATION),
        ("technical", "run_follow_up", ""),
    ),
    (
        "both issues found early means probing limits, not repeating the bug",
        state(stage="investigation", covered={"cross_company": True, "revocation": True}),
        facts(),
        ("technical", "probe_deeper", ""),
    ),
    (
        "both issues found after the notice is a normal turn",
        state(stage="investigation", covered={"cross_company": True, "revocation": True},
              revocation_introduced=True),
        facts(),
        ("technical", "normal", ""),
    ),
    (
        "three investigation turns without the finding earn a hint",
        state(stage="investigation", candidate_turns_in_stage=3),
        facts(),
        ("technical", "hint", "cache key"),
    ),
    (
        "one hint per investigation stage",
        state(stage="investigation", candidate_turns_in_stage=4, hints_in_stage=1),
        facts(),
        ("technical", "normal", ""),
    ),
    (
        "the investigation otherwise goes on normally",
        state(stage="investigation", candidate_turns_in_stage=1),
        facts(),
        ("technical", "normal", ""),
    ),
    (
        "the changed condition opens with the customer's notice",
        state(stage="changed_condition"),
        facts(),
        ("customer", "scenario_notice", ""),
    ),
    (
        "the customer follows up a revocation run",
        state(stage="changed_condition", revocation_introduced=True, pending_run_ids=["run_3"]),
        facts(latest_run_passed={"revocation_next_request": False}),
        ("customer", "run_follow_up", ""),
    ),
    (
        "the customer follows up at most twice",
        state(stage="changed_condition", revocation_introduced=True, pending_run_ids=["run_4"],
              role_turns_in_stage={"customer": 2}),
        facts(latest_run_passed={"revocation_next_request": True}),
        ("technical", "run_follow_up", ""),
    ),
    (
        "a run without the revocation check goes to the technical interviewer",
        state(stage="changed_condition", revocation_introduced=True, pending_run_ids=["run_5"]),
        facts(latest_run_passed={"cross_company_isolation": True}),
        ("technical", "run_follow_up", ""),
    ),
    (
        "the changed condition otherwise goes on normally",
        state(stage="changed_condition", revocation_introduced=True, candidate_turns_in_stage=2),
        facts(),
        ("technical", "normal", ""),
    ),
    (
        "the release discussion opens with the product manager's wrap-up",
        state(stage="release_discussion"),
        facts(),
        ("product", "wrap_up", ""),
    ),
    (
        "after the recommendation the technical interviewer asks for next checks",
        state(stage="release_discussion", covered={"final_recommendation": True}),
        facts(),
        ("technical", "normal", "next checks"),
    ),
]


@pytest.mark.parametrize(
    ("current", "known", "expected"),
    [case[1:] for case in ROLE_CASES],
    ids=[case[0] for case in ROLE_CASES],
)
def test_select_role(current, known, expected):
    role, instruction = select_role(current, known)
    expected_role, expected_kind, note_fragment = expected

    assert isinstance(instruction, TurnInstruction)
    assert (role, instruction.kind) == (expected_role, expected_kind)
    if note_fragment:
        assert note_fragment in instruction.note
    else:
        assert instruction.note == ""


# --- state JSON ------------------------------------------------------------------


def test_state_round_trips_through_json():
    original = state(
        stage="investigation",
        generation=4,
        covered={"cross_company": True},
        hints_given=["seg_1"],
        pending_run_ids=["run_1"],
        role_turns_in_stage={"technical": 2},
    )

    restored = ControllerState.from_json(original.to_json())

    assert restored == original


def test_state_reads_an_empty_or_partial_document_as_defaults():
    assert ControllerState.from_json(None) == ControllerState()
    assert ControllerState.from_json("{}") == ControllerState()

    partial = ControllerState.from_json('{"revocation_introduced": true, "covered": {"revocation": true}}')

    assert partial.revocation_introduced is True
    assert partial.covered["revocation"] is True
    assert partial.covered["cross_company"] is False
    assert partial.stage == "briefing"


def test_state_ignores_keys_it_does_not_know():
    assert ControllerState.from_json('{"future_field": 1}') == ControllerState()
