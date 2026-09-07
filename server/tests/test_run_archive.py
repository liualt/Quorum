"""Archived run inputs: a replay reproduces the bytes the original ran against.

The scenario is copied into the test's temp directory so these tests can edit
fixtures in place and "upgrade" the deployment without touching the repo.
"""

import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from app.config import Settings
from app.execution import archive, runs
from app.execution.archive import ArchiveError, RunInputs
from app.execution.executor import ExecResult
from app.execution.runs import RunError
from app.scenario import load_scenario
from app.storage import db, repo
from tests.conftest import INITIAL_CHECK, drain, seed_interview, seed_snapshot
from tests.test_runs import runner_output

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = "documents.json"


@pytest.fixture
def scenario_root(tmp_path):
    root = tmp_path / "scenarios"
    shutil.copytree(REPO_ROOT / "scenarios" / "document-search", root / "document-search")
    return root


@pytest.fixture
def settings(tmp_path, scenario_root):
    return Settings(
        DATABASE_PATH=str(tmp_path / "quorum.db"),
        SNAPSHOT_DIR=str(tmp_path / "snapshots"),
        SESSION_SECRET="test",
        LLM_PROVIDER="scripted",
        EXECUTOR="local",
        SCENARIO_DIR=str(scenario_root),
    )


class RecordingExecutor:
    """Passes every check and remembers the workspace each run was given."""

    name = "local"

    def __init__(self, scenario):
        self.output = runner_output(scenario, [INITIAL_CHECK])
        self.workspaces = []

    async def run(self, files, script, *, timeout_s, output_cap):
        self.workspaces.append(dict(files))
        return ExecResult(status="completed", stdout=self.output, stderr="", exit_code=0,
                          sandbox_id="sbx_stub", duration_ms=5)


@pytest.fixture
def seeded(live_app):
    interview = seed_interview(live_app)
    snapshot = seed_snapshot(live_app, interview["id"], dict(live_app.state.scenario.editable_files))
    live_app.state.executor = RecordingExecutor(live_app.state.scenario)
    return interview, snapshot


def archive_root(app) -> Path:
    return Path(app.state.settings.SNAPSHOT_DIR) / archive.ARCHIVE_DIRNAME


def archive_contents(app) -> dict[str, bytes]:
    root = archive_root(app)
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def fixture_path(scenario_root) -> Path:
    return scenario_root / "document-search" / "fixtures" / "v1" / FIXTURE


def reinstall(app, scenario_root):
    """What a restart does: load whatever is on disk now, under whatever label it has."""
    app.state.scenario = load_scenario(scenario_root, "document-search")
    app.state.executor = RecordingExecutor(app.state.scenario)


async def completed_original(live_app, seeded):
    interview, snapshot = seeded
    original = await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], None)
    await drain(live_app)
    original = repo.get_run(live_app.state.db, original["id"])
    assert original["status"] == "completed"
    assert original["inputs_hash"]
    return interview, snapshot, original


# --- (a) an edit under an unchanged version label ------------------------------------------


async def test_replay_uses_the_archived_fixture_not_the_edited_one(live_app, seeded, scenario_root):
    interview, _, original = await completed_original(live_app, seeded)
    original_fixture = fixture_path(scenario_root).read_text(encoding="utf-8")

    edited = original_fixture.replace("{", '{"tampered": true, ', 1)
    fixture_path(scenario_root).write_text(edited, encoding="utf-8")
    reinstall(live_app, scenario_root)
    assert live_app.state.scenario.fixture_version == original["fixture_version"]  # label unchanged
    assert live_app.state.scenario.readonly_files[f"fixtures/{FIXTURE}"] == edited

    replay = await runs.start_replay(live_app, interview["id"], original["id"])
    await drain(live_app)

    stored = repo.get_run(live_app.state.db, replay["id"])
    assert stored["status"] == "completed"
    assert stored["differs_from_original"] == 0
    assert stored["input_hash"] == original["input_hash"]
    assert stored["inputs_hash"] == original["inputs_hash"]
    assert stored["results_json"] == original["results_json"]
    [workspace] = live_app.state.executor.workspaces
    assert workspace[f"fixtures/{FIXTURE}"] == original_fixture


async def test_a_fresh_run_after_an_edit_gets_its_own_archive_entry_and_hash(live_app, seeded, scenario_root):
    interview, snapshot, original = await completed_original(live_app, seeded)
    fixture_path(scenario_root).write_text("[]", encoding="utf-8")
    reinstall(live_app, scenario_root)

    fresh = await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], None)
    await drain(live_app)

    fresh = repo.get_run(live_app.state.db, fresh["id"])
    assert fresh["fixture_version"] == original["fixture_version"]
    assert fresh["inputs_hash"] != original["inputs_hash"]
    assert fresh["input_hash"] != original["input_hash"]
    assert sorted(p.name for p in archive_root(live_app).iterdir()) == sorted(
        [original["inputs_hash"], fresh["inputs_hash"]]
    )
    assert live_app.state.executor.workspaces[-1][f"fixtures/{FIXTURE}"] == "[]"


