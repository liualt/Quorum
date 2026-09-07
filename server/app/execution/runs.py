"""Run and replay services: what may run, what happened, and what changed.

Everything a route needs about a run lives here; the routes only translate
`RunError` into an HTTP status. A run's results are written once, from the
runner's own output, and are never invented for a run that did not complete.
"""

import asyncio
import json
import logging
from datetime import datetime

from app import background, ids
from app.execution import archive
from app.execution.archive import ArchiveError, RunInputs
from app.execution.checks import evaluate, results_differ
from app.execution.runner_protocol import (
    build_script,
    build_workspace_files,
    input_hash,
    parse_output,
)
from app.storage import repo, usage
from app.storage.events import emit

logger = logging.getLogger(__name__)

EXCERPT_BYTES = 4096
MAX_REPLAYS_PER_RUN = 3
# Sandbox provisioning and file transfer sit outside the command timeout, so the
# whole executor call gets its own deadline; without one a stalled control plane
# holds a run `running` and 409s every later run.
EXECUTOR_DEADLINE_MARGIN_SECONDS = 40
# What the candidate is told when the backend itself broke. The reason is logged.
EXECUTION_FAILED_MESSAGE = "Execution failed before results were produced."


class RunError(Exception):
    """A refused run, carrying the HTTP status the route should return."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def run_view(row) -> dict:
    differs = row["differs_from_original"]
    return {
        "id": row["id"],
        "snapshot_id": row["snapshot_id"],
        "status": row["status"],
        "check_ids": repo.row_json(row, "check_ids_json"),
        "results": repo.row_json(row, "results_json"),
        "executor": row["executor"],
        "sandbox_id": row["sandbox_id"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "replay_of": row["replay_of"],
        "differs_from_original": None if differs is None else bool(differs),
        "fixture_version": row["fixture_version"],
        "check_version": row["check_version"],
        "input_hash": row["input_hash"],
        "inputs_hash": row["inputs_hash"],
        "stdout_excerpt": row["stdout_excerpt"],
        "stderr_excerpt": row["stderr_excerpt"],
        "created_at": row["created_at"],
    }


def allowed_check_ids(app, interview_id: str) -> list[str]:
    """The checks the candidate may run right now; the controller owns the rule."""
    return app.state.controller.allowed_check_ids(interview_id)


async def start_run(app, interview_id: str, snapshot_id: str, check_ids: list[str],
                    idempotency_key: str | None):
    conn = app.state.db
    if idempotency_key:
        existing = repo.find_run_by_idempotency(conn, interview_id, idempotency_key)
        if existing is not None:
            return existing

    snapshot = repo.get_snapshot(conn, snapshot_id)
    if snapshot is None or snapshot["interview_id"] != interview_id:
        raise RunError(404, "snapshot not found")
    if repo.active_run(conn, interview_id) is not None:
        raise RunError(409, "a run is already in progress")
    if repo.count_runs(conn, interview_id) >= app.state.settings.MAX_RUNS_PER_INTERVIEW:
        raise RunError(409, "this interview has used all of its runs")

    scenario = app.state.scenario
    checks = _selected_checks(app, interview_id, check_ids)
    # The run executes from the archive, never from the installed scenario, so
    # what it ran against is on disk under its own hash before it is scheduled.
    inputs = RunInputs.from_scenario(scenario)
    inputs_hash = archive.store(app.state.settings.SNAPSHOT_DIR, inputs)
    return _insert_and_schedule(
        app,
        interview_id,
        snapshot_id=snapshot_id,
        fixture_version=scenario.fixture_version,
        check_version=scenario.check_version,
        check_ids_json=json.dumps([check.id for check in checks]),
        input_hash=input_hash(scenario, snapshot["content_hash"], [c.id for c in checks], inputs_hash),
        inputs_hash=inputs_hash,
        idempotency_key=idempotency_key,
    )


async def start_replay(app, interview_id: str, run_id: str):
    """Re-run a completed run's own inputs.

    A replay does not spend the candidate's run budget — it is the reviewer's
    reproduction, not the candidate's work — but it still takes the one active
    run slot, and one original can only be replayed a few times.
    """
    conn = app.state.db
    original = repo.get_run(conn, run_id)
    if original is None or original["interview_id"] != interview_id:
        raise RunError(404, "run not found")
    if original["status"] != "completed":
        raise RunError(409, "only a completed run can be replayed")
    if original["replay_of"]:
        raise RunError(409, "replay the original run, not a replay")
    scenario = app.state.scenario
    if (original["fixture_version"] != scenario.fixture_version
            or original["check_version"] != scenario.check_version):
        raise RunError(409, "the original fixture and check versions are not available")
    inputs = _archived_inputs(app, original)
    if repo.active_run(conn, interview_id) is not None:
        raise RunError(409, "a run is already in progress")
    replays = [row for row in repo.list_runs(conn, interview_id) if row["replay_of"] == run_id]
    if len(replays) >= MAX_REPLAYS_PER_RUN:
        raise RunError(409, f"this run has already been replayed {MAX_REPLAYS_PER_RUN} times")

    # Hashed again from the archive, not copied: a replay's hash vouches for the
    # bytes it will actually execute, and it must agree with the original's.
    snapshot = repo.get_snapshot(conn, original["snapshot_id"])
    if snapshot is None:
        raise RunError(409, "the original run's snapshot is no longer available")
    check_ids = repo.row_json(original, "check_ids_json")
    replay_hash = input_hash(inputs, snapshot["content_hash"], check_ids, original["inputs_hash"])
    if replay_hash != original["input_hash"]:
        raise RunError(409, "the archived inputs no longer match the original run")

    return _insert_and_schedule(
        app,
        interview_id,
        snapshot_id=original["snapshot_id"],
        fixture_version=original["fixture_version"],
        check_version=original["check_version"],
        check_ids_json=original["check_ids_json"],
        input_hash=replay_hash,
        inputs_hash=original["inputs_hash"],
        replay_of=original["id"],
    )


def _archived_inputs(app, run) -> RunInputs:
    """The exact inputs `run` executed against, or a refusal the route can return."""
    if not run["inputs_hash"]:
        raise RunError(409, "the original run's inputs were not archived and cannot be replayed")
    try:
        return archive.load(app.state.settings.SNAPSHOT_DIR, run["inputs_hash"])
    except ArchiveError as error:
        raise RunError(409, f"the original run's inputs cannot be replayed: {error}") from error


async def execute_run(app, run_id: str) -> None:
    conn = app.state.db
    run = repo.get_run(conn, run_id)
    if run is None:
        return
    interview_id = run["interview_id"]
    repo.update_run(conn, run_id, status="running", started_at=ids.now_iso())

    executor_failed = False
    try:
        fields = await _execute(app, run)
    except TimeoutError:  # the whole executor call, not just the sandbox command
        logger.warning("run %s passed its deadline", run_id)
        fields = {"status": "timeout", "stderr_excerpt": EXECUTION_FAILED_MESSAGE}
        executor_failed = True
    except Exception:  # a crash here must not leave the run running forever
        logger.exception("run %s failed before results were produced", run_id)
        fields = {"status": "failed", "stderr_excerpt": EXECUTION_FAILED_MESSAGE}
        executor_failed = True
    if repo.get_run(conn, run_id) is None:
        return
    row = repo.update_run(conn, run_id, finished_at=ids.now_iso(), **fields)
    # Failed runs cost sandbox time too (PRD section 15), so every run is counted.
    usage.record(
        conn, interview_id,
        sandbox_runs=1,
        sandbox_seconds=_seconds_between(row["started_at"], row["finished_at"]),
        provider_failures=int(executor_failed),
    )

    row, replay_differs = _compare_with_original(conn, row)
    emit(conn, app.state.bus, interview_id, "run_completed", {"run": run_view(row)})

    if replay_differs:
        mark_needing_review = getattr(app.state, "mark_findings_needing_review", None)
        if mark_needing_review is not None:
            mark_needing_review(interview_id, "run", row["replay_of"], "replay_differs")

    controller = getattr(app.state, "controller", None)
    if controller is not None:
        await controller.on_run_completed(interview_id, run_id)


def recover_interrupted_runs(app) -> int:
    """A single-worker restart cannot resume the previous process's tasks."""
    abandoned = repo.list_active_runs(app.state.db)
    for run in abandoned:
        row = repo.update_run(
            app.state.db, run["id"], status="failed", finished_at=ids.now_iso(),
            results_json=None,
            stderr_excerpt="The server restarted before this run finished. Please retry.",
        )
        emit(app.state.db, app.state.bus, row["interview_id"], "run_completed", {"run": run_view(row)})
    return len(abandoned)


