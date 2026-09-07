"""Run and replay services, plus the snapshot storage they read from.

The executor is stubbed here so the assertions are about bookkeeping — limits,
idempotency, statuses, events, replay comparison — rather than about sandbox
behaviour, which `test_checks_matrix.py` covers end to end.
"""

import asyncio
import json

import pytest

from app.execution import runs
from app.execution.executor import ExecResult
from app.execution.runs import RunError, allowed_check_ids, run_view
from app.storage import repo, snapshots
from app.storage.snapshots import SnapshotError
from tests.conftest import seed_interview, seed_snapshot

INITIAL_CHECK = "cross_company_isolation"
CHANGED_CHECK = "revocation_next_request"


class StubExecutor:
    """Returns canned runner output, one entry per call, repeating the last."""

    name = "local"

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.scripts = []

    async def run(self, files, script, *, timeout_s, output_cap):
        self.scripts.append(script)
        index = min(len(self.scripts) - 1, len(self.outputs) - 1)
        return ExecResult(
            status="completed",
            stdout=self.outputs[index],
            stderr="",
            exit_code=0,
            sandbox_id="sbx_stub",
            duration_ms=5,
        )


class FailingExecutor:
    name = "local"

    def __init__(self, status="timeout"):
        self.status = status

    async def run(self, files, script, *, timeout_s, output_cap):
        return ExecResult(
            status=self.status,
            stdout="",
            stderr="killed",
            exit_code=None,
            sandbox_id=None,
            duration_ms=5,
        )


def runner_output(scenario, check_ids, *, mangle_first_step=False):
    """The stdout the real runner would print for a run that meets expectations."""
    results = []
    for check in scenario.checks:
        if check.id not in check_ids:
            continue
        steps = [
            {"returned": [] if step.expect is None else list(step.expect), "error": None}
            for step in check.steps
        ]
        if mangle_first_step:
            steps[0]["returned"] = ["doc_unexpected"]
        results.append(
            {
                "check_id": check.id,
                "steps": steps,
                "search_calls": check.max_search_calls,
                "error": None,
            }
        )
    return json.dumps({"results": results})


@pytest.fixture
def seeded(live_app, scenario):
    """An interview, a snapshot of the seeded files, and a passing executor."""
    interview = seed_interview(live_app)
    snapshot = seed_snapshot(live_app, interview["id"], dict(scenario.editable_files))
    live_app.state.executor = StubExecutor(runner_output(scenario, [INITIAL_CHECK, CHANGED_CHECK]))
    return interview, snapshot


async def drain(app):
    tasks = list(getattr(app.state, "background_tasks", ()))
    if tasks:
        await asyncio.gather(*tasks)


def event_types(app, interview_id):
    return [event["type"] for event in repo.list_events(app.state.db, interview_id, 0)]


# --- start_run ------------------------------------------------------------

async def test_idempotent_start_returns_the_existing_run(live_app, seeded):
    interview, snapshot = seeded

    first = await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], "key-1")
    second = await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], "key-1")

    assert first["id"] == second["id"]
    assert repo.count_runs(live_app.state.db, interview["id"]) == 1
    await drain(live_app)


async def test_second_run_while_one_is_active_is_rejected(live_app, seeded):
    interview, snapshot = seeded

    await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], None)
    with pytest.raises(RunError) as excinfo:
        await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], None)

    assert excinfo.value.status_code == 409
    await drain(live_app)


async def test_run_limit_rejects_the_next_run(live_app, seeded, scenario):
    interview, snapshot = seeded
    for index in range(live_app.state.settings.MAX_RUNS_PER_INTERVIEW):
        repo.insert_run(
            live_app.state.db,
            id=f"run_seed{index}",
            interview_id=interview["id"],
            snapshot_id=snapshot["id"],
            fixture_version=scenario.fixture_version,
            check_version=scenario.check_version,
            check_ids_json=json.dumps([INITIAL_CHECK]),
            input_hash="hash",
            status="completed",
            executor="local",
        )

    with pytest.raises(RunError) as excinfo:
        await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], None)

    assert excinfo.value.status_code == 409


