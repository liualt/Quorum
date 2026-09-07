"""The one speech controller for the whole panel (PRD section 9).

A turn is planned under the interview's lock — candidate segment recorded, stage
advanced, role chosen, bounded context built, state saved — and then streamed
outside it. Every stream carries the generation number the plan gave it and
stops the moment the interview's generation moves on, so a candidate who
interrupts is never talked over by a stale response. What was actually said
is recorded as the role segment, and only a turn that was heard in full
changes the interview's bookkeeping: an interrupted hint was not a hint, an
interrupted scenario notice did not introduce the condition.

Nothing here writes prompt text or SQL: prompts come from `prompts`, rows from
`repo`, and the stage and role decisions from the pure `stages` and `roles`.
"""

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, datetime

from app import background, ids
from app.execution.runs import run_view
from app.interview.llm_client import LLMError
from app.interview.prompts import TurnContext, spoken_turn_messages
from app.interview.roles import TurnInstruction, select_role
from app.interview.stages import Facts, next_stage
from app.interview.state import ControllerState
from app.storage import repo
from app.storage.events import emit

logger = logging.getLogger(__name__)

ENDED_TEXT = "The interview has ended. Thank you."
# Spoken when the model fails. Never a made-up question: the candidate is asked to repeat.
RECOVERY_TEXT = "Give me a moment, I lost my train of thought. Could you say that again?"

# Statuses in which the panel still speaks; `finishing` and `finished` get ENDED_TEXT.
ACCEPTING_TURNS = ("created", "live")
RECENT_SEGMENTS = 12
RECENT_RUNS = 3
# How many follow-up delays a pending run waits for an open stream before it is
# left for the next candidate turn to raise.
FOLLOW_UP_ATTEMPTS = 5

# Every instruction kind not listed is stored as an ordinary `turn`.
SEGMENT_KIND_FOR = {
    "hint": "hint",
    "scenario_notice": "scenario_notice",
    "clarify": "clarification",
    "run_follow_up": "follow_up",
}

SEGMENT_VIEW_COLUMNS = (
    "id", "seq", "speaker", "kind", "text", "spoken_text", "status", "stage", "generation",
    "start_ms", "end_ms", "created_at",
)


def segment_view(row) -> dict:
    return {column: row[column] for column in SEGMENT_VIEW_COLUMNS}


@dataclass
class TurnOutcome:
    """What a collected turn reports back; filled in as the turn runs."""

    segment_id: str | None = None
    role: str = "technical"
    stage: str = "briefing"


@dataclass
class TurnPlan:
    """Everything decided under the lock before the model speaks."""

    interview_id: str
    generation: int
    stage: str
    role: str
    instruction: TurnInstruction
    messages: list[dict]
    candidate_segment_id: str | None
    pending_run_ids: list[str]

    @property
    def kind(self) -> str:
        return SEGMENT_KIND_FOR.get(self.instruction.kind, "turn")