async def _execute(app, run) -> dict:
    """Run the sandbox and return the row fields its outcome implies."""
    settings = app.state.settings
    # Fresh runs and replays alike execute the archived bytes recorded on the
    # row, so a replay reproduces the original run rather than the current
    # installation, whatever has been edited on disk since.
    inputs = archive.load(settings.SNAPSHOT_DIR, run["inputs_hash"])

    snapshot = repo.get_snapshot(app.state.db, run["snapshot_id"])
    if snapshot is None:
        raise LookupError(f"snapshot {run['snapshot_id']} is gone")
    files = build_workspace_files(inputs, repo.row_json(snapshot, "files_json"))
    checks = _checks_by_id(inputs, repo.row_json(run, "check_ids_json"))

    result = await asyncio.wait_for(
        app.state.executor.run(
            files,
            build_script(checks),
            timeout_s=settings.RUN_TIMEOUT_SECONDS,
            output_cap=settings.RUN_OUTPUT_CAP_BYTES,
        ),
        timeout=settings.RUN_TIMEOUT_SECONDS + EXECUTOR_DEADLINE_MARGIN_SECONDS,
    )
    fields = {
        "status": result.status,
        "stdout_excerpt": _tail(result.stdout),
        "stderr_excerpt": _tail(result.stderr),
        "sandbox_id": result.sandbox_id,
    }
    if result.status != "completed":
        return fields

    try:
        parsed = parse_output(result.stdout)
    except ValueError as error:
        fields["status"] = "failed"
        fields["stderr_excerpt"] = _tail(f"{result.stderr}\n[parse error] {error}")
        return fields

    fields["results_json"] = json.dumps([item.to_dict() for item in evaluate(checks, parsed)])
    return fields


