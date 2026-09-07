"""Retention: expired interviews go, on a timer and at startup, by the same path
the delete route takes."""

import asyncio
import os
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
import pytest

from app import background, cleanup, ids
from app.main import create_app
from app.storage import db, repo
from tests.conftest import ORIGIN, create_interview, save_files, seed_interview, seed_snapshot


async def test_deletion_cancels_only_its_interview_tasks(live_app):
    interview = seed_interview(live_app)
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def work():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    own = background.spawn(live_app, work(), "own", interview_id=interview["id"])
    other = background.spawn(live_app, asyncio.sleep(60), "other", interview_id="other")
    await started.wait()
    await cleanup.delete_interview(live_app, interview["id"])
    assert own.cancelled()
    assert stopped.is_set()
    assert not other.done()
    assert repo.get_interview(live_app.state.db, interview["id"]) is None
    assert interview["id"] not in live_app.state.finish_locks
    assert interview["id"] not in live_app.state.controller._locks


@pytest.mark.parametrize("failure", ["hang", "raise"])
async def test_voice_failure_does_not_prevent_deletion(live_app, monkeypatch, failure):
    class Voice:
        async def stop_agent(self, agent_id):
            if failure == "raise":
                raise RuntimeError("provider failed")
            await asyncio.Event().wait()

    interview = seed_interview(live_app)
    repo.update_interview(live_app.state.db, interview["id"], agora_agent_id="agent")
    live_app.state.voice = Voice()
    monkeypatch.setattr(cleanup, "VOICE_STOP_TIMEOUT_SECONDS", 0.01)
    await asyncio.wait_for(cleanup.delete_interview(live_app, interview["id"]), 1)
    assert repo.get_interview(live_app.state.db, interview["id"]) is None


async def test_late_stream_cannot_recreate_deleted_transcript(live_app):
    interview = seed_interview(live_app)
    started, release = asyncio.Event(), asyncio.Event()

    class SlowModel:
        async def stream_text(self, messages):
            started.set()
            await release.wait()
            yield "late words"

    live_app.state.llm = SlowModel()
    turn = asyncio.create_task(live_app.state.controller.run_turn_collect(
        interview["id"], "I will investigate the cache", source="candidate"
    ))
    await started.wait()
    await cleanup.delete_interview(live_app, interview["id"])
    release.set()
    result = await turn
    assert result["segment_id"] is None
    assert repo.list_segments(live_app.state.db, interview["id"]) == []
    assert repo.list_events(live_app.state.db, interview["id"], 0) == []


async def test_interrupted_deletion_is_recovered_on_expiry(live_app):
    interview = seed_interview(live_app)
    repo.update_interview(live_app.state.db, interview["id"], status="deleted", expires_at=FUTURE)
    assert await cleanup.expire_interviews(live_app, ids.now_iso()) == 1


