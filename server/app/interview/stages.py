"""Which interview stage comes next. A pure function of state and a few facts.

The stage advances on candidate turns only: coverage of the core tasks moves it
on early, a turn budget moves it on when the candidate is still circling, and
the clock moves it on regardless (PRD section 4: every session covers the same
core conditions). `assessment` is set by the finish route, never here.
"""

from dataclasses import dataclass, field

from app.interview.state import ControllerState

STAGES = [
    "briefing",
    "initial_review",
    "investigation",
    "changed_condition",
    "release_discussion",
    "assessment",
]

INVESTIGATION_TURN_BUDGET = 6
INVESTIGATION_MINUTES = 12.0
CHANGED_CONDITION_TURN_BUDGET = 4
CHANGED_CONDITION_MINUTES = 18.0


@dataclass
class Facts:
    """What the rules need from the database, gathered by the controller."""

    completed_runs: int
    revocation_run_completed: bool
    elapsed_minutes: float
    latest_run_passed: dict[str, bool]  # check_id -> passed for the newest completed run
    latest_run_id: str | None = None  # the run `latest_run_passed` describes
    pending_check_ids: list[str] = field(default_factory=list)  # checks of the newest pending run


def next_stage(state: ControllerState, facts: Facts) -> str:
    turns = state.candidate_turns_in_stage
    covered = state.covered

    if state.stage == "briefing":
        return "initial_review" if turns >= 1 else "briefing"

    if state.stage == "initial_review":
        explained = covered["initial_explanation"] and covered["release_decision"]
        return "investigation" if explained or turns >= 3 else "initial_review"

    if state.stage == "investigation":
        ran_and_discussed = facts.completed_runs >= 1 and turns >= 2 and not state.pending_run_ids
        if (
            ran_and_discussed
            or turns >= INVESTIGATION_TURN_BUDGET
            or facts.elapsed_minutes >= INVESTIGATION_MINUTES
        ):
            return "changed_condition"
        return "investigation"

    if state.stage == "changed_condition":
        checked = state.revocation_introduced and facts.revocation_run_completed and turns >= 1
        if (
            checked
            or turns >= CHANGED_CONDITION_TURN_BUDGET
            or facts.elapsed_minutes >= CHANGED_CONDITION_MINUTES
        ):
            return "release_discussion"
        return "changed_condition"

    return state.stage