class InterviewController:
    def __init__(self, app):
        self._app = app
        self._locks: dict[str, asyncio.Lock] = {}
        # interview id -> the generation whose stream is open right now
        self._streaming: dict[str, int] = {}

    # --- state ------------------------------------------------------------------

    @property
    def _db(self):
        return self._app.state.db

    @property
    def _bus(self):
        return self._app.state.bus

    def _lock(self, interview_id: str) -> asyncio.Lock:
        return self._locks.setdefault(interview_id, asyncio.Lock())

    def load_state(self, interview_id: str) -> ControllerState:
        row = repo.get_interview(self._db, interview_id)
        return ControllerState.from_json(row["state_json"] if row is not None else None)

    def save_state(self, interview_id: str, state: ControllerState) -> None:
        """Persist the state and keep the row's stage and role columns in step with it."""
        repo.update_interview(
            self._db,
            interview_id,
            state_json=state.to_json(),
            stage=state.stage,
            active_role=state.active_role,
        )

    def current_generation(self, interview_id: str) -> int:
        return self.load_state(interview_id).generation

    def allowed_check_ids(self, interview_id: str) -> list[str]:
        unlocked = self.load_state(interview_id).revocation_introduced
        return [
            check.id
            for check in self._app.state.scenario.checks
            if check.introduced_at == "initial" or (unlocked and check.introduced_at == "changed_condition")
        ]

    def _changed_condition_check_ids(self) -> list[str]:
        return [c.id for c in self._app.state.scenario.checks if c.introduced_at == "changed_condition"]

    def facts(self, interview_id: str) -> Facts:
        row = repo.get_interview(self._db, interview_id)
        state = ControllerState.from_json(row["state_json"] if row is not None else None)
        runs = [run for run in repo.list_runs(self._db, interview_id) if not run["replay_of"]]
        completed = [run for run in runs if run["status"] == "completed"]
        changed = set(self._changed_condition_check_ids())
        latest_passed = {}
        if completed:
            latest_passed = {
                result["check_id"]: bool(result["passed"])
                for result in repo.row_json(completed[-1], "results_json") or []
            }
        pending = [run for run in runs if run["id"] in state.pending_run_ids]
        return Facts(
            completed_runs=len(completed),
            revocation_run_completed=any(
                changed & set(repo.row_json(run, "check_ids_json")) for run in completed
            ),
            elapsed_minutes=_elapsed_minutes(row),
            latest_run_passed=latest_passed,
            latest_run_id=completed[-1]["id"] if completed else None,
            pending_check_ids=repo.row_json(pending[-1], "check_ids_json") if pending else [],
        )

    # --- turns ------------------------------------------------------------------

    def run_turn(self, interview_id: str, user_text: str, *, source: str) -> AsyncIterator[str]:
        """Stream one panel turn's spoken text. `source` is `candidate` or `run`."""
        return self._turn(interview_id, user_text, source, TurnOutcome())

    async def run_turn_collect(self, interview_id: str, user_text: str, *, source: str) -> dict:
        outcome = TurnOutcome()
        pieces = []
        async with aclosing(self._turn(interview_id, user_text, source, outcome)) as stream:
            async for chunk in stream:
                pieces.append(chunk)
        return {
            "segment_id": outcome.segment_id,
            "role": outcome.role,
            "text": "".join(pieces),
            "stage": outcome.stage,
        }

    async def _turn(self, interview_id: str, user_text: str, source: str, outcome: TurnOutcome):
        async with self._lock(interview_id):
            plan = self._plan(interview_id, user_text.strip(), source, outcome)
        if plan is None:
            yield ENDED_TEXT
            return

        pieces: list[str] = []
        status = "complete"
        self._streaming[interview_id] = plan.generation
        try:
            try:
                async with aclosing(self._app.state.llm.stream_text(plan.messages)) as stream:
                    async for chunk in stream:
                        if self.current_generation(interview_id) != plan.generation:
                            status = "interrupted"
                            break
                        pieces.append(chunk)
                        yield chunk
            except LLMError as error:
                logger.warning("turn %s of %s: %s", plan.generation, interview_id, error)
                status = "pending"
                recovery = _joined(pieces, RECOVERY_TEXT)
                pieces.append(recovery)
                yield recovery
        except BaseException:
            # The listener went away mid-stream (a closed generator, a cancelled
            # request). Keep what was said; nothing here awaits, so a cancelled
            # task cannot be cancelled again on the way out.
            self._record_role_segment(plan, "".join(pieces), "interrupted", outcome)
            raise
        finally:
            self._end_stream(interview_id, plan.generation)

        async with self._lock(interview_id):
            self._record_role_segment(plan, "".join(pieces), status, outcome)

    def _end_stream(self, interview_id: str, generation: int) -> None:
        if self._streaming.get(interview_id) == generation:
            del self._streaming[interview_id]

    def _plan(self, interview_id: str, user_text: str, source: str, outcome: TurnOutcome) -> TurnPlan | None:
        row = repo.get_interview(self._db, interview_id)
        if row is None:
            return None
        state = ControllerState.from_json(row["state_json"])
        outcome.role, outcome.stage = state.active_role, state.stage
        if row["status"] not in ACCEPTING_TURNS:
            return None

        state.generation += 1
        recent = self._recent_segments(interview_id)  # before this turn's own candidate line
        candidate_segment_id = None
        if user_text:
            candidate_segment_id = self._record_candidate(interview_id, state, user_text)
        facts = self.facts(interview_id)
        if user_text:
            self._advance_stage(interview_id, state, facts)
        role, instruction = self._choose_role(interview_id, state, facts, source)
        messages = self._build_messages(interview_id, state, role, instruction, recent, user_text)
        self.save_state(interview_id, state)

        outcome.role, outcome.stage = role, state.stage
        return TurnPlan(
            interview_id=interview_id,
            generation=state.generation,
            stage=state.stage,
            role=role,
            instruction=instruction,
            messages=messages,
            candidate_segment_id=candidate_segment_id,
            pending_run_ids=list(state.pending_run_ids),
        )

    def _record_candidate(self, interview_id: str, state: ControllerState, text: str) -> str:
        row = self._insert_segment(
            interview_id, speaker="candidate", kind="turn", text=text, stage=state.stage,
            generation=state.generation, status="complete",
        )
        state.turns_total += 1
        state.candidate_turns_in_stage += 1
        state.last_candidate_segment_id = row["id"]
        return row["id"]

    def _advance_stage(self, interview_id: str, state: ControllerState, facts: Facts) -> None:
        stage = next_stage(state, facts)
        if stage == state.stage:
            return
        state.enter_stage(stage)
        emit(self._db, self._bus, interview_id, "stage_changed", {"stage": stage})

    def _choose_role(
        self, interview_id: str, state: ControllerState, facts: Facts, source: str
    ) -> tuple[str, TurnInstruction]:
        role, instruction = select_role(state, facts)
        if source == "run" and instruction.kind != "run_follow_up":
            # The panel is speaking because a run landed, whatever else is pending.
            instruction = TurnInstruction("run_follow_up")
        if role != state.active_role:
            state.active_role = role
            emit(self._db, self._bus, interview_id, "role_changed", {"role": role})
        return role, instruction

    def _build_messages(
        self, interview_id: str, state: ControllerState, role: str, instruction: TurnInstruction,
        recent: list[dict], user_text: str,
    ) -> list[dict]:
        latest = repo.latest_snapshot(self._db, interview_id)
        runs = [run_view(run) for run in repo.list_runs(self._db, interview_id) if not run["replay_of"]]
        context = TurnContext(
            role=role,
            stage=state.stage,
            instruction_kind=instruction.kind,
            instruction_note=instruction.note,
            state_summary={
                "covered": state.covered,
                "hints_given": len(state.hints_given),
                "revocation_introduced": state.revocation_introduced,
            },
            latest_files=repo.row_json(latest, "files_json") if latest is not None else None,
            runs=runs[-RECENT_RUNS:],
            pending_runs=[run for run in runs if run["id"] in state.pending_run_ids],
            recent_segments=recent,
            candidate_text=user_text,
        )
        return spoken_turn_messages(context)

    def _recent_segments(self, interview_id: str) -> list[dict]:
        rows = repo.list_segments(self._db, interview_id, limit=RECENT_SEGMENTS)
        return [segment_view(row) for row in rows]

    def _record_role_segment(self, plan: TurnPlan, text: str, status: str, outcome: TurnOutcome) -> None:
        row = self._insert_segment(
            plan.interview_id, speaker=plan.role, kind=plan.kind, text=text, stage=plan.stage,
            generation=plan.generation, status=status,
        )
        outcome.segment_id = row["id"]
        if status == "complete":
            state = self.load_state(plan.interview_id)
            self._apply_turn_effects(plan, state, row)
            self.save_state(plan.interview_id, state)
        if plan.candidate_segment_id is not None:
            self._schedule_claims(plan.interview_id, plan.candidate_segment_id)

    def _apply_turn_effects(self, plan: TurnPlan, state: ControllerState, row) -> None:
        """The bookkeeping a turn the candidate heard in full leaves behind."""
        kind = plan.instruction.kind
        if kind == "hint":
            state.hints_given.append(row["id"])
            state.hints_in_stage += 1
        elif kind == "scenario_notice":
            state.revocation_introduced = True
            state.revocation_segment_id = row["id"]
            emit(
                self._db, self._bus, plan.interview_id, "scenario_notice",
                {"segment_id": row["id"], "text": row["text"],
                 "checks_unlocked": self._changed_condition_check_ids()},
            )
        elif kind == "clarify":
            # The ambiguity was put to the candidate; their answer decides afresh.
            state.last_clarity = "clear"
            state.contradiction_note = None
        for run_id in plan.pending_run_ids:
            if run_id in state.pending_run_ids:
                state.pending_run_ids.remove(run_id)
            if run_id not in state.discussed_run_ids:
                state.discussed_run_ids.append(run_id)
        state.role_turns_in_stage[plan.role] = state.role_turns_in_stage.get(plan.role, 0) + 1
        state.last_role_segment_id = row["id"]

    def _insert_segment(self, interview_id: str, **fields):
        row = repo.insert_segment(self._db, id=ids.new_id("seg"), interview_id=interview_id, **fields)
        emit(self._db, self._bus, interview_id, "transcript_segment", {"segment": segment_view(row)})
        return row

    def _schedule_claims(self, interview_id: str, segment_id: str) -> None:
        extractor = getattr(self._app.state, "claims_extractor", None)
        if extractor is None:
            return
        background.spawn(
            self._app, extractor(self._app, interview_id, segment_id), f"claims for {segment_id}"
        )

    # --- runs -------------------------------------------------------------------

    async def on_run_completed(self, interview_id: str, run_id: str) -> None:
        run = repo.get_run(self._db, run_id)
        if run is None or run["replay_of"]:
            return  # a replay is the reviewer's reproduction, not the candidate's work
        async with self._lock(interview_id):
            state = self.load_state(interview_id)
            if run_id not in state.pending_run_ids and run_id not in state.discussed_run_ids:
                state.pending_run_ids.append(run_id)
            self.save_state(interview_id, state)
            generation = state.generation
        link_run = getattr(self._app.state, "link_run", None)
        if link_run is not None:
            link_run(interview_id, run)

        row = repo.get_interview(self._db, interview_id)
        if row is not None and row["status"] == "live":
            background.spawn(
                self._app,
                self._proactive_follow_up(interview_id, run_id, generation),
                f"follow-up on {run_id}",
            )

    async def _proactive_follow_up(self, interview_id: str, run_id: str, generation: int) -> None:
        """Raise a run the candidate has gone quiet on, unless they spoke first.

        A response that is still streaming when the delay expires is never cut
        off (PRD section 9: a new finding is queued until the candidate is
        done); the follow-up waits another delay, a bounded number of times.
        """
        for _attempt in range(FOLLOW_UP_ATTEMPTS):
            await asyncio.sleep(self._app.state.settings.FOLLOW_UP_DELAY_SECONDS)
            row = repo.get_interview(self._db, interview_id)
            if row is None or row["status"] != "live" or row["paused"]:
                return
            state = ControllerState.from_json(row["state_json"])
            if run_id not in state.pending_run_ids or state.generation != generation:
                return  # a turn happened meanwhile; it saw the run
            if self._streaming.get(interview_id) != state.generation:
                break  # nobody is speaking
        else:
            logger.info("run %s of %s: the panel kept speaking; leaving it pending", run_id, interview_id)
            return

        outcome = await self.run_turn_collect(interview_id, "", source="run")
        voice = getattr(self._app.state, "voice", None)
        if voice is not None and voice.enabled and row["agora_agent_id"] and outcome["text"]:
            await voice.say(row["agora_agent_id"], outcome["text"])

    # --- transcript -------------------------------------------------------------

    async def apply_transcript_status(
        self, interview_id: str, *, speaker: str, status: str, text: str, turn_id: int
    ) -> str | None:
        """Map what the browser heard the agent say onto the stored role segment.

        Candidate speech reaches the record through the model endpoint, so a
        candidate report has nothing to update.
        """
        if speaker != "agent":
            return None
        heard = _normalise(text)
        for row in reversed(repo.list_segments(self._db, interview_id)):
            if row["speaker"] == "candidate":
                continue
            stored = _normalise(row["text"])
            if not (stored.startswith(heard) or heard.startswith(stored)):
                continue
            updated = repo.update_segment(
                self._db, row["id"], spoken_text=text,
                status="interrupted" if status == "interrupted" else "complete",
            )
            emit(self._db, self._bus, interview_id, "segment_updated", {"segment": segment_view(updated)})
            return updated["id"]
        return None


def _normalise(text: str | None) -> str:
    return " ".join(re.sub(r"[^\w\s]", "", (text or "").lower()).split())


def _joined(pieces: list[str], text: str) -> str:
    """`text` as the next spoken piece: separated from what came before by a space."""
    if pieces and not pieces[-1].endswith((" ", "\n")):
        return " " + text
    return text


def _elapsed_minutes(row) -> float:
    """Minutes since the interview started, with paused time taken out."""
    if row is None or not row["started_at"]:
        return 0.0
    now = datetime.now(UTC)
    paused_seconds = (row["paused_ms"] or 0) / 1000
    if row["paused"] and row["paused_at"]:
        paused_seconds += (now - datetime.fromisoformat(row["paused_at"])).total_seconds()
    elapsed = (now - datetime.fromisoformat(row["started_at"])).total_seconds() - paused_seconds
    return max(0.0, elapsed) / 60
