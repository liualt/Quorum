"""A restart releases abandoned run slots without inventing results."""

import pytest

from app.storage import repo
from tests.conftest import seed_interview, seed_snapshot


@pytest.mark.parametrize("status", ["queued", "running"])
async def test_startup_fails_abandoned_runs_and_preserves_evidence(app, scenario, status):
    async with app.router.lifespan_context(app):
        interview = seed_interview(app)
        snapshot = seed_snapshot(app, interview["id"], dict(scenario.editable_files))
        for run_status in (status, "completed"):
            repo.insert_run(
                app.state.db, id=f"run_{run_status}", interview_id=interview["id"],
                snapshot_id=snapshot["id"], fixture_version=scenario.fixture_version,
                check_version=scenario.check_version, check_ids_json='["access_filtering"]',
                input_hash="original-hash", status=run_status, executor="local",
            )
        before = dict(repo.get_run(app.state.db, "run_completed"))

    async with app.router.lifespan_context(app):
        recovered = repo.get_run(app.state.db, f"run_{status}")
        assert recovered["status"] == "failed"
        assert recovered["finished_at"] is not None
        assert recovered["results_json"] is None
        assert recovered["input_hash"] == "original-hash"
        assert repo.active_run(app.state.db, interview["id"]) is None
        assert dict(repo.get_run(app.state.db, "run_completed")) == before
        assert repo.get_snapshot(app.state.db, snapshot["id"]) is not None
        events = repo.list_events(app.state.db, interview["id"], 0)
        assert len(events) == 1
        assert events[0]["type"] == "run_completed"
        assert events[0]["payload"]["run"]["status"] == "failed"

    async with app.router.lifespan_context(app):
        assert len(repo.list_events(app.state.db, interview["id"], 0)) == 1