def _compare_with_original(conn, row) -> tuple[object, bool]:
    """For a replay, record whether it reproduced the original's outcome."""
    if not row["replay_of"]:
        return row, False

    original = repo.get_run(conn, row["replay_of"])
    differs = None
    if original is not None and original["status"] == "completed" and row["status"] == "completed":
        differs = results_differ(
            repo.row_json(original, "results_json"), repo.row_json(row, "results_json")
        )
    row = repo.update_run(
        conn, row["id"], differs_from_original=None if differs is None else int(differs)
    )
    return row, bool(differs)


def _selected_checks(app, interview_id: str, check_ids: list[str]) -> list:
    scenario = app.state.scenario
    requested = list(dict.fromkeys(check_ids))
    if not requested:
        raise RunError(400, "select at least one check")

    known = {check.id for check in scenario.checks}
    unknown = [check_id for check_id in requested if check_id not in known]
    if unknown:
        raise RunError(400, f"unknown check ids: {', '.join(unknown)}")

    allowed = set(allowed_check_ids(app, interview_id))
    unavailable = [check_id for check_id in requested if check_id not in allowed]
    if unavailable:
        raise RunError(400, f"checks not available yet: {', '.join(unavailable)}")

    return _checks_by_id(scenario, requested)


def _checks_by_id(scenario, check_ids: list[str]) -> list:
    """The requested checks in scenario order, so a run is reproducible."""
    wanted = set(check_ids)
    return [check for check in scenario.checks if check.id in wanted]


def _insert_and_schedule(app, interview_id: str, **fields):
    run_id = ids.new_id("run")
    row = repo.insert_run(
        app.state.db,
        id=run_id,
        interview_id=interview_id,
        status="queued",
        executor=app.state.executor.name,
        **fields,
    )
    emit(app.state.db, app.state.bus, interview_id, "run_started", {"run": run_view(row)})
    background.spawn(app, execute_run(app, run_id), f"run {run_id}", interview_id=interview_id)
    return row


def _seconds_between(started_at: str | None, finished_at: str | None) -> float:
    if not started_at or not finished_at:
        return 0.0
    delta = datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)
    return max(0.0, delta.total_seconds())


def _tail(text: str | None) -> str | None:
    """The last few KB of output, which is where a failure explains itself."""
    if text is None:
        return None
    data = text.encode("utf-8", "replace")
    if len(data) <= EXCERPT_BYTES:
        return text
    return data[-EXCERPT_BYTES:].decode("utf-8", "ignore")