async def test_deletion_cancels_a_running_executor(live_app, scenario):
    from app.execution import runs

    started, stopped = asyncio.Event(), asyncio.Event()

    class Executor:
        name = "test"

        async def run(self, *args, **kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    live_app.state.executor = Executor()
    interview = seed_interview(live_app)
    snapshot = seed_snapshot(live_app, interview["id"], dict(scenario.editable_files))
    await runs.start_run(live_app, interview["id"], snapshot["id"], ["access_filtering"], None)
    await started.wait()
    await cleanup.delete_interview(live_app, interview["id"])
    assert stopped.is_set()
    assert repo.list_runs(live_app.state.db, interview["id"]) == []
    assert not os.path.exists(snapshot_dir(live_app, interview["id"]))


async def test_delete_waits_for_finish_then_removes_its_assessment(live_app):
    from types import SimpleNamespace
    from app.routes.interviews import finish_interview

    interview = seed_interview(live_app)
    started, release = asyncio.Event(), asyncio.Event()
    original = live_app.state.llm

    class SlowModel:
        model_id = original.model_id

        async def complete_json(self, messages):
            started.set()
            await release.wait()
            return await original.complete_json(messages)

    live_app.state.llm = SlowModel()
    finish = asyncio.create_task(finish_interview(
        interview["id"], SimpleNamespace(app=live_app), row=interview
    ))
    await started.wait()
    deletion = asyncio.create_task(cleanup.delete_interview(live_app, interview["id"]))
    await asyncio.sleep(0)
    assert not deletion.done()
    release.set()
    await asyncio.wait_for(asyncio.gather(finish, deletion), 2)
    assert repo.get_interview(live_app.state.db, interview["id"]) is None
    assert repo.latest_assessment(live_app.state.db, interview["id"]) is None


def iso(moment: datetime) -> str:
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


PAST = iso(datetime.now(UTC) - timedelta(minutes=1))
FUTURE = iso(datetime.now(UTC) + timedelta(days=1))


def snapshot_dir(app, interview_id):
    return os.path.join(app.state.settings.SNAPSHOT_DIR, interview_id)


async def test_expiry_removes_only_what_has_expired(live_app, scenario):
    expired = seed_interview(live_app)
    kept = seed_interview(live_app)
    for row in (expired, kept):
        seed_snapshot(live_app, row["id"], dict(scenario.editable_files))
        repo.append_event(live_app.state.db, row["id"], "stage_changed", {"stage": "briefing"})
    repo.update_interview(live_app.state.db, expired["id"], expires_at=PAST)
    repo.update_interview(live_app.state.db, kept["id"], expires_at=FUTURE)

    removed = await cleanup.expire_interviews(live_app, ids.now_iso())

    assert removed == 1
    assert repo.get_interview(live_app.state.db, expired["id"]) is None
    assert repo.list_events(live_app.state.db, expired["id"], 0) == []
    assert not os.path.exists(snapshot_dir(live_app, expired["id"]))
    assert repo.get_interview(live_app.state.db, kept["id"]) is not None
    assert os.path.isdir(snapshot_dir(live_app, kept["id"]))
    assert await cleanup.expire_interviews(live_app, ids.now_iso()) == 0


async def test_deleting_stops_the_voice_agent_before_the_rows_go(live_app):
    stopped = []

    class StubVoice:
        enabled = True

        async def stop_agent(self, agent_id):
            stopped.append(agent_id)
            # The row was still there to read the id from.
            assert repo.get_interview(live_app.state.db, interview["id"]) is not None

    live_app.state.voice = StubVoice()
    interview = seed_interview(live_app)
    repo.update_interview(live_app.state.db, interview["id"], agora_agent_id="agent_7")

    await cleanup.delete_interview(live_app, interview["id"])

    assert stopped == ["agent_7"]
    assert repo.get_interview(live_app.state.db, interview["id"]) is None


def test_the_delete_route_takes_the_cleanup_path(client, app, candidate, scenario, monkeypatch):
    save_files(client, candidate["id"], dict(scenario.editable_files))
    deleted = []

    async def spy(app_, interview_id):
        deleted.append(interview_id)
        await original(app_, interview_id)

    original = cleanup.delete_interview
    monkeypatch.setattr(cleanup, "delete_interview", spy)

    response = client.delete(f"/api/interviews/{candidate['id']}", headers=ORIGIN)

    assert response.status_code == 204
    assert deleted == [candidate["id"]]
    assert repo.get_interview(app.state.db, candidate["id"]) is None
    assert not os.path.exists(snapshot_dir(app, candidate["id"]))


def test_startup_expires_what_was_left_behind(settings, scenario):
    connection = db.connect(settings.DATABASE_PATH)
    db.init_schema(connection)
    stale = repo.create_interview(
        connection, id="itv_stale", display_name="Old", scenario_id=scenario.id,
        scenario_version=scenario.version, consent_at=ids.now_iso(), expires_at=PAST,
        state_json="{}", stage="briefing", active_role="technical",
    )
    fresh = repo.create_interview(
        connection, id="itv_fresh", display_name="New", scenario_id=scenario.id,
        scenario_version=scenario.version, consent_at=ids.now_iso(), expires_at=FUTURE,
        state_json="{}", stage="briefing", active_role="technical",
    )
    connection.close()

    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=True):
        assert repo.get_interview(app.state.db, stale["id"]) is None
        assert repo.get_interview(app.state.db, fresh["id"]) is not None
        [task] = [t for t in app.state.periodic_tasks if t.get_name() == "expiry"]
        assert not task.done()
    assert task.done()


async def test_expiry_keeps_running_on_its_interval(app, monkeypatch):
    monkeypatch.setattr(cleanup, "EXPIRY_INTERVAL_SECONDS", 0.05)

    async with app.router.lifespan_context(app):
        interview = seed_interview(app)
        repo.update_interview(app.state.db, interview["id"], expires_at=PAST)
        await asyncio.sleep(0.2)

        assert repo.get_interview(app.state.db, interview["id"]) is None


async def test_a_periodic_task_is_never_among_the_awaitable_background_tasks(app):
    async with app.router.lifespan_context(app):
        assert all(task.get_name() != "expiry" for task in app.state.background_tasks)
        assert background.pending(app, "expiry") == []
        assert {t.get_name() for t in app.state.periodic_tasks} == {"expiry", "session_watchdog"}


def test_created_interviews_carry_the_retention_expiry(client, app, candidate):
    row = repo.get_interview(app.state.db, candidate["id"])
    expected = datetime.now(UTC) + timedelta(days=app.state.settings.RETENTION_DAYS)

    assert abs(datetime.fromisoformat(row["expires_at"]) - expected) < timedelta(minutes=1)
    assert create_interview(client)["id"] != candidate["id"]