async def test_unknown_check_id_is_rejected(live_app, seeded):
    interview, snapshot = seeded

    with pytest.raises(RunError) as excinfo:
        await runs.start_run(live_app, interview["id"], snapshot["id"], ["not_a_check"], None)

    assert excinfo.value.status_code == 400


async def test_snapshot_from_another_interview_is_not_found(live_app, seeded):
    _interview, snapshot = seeded
    other = seed_interview(live_app)

    with pytest.raises(RunError) as excinfo:
        await runs.start_run(live_app, other["id"], snapshot["id"], [INITIAL_CHECK], None)

    assert excinfo.value.status_code == 404


# --- allowed checks -------------------------------------------------------

async def test_changed_condition_check_is_rejected_until_revocation_is_introduced(live_app, seeded):
    interview, snapshot = seeded

    assert allowed_check_ids(live_app, interview["id"]) == [
        "access_filtering",
        "cross_company_isolation",
        "repeat_search_efficiency",
    ]
    with pytest.raises(RunError) as excinfo:
        await runs.start_run(live_app, interview["id"], snapshot["id"], [CHANGED_CHECK], None)

    assert excinfo.value.status_code == 400


async def test_changed_condition_check_is_allowed_after_revocation_is_introduced(live_app, scenario):
    interview = seed_interview(live_app, state_json=json.dumps({"revocation_introduced": True}))
    snapshot = seed_snapshot(live_app, interview["id"], dict(scenario.editable_files))
    live_app.state.executor = StubExecutor(runner_output(scenario, [CHANGED_CHECK]))

    assert CHANGED_CHECK in allowed_check_ids(live_app, interview["id"])
    run = await runs.start_run(live_app, interview["id"], snapshot["id"], [CHANGED_CHECK], None)
    await drain(live_app)

    assert repo.get_run(live_app.state.db, run["id"])["status"] == "completed"


async def test_allowed_check_ids_delegates_to_a_controller_when_present(live_app, seeded):
    interview, _snapshot = seeded

    class StubController:
        def allowed_check_ids(self, interview_id):
            return [CHANGED_CHECK]

    live_app.state.controller = StubController()

    assert allowed_check_ids(live_app, interview["id"]) == [CHANGED_CHECK]


# --- execute_run ----------------------------------------------------------

async def test_execute_run_stores_results_and_emits_run_completed(live_app, seeded):
    interview, snapshot = seeded

    run = await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], None)
    assert run["status"] == "queued"
    await drain(live_app)

    stored = repo.get_run(live_app.state.db, run["id"])
    assert stored["status"] == "completed"
    assert stored["started_at"] and stored["finished_at"]
    assert stored["sandbox_id"] == "sbx_stub"
    view = run_view(stored)
    assert view["check_ids"] == [INITIAL_CHECK]
    assert view["results"][0]["check_id"] == INITIAL_CHECK
    assert view["results"][0]["passed"] is True
    assert view["differs_from_original"] is None
    assert event_types(live_app, interview["id"]) == ["run_started", "run_completed"]


async def test_execute_run_notifies_the_controller(live_app, seeded):
    interview, snapshot = seeded
    completed = []

    class StubController:
        def allowed_check_ids(self, interview_id):
            return [INITIAL_CHECK]

        async def on_run_completed(self, interview_id, run_id):
            completed.append((interview_id, run_id))

    live_app.state.controller = StubController()

    run = await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], None)
    await drain(live_app)

    assert completed == [(interview["id"], run["id"])]


async def test_a_timed_out_run_never_invents_results(live_app, seeded):
    interview, snapshot = seeded
    live_app.state.executor = FailingExecutor("timeout")

    run = await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], None)
    await drain(live_app)

    stored = repo.get_run(live_app.state.db, run["id"])
    assert stored["status"] == "timeout"
    assert stored["results_json"] is None
    assert stored["stderr_excerpt"] == "killed"


async def test_unparseable_output_fails_the_run(live_app, seeded):
    interview, snapshot = seeded
    live_app.state.executor = StubExecutor("Traceback: no json here\n")

    run = await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], None)
    await drain(live_app)

    stored = repo.get_run(live_app.state.db, run["id"])
    assert stored["status"] == "failed"
    assert stored["results_json"] is None
    assert "Traceback" in stored["stdout_excerpt"]


