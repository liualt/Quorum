"""Which of the three roles speaks next, and with what instruction.

A pure function of state and facts: application code owns every switch of
speaker (PRD section 9: one speech controller, roles change instructions and
the visible label, never add a second voice). Clarifications come first because
an ambiguous answer must be resolved before anyone builds on it.
"""

from dataclasses import dataclass

from app.interview.stages import Facts
from app.interview.state import ControllerState

ISOLATION_CHECK = "cross_company_isolation"
REVOCATION_CHECK = "revocation_next_request"

CACHE_KEY_HINT = (
    "The cache key is worth a close look. What does it include, and who else could share it?"
)
PRODUCT_RUN_NOTE = (
    "Ask whether they would ship the slower safe version today and what they would tell the team"
)
NEXT_CHECKS_NOTE = "ask for the next checks they would add"

# How often the customer may follow up revocation runs in the changed-condition stage.
CUSTOMER_FOLLOW_UP_LIMIT = 2


@dataclass(frozen=True)
class TurnInstruction:
    kind: str  # normal | hint | scenario_notice | clarify | run_follow_up | wrap_up | probe_deeper
    note: str = ""


NORMAL = TurnInstruction("normal")


def select_role(state: ControllerState, facts: Facts) -> tuple[str, TurnInstruction]:
    if state.contradiction_note:
        return state.active_role, TurnInstruction("clarify", state.contradiction_note)
    if state.last_clarity == "vague":
        return state.active_role, TurnInstruction("clarify")

    selector = _BY_STAGE.get(state.stage)
    return selector(state, facts) if selector else ("technical", NORMAL)


def _initial_review(state: ControllerState, facts: Facts) -> tuple[str, TurnInstruction]:
    if state.candidate_turns_in_stage >= 2 and not state.covered["cross_company"]:
        return "technical", TurnInstruction("hint", CACHE_KEY_HINT)
    return "technical", NORMAL


def _investigation(state: ControllerState, facts: Facts) -> tuple[str, TurnInstruction]:
    covered = state.covered
    if state.pending_run_ids:
        product_silent = state.role_turns_in_stage.get("product", 0) == 0
        # The pass must belong to the run being raised now, not to an older one.
        isolation_passed = (
            facts.latest_run_id == state.pending_run_ids[-1]
            and facts.latest_run_passed.get(ISOLATION_CHECK) is True
        )
        if product_silent and isolation_passed:
            return "product", TurnInstruction("run_follow_up", PRODUCT_RUN_NOTE)
        return "technical", TurnInstruction("run_follow_up")
    if covered["cross_company"] and covered["revocation"] and not state.revocation_introduced:
        return "technical", TurnInstruction("probe_deeper")
    stuck = state.candidate_turns_in_stage >= 3 and not covered["cross_company"]
    if stuck and state.hints_in_stage == 0:
        return "technical", TurnInstruction("hint", CACHE_KEY_HINT)
    return "technical", NORMAL


def _changed_condition(state: ControllerState, facts: Facts) -> tuple[str, TurnInstruction]:
    if not state.revocation_introduced:
        return "customer", TurnInstruction("scenario_notice")
    if state.pending_run_ids:
        revocation_run = REVOCATION_CHECK in facts.pending_check_ids
        customer_turns = state.role_turns_in_stage.get("customer", 0)
        if revocation_run and customer_turns < CUSTOMER_FOLLOW_UP_LIMIT:
            return "customer", TurnInstruction("run_follow_up")
        return "technical", TurnInstruction("run_follow_up")
    return "technical", NORMAL


def _release_discussion(state: ControllerState, facts: Facts) -> tuple[str, TurnInstruction]:
    if not state.covered["final_recommendation"]:
        return "product", TurnInstruction("wrap_up")
    return "technical", TurnInstruction("normal", NEXT_CHECKS_NOTE)


_BY_STAGE = {
    "initial_review": _initial_review,
    "investigation": _investigation,
    "changed_condition": _changed_condition,
    "release_discussion": _release_discussion,
}