# --- (b) a deployment upgrade changes the version label ------------------------------------


async def test_replay_after_a_version_upgrade_is_refused_and_the_archive_is_untouched(
    live_app, seeded, scenario_root
):
    interview, _, original = await completed_original(live_app, seeded)
    before = archive_contents(live_app)

    fixtures = scenario_root / "document-search" / "fixtures"
    os.rename(fixtures / "v1", fixtures / "v2")
    reinstall(live_app, scenario_root)
    assert live_app.state.scenario.fixture_version == "v2"

    with pytest.raises(RunError, match="versions are not available") as error:
        await runs.start_replay(live_app, interview["id"], original["id"])

    assert error.value.status_code == 409
    assert archive_contents(live_app) == before
    assert len(repo.list_runs(live_app.state.db, interview["id"])) == 1
    assert archive.load(live_app.state.settings.SNAPSHOT_DIR, original["inputs_hash"]).fixture_version == "v1"


# --- (c) identical inputs share one entry ------------------------------------------------


async def test_runs_with_identical_inputs_share_one_archive_entry(live_app, seeded):
    interview, snapshot, first = await completed_original(live_app, seeded)
    second = await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], None)
    await drain(live_app)
    replay = await runs.start_replay(live_app, interview["id"], first["id"])
    await drain(live_app)

    second = repo.get_run(live_app.state.db, second["id"])
    replay = repo.get_run(live_app.state.db, replay["id"])
    assert first["inputs_hash"] == second["inputs_hash"] == replay["inputs_hash"]
    assert [p.name for p in archive_root(live_app).iterdir()] == [first["inputs_hash"]]
    assert archive_contents(live_app)  # the shared entry is real, not an empty directory


def test_store_is_idempotent_and_load_round_trips(tmp_path, scenario):
    inputs = RunInputs.from_scenario(scenario)
    digest = archive.store(tmp_path, inputs)
    assert archive.store(tmp_path, inputs) == digest
    assert digest == archive.inputs_hash(inputs)

    loaded = archive.load(tmp_path, digest)
    assert loaded == inputs
    assert archive.inputs_hash(loaded) == digest
    entry = Path(archive.entry_path(tmp_path, digest))
    assert (entry / "readonly" / "fixtures" / FIXTURE).read_text(encoding="utf-8") == (
        scenario.readonly_files[f"fixtures/{FIXTURE}"]
    )
    assert (entry / "readonly" / "runner.py").exists()
    assert (entry / "defaults" / "search.py").exists()
    assert json.loads((entry / "checks.json").read_text(encoding="utf-8"))["checks"]


# --- a missing or tampered archive ---------------------------------------------------------


async def test_replay_is_refused_when_the_archive_entry_is_missing(live_app, seeded):
    interview, _, original = await completed_original(live_app, seeded)
    shutil.rmtree(archive.entry_path(live_app.state.settings.SNAPSHOT_DIR, original["inputs_hash"]))

    with pytest.raises(RunError, match="cannot be replayed") as error:
        await runs.start_replay(live_app, interview["id"], original["id"])

    assert error.value.status_code == 409
    assert len(repo.list_runs(live_app.state.db, interview["id"])) == 1


async def test_replay_is_refused_when_the_archive_entry_was_tampered_with(live_app, seeded):
    interview, _, original = await completed_original(live_app, seeded)
    entry = Path(archive.entry_path(live_app.state.settings.SNAPSHOT_DIR, original["inputs_hash"]))
    (entry / "readonly" / "fixtures" / FIXTURE).write_text("[]", encoding="utf-8")

    with pytest.raises(RunError, match="do not match their hash") as error:
        await runs.start_replay(live_app, interview["id"], original["id"])
    assert error.value.status_code == 409

    with pytest.raises(ArchiveError):
        archive.load(live_app.state.settings.SNAPSHOT_DIR, original["inputs_hash"])


async def test_a_run_whose_archive_vanished_fails_without_inventing_results(live_app, seeded):
    interview, snapshot = seeded
    run = await runs.start_run(live_app, interview["id"], snapshot["id"], [INITIAL_CHECK], None)
    shutil.rmtree(archive_root(live_app))
    await drain(live_app)

    stored = repo.get_run(live_app.state.db, run["id"])
    assert stored["status"] == "failed"
    assert stored["results_json"] is None
    assert live_app.state.executor.workspaces == []


# --- schema -------------------------------------------------------------------------------


def test_init_schema_adds_inputs_hash_to_an_existing_test_runs_table():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_runs (id TEXT PRIMARY KEY, input_hash TEXT)")
    db.init_schema(conn)
    db.init_schema(conn)  # idempotent
    columns = {row[1] for row in conn.execute("PRAGMA table_info(test_runs)")}
    assert "inputs_hash" in columns