# --- replay ---------------------------------------------------------------

async def test_replay_reruns_the_original_and_leaves_it_untouched(live_app, seeded, scenario):
    interview, snapshot = seeded

    original = await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], None)
    await drain(live_app)
    before = repo.get_run(live_app.state.db, original["id"])["results_json"]

    replay = await runs.start_replay(live_app, interview["id"], original["id"])
    await drain(live_app)

    stored_replay = repo.get_run(live_app.state.db, replay["id"])
    assert stored_replay["replay_of"] == original["id"]
    assert stored_replay["snapshot_id"] == snapshot["id"]
    assert stored_replay["fixture_version"] == scenario.fixture_version
    assert repo.row_json(stored_replay, "check_ids_json") == [INITIAL_CHECK]
    assert stored_replay["differs_from_original"] == 0
    assert repo.get_run(live_app.state.db, original["id"])["results_json"] == before


async def test_replay_with_different_results_is_flagged_for_review(live_app, seeded, scenario):
    interview, snapshot = seeded
    live_app.state.executor = StubExecutor(
        runner_output(scenario, [INITIAL_CHECK]),
        runner_output(scenario, [INITIAL_CHECK], mangle_first_step=True),
    )
    flagged = []
    live_app.state.mark_findings_needing_review = lambda *args: flagged.append(args)

    original = await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], None)
    await drain(live_app)
    replay = await runs.start_replay(live_app, interview["id"], original["id"])
    await drain(live_app)

    assert repo.get_run(live_app.state.db, replay["id"])["differs_from_original"] == 1
    assert flagged == [(interview["id"], "run", original["id"], "replay_differs")]


async def test_replay_requires_a_completed_original(live_app, seeded):
    interview, snapshot = seeded
    live_app.state.executor = FailingExecutor("failed")

    original = await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], None)
    await drain(live_app)

    with pytest.raises(RunError) as excinfo:
        await runs.start_replay(live_app, interview["id"], original["id"])

    assert excinfo.value.status_code == 409


# --- snapshot storage -----------------------------------------------------

def test_validate_files_rejects_a_read_only_name():
    with pytest.raises(SnapshotError):
        snapshots.validate_files({"index.py": "x"}, 1000)


def test_validate_files_rejects_a_traversal_name():
    with pytest.raises(SnapshotError):
        snapshots.validate_files({"../search.py": "x"}, 1000)


def test_validate_files_rejects_oversize_source():
    with pytest.raises(SnapshotError):
        snapshots.validate_files({"search.py": "x" * 101}, 100)


def test_validate_files_rejects_non_text_and_nul_bytes():
    with pytest.raises(SnapshotError):
        snapshots.validate_files({"search.py": b"x"}, 1000)
    with pytest.raises(SnapshotError):
        snapshots.validate_files({"search.py": "a\x00b"}, 1000)


def test_validate_files_accepts_a_subset_of_the_editable_files():
    snapshots.validate_files({"search.py": "x", "cache.py": "y"}, 1000)


def test_content_hash_is_stable_across_key_order():
    first = snapshots.content_hash({"search.py": "a", "cache.py": "b"})
    second = snapshots.content_hash({"cache.py": "b", "search.py": "a"})
    third = snapshots.content_hash({"cache.py": "b", "search.py": "c"})

    assert first == second
    assert first != third


def test_snapshots_round_trip_on_disk(tmp_path):
    files = {"search.py": "print('hi')\n", "cache.py": "_entries = {}\n"}
    snapshots.write_snapshot(str(tmp_path), "itv_1", "snap_1", files)

    assert snapshots.read_snapshot(str(tmp_path), "itv_1", "snap_1") == files
    assert (tmp_path / "itv_1" / "snap_1" / "search.py").exists()

    snapshots.delete_interview_dir(str(tmp_path), "itv_1")
    assert not (tmp_path / "itv_1").exists()
    snapshots.delete_interview_dir(str(tmp_path), "itv_1")
