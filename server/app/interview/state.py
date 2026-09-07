"""The controller's persisted state: one JSON document per interview.

Everything the stage and role rules read lives here, so the rules can be pure
functions and a restarted server picks an interview up exactly where it was.
"""

import json
from dataclasses import asdict, dataclass, field, fields


def _default_covered() -> dict[str, bool]:
    return {
        "initial_explanation": False,
        "release_decision": False,
        "cross_company": False,
        "revocation": False,
        "final_recommendation": False,
    }


@dataclass
class ControllerState:
    stage: str = "briefing"
    active_role: str = "technical"
    # Bumped by every turn; a stream whose generation is no longer current stops.
    generation: int = 0
    candidate_turns_in_stage: int = 0
    turns_total: int = 0
    role_turns_in_stage: dict[str, int] = field(default_factory=dict)
    covered: dict[str, bool] = field(default_factory=_default_covered)
    hints_given: list[str] = field(default_factory=list)  # segment ids
    hints_in_stage: int = 0
    revocation_introduced: bool = False
    revocation_segment_id: str | None = None
    discussed_run_ids: list[str] = field(default_factory=list)
    pending_run_ids: list[str] = field(default_factory=list)
    last_candidate_segment_id: str | None = None
    last_role_segment_id: str | None = None
    last_clarity: str = "clear"
    contradiction_note: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, text: str | None) -> "ControllerState":
        """Read a stored document, filling anything it lacks with the defaults.

        A partial document (an older row, or a test seeding one flag) is
        merged over the defaults rather than rejected, and unknown keys are
        dropped so a newer server can read an older row.
        """
        data = json.loads(text) if text else {}
        known = {item.name for item in fields(cls)}
        state = cls(**{key: value for key, value in data.items() if key in known})
        state.covered = {**_default_covered(), **(data.get("covered") or {})}
        return state

    def enter_stage(self, stage: str) -> None:
        """Move to `stage` and reset every per-stage counter."""
        self.stage = stage
        self.candidate_turns_in_stage = 0
        self.role_turns_in_stage = {}
        self.hints_in_stage = 0
