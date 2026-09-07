"""A07: the session-lifetime watchdog and the aggregate usage record.

The watchdog ends a live interview at the cap without waiting for a turn; the
usage row counts what a session cost, failures included, and never holds any
transcript or code.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.interview import watchdog
from app.main import create_app
from app.storage import repo, usage
from tests.conftest import (
    FIRST_TURN,
    ORIGIN,
    REPO_ROOT,
    become_reviewer,
    create_interview,
    event_types,
    save_files,
    seed_interview,
    wait_for_run,
)


def ago(minutes: float) -> str:
    moment = datetime.now(UTC) - timedelta(minutes=minutes)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class RecordingVoice:
    enabled = True

    def __init__(self, *, fails: bool = False):
        self.fails = fails
        self.stopped: list[str] = []

    async def stop_agent(self, agent_id: str):
        self.stopped.append(agent_id)
        if self.fails:
            raise RuntimeError("provider failed")


def live_interview(app, *, started_minutes_ago: float, **fields):
    interview = seed_interview(app)
    repo.update_interview(
        app.state.db, interview["id"], status="live", started_at=ago(started_minutes_ago),
        agora_agent_id="agent-1", **fields,
    )
    return interview["id"]


# --- the watchdog -----------------------------------------------------------


async def test_idle_session_is_finished_at_the_cap_without_a_turn(live_app):
    voice = RecordingVoice()
    live_app.state.voice = voice
    over = live_interview(live_app, started_minutes_ago=31)
    under = live_interview(live_app, started_minutes_ago=5)
    usage.voice_started(live_app.state.db, over)

    finished = await watchdog.sweep_sessions(live_app)

    assert finished == [over]
    assert voice.stopped == ["agent-1"]
    assert repo.get_interview(live_app.state.db, over)["status"] == "finished"
    assert repo.get_interview(live_app.state.db, under)["status"] == "live"
    assert repo.latest_assessment(live_app.state.db, over) is not None
    types = event_types(live_app, over)
    assert "session_cap_reached" in types and "interview_finished" in types
    row = usage.get(live_app.state.db, over)
    assert row["voice_seconds"] >= 0 and row["provider_failures"] == 0
    # A second sweep finds nothing left to do.
    assert await watchdog.sweep_sessions(live_app) == []


async def test_paused_time_does_not_count_toward_the_cap(live_app):
    live_app.state.voice = RecordingVoice()
    banked = live_interview(live_app, started_minutes_ago=35, paused_ms=10 * 60 * 1000)
    paused_now = live_interview(live_app, started_minutes_ago=35, paused=1, paused_at=ago(6))
    exhausted = live_interview(live_app, started_minutes_ago=35, paused_ms=4 * 60 * 1000)

    finished = await watchdog.sweep_sessions(live_app)

    assert finished == [exhausted]
    assert repo.get_interview(live_app.state.db, banked)["status"] == "live"
    assert repo.get_interview(live_app.state.db, paused_now)["status"] == "live"


async def test_provider_stop_failure_is_recorded_and_the_interview_still_finishes(live_app):
    voice = RecordingVoice(fails=True)
    live_app.state.voice = voice
    interview_id = live_interview(live_app, started_minutes_ago=31)
    usage.voice_started(live_app.state.db, interview_id)

    assert await watchdog.sweep_sessions(live_app) == [interview_id]

    assert voice.stopped == ["agent-1"]
    assert repo.get_interview(live_app.state.db, interview_id)["status"] == "finished"
    row = usage.get(live_app.state.db, interview_id)
    assert row["provider_failures"] == 1
    assert row["voice_seconds"] >= 0


async def test_a_zero_cap_never_ends_a_session(live_app):
    live_app.state.settings.SESSION_CAP_MINUTES = 0
    interview_id = live_interview(live_app, started_minutes_ago=500)
    assert await watchdog.sweep_sessions(live_app) == []
    assert repo.get_interview(live_app.state.db, interview_id)["status"] == "live"


async def test_the_watchdog_runs_on_its_timer(tmp_path):
    settings = Settings(
        DATABASE_PATH=str(tmp_path / "quorum.db"),
        SNAPSHOT_DIR=str(tmp_path / "snapshots"),
        SESSION_SECRET="test",
        LLM_PROVIDER="scripted",
        EXECUTOR="local",
        SCENARIO_DIR=str(REPO_ROOT / "scenarios"),
        SESSION_WATCHDOG_INTERVAL_SECONDS=0.05,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert any(t.get_name() == "session_watchdog" for t in app.state.periodic_tasks)
        interview_id = live_interview(app, started_minutes_ago=31)
        for _ in range(100):
            await asyncio.sleep(0.05)
            if repo.get_interview(app.state.db, interview_id)["status"] == "finished":
                break
        assert repo.get_interview(app.state.db, interview_id)["status"] == "finished"


# --- the usage record ---------------------------------------------------------


def test_usage_row_is_created_and_updated_in_place(conn):
    usage.record(conn, "itv_1", model_calls=1)
    usage.record(conn, "itv_1", model_calls=2, model_input_tokens=30, sandbox_seconds=1.5)
    row = usage.get(conn, "itv_1")
    assert row["model_calls"] == 3
    assert row["model_input_tokens"] == 30
    assert row["sandbox_seconds"] == 1.5
    assert row["updated_at"]
    with pytest.raises(ValueError):
        usage.record(conn, "itv_1", transcript="never")
    columns = {c[1] for c in conn.execute("PRAGMA table_info(session_usage)")}
    assert not columns & {"text", "files_json", "stdout_excerpt", "summary"}


def test_voice_seconds_are_banked_when_the_session_stops(conn):
    usage.voice_started(conn, "itv_2")
    assert usage.voice_stopped(conn, "itv_2") >= 0
    assert usage.voice_stopped(conn, "itv_2") == 0  # nothing open the second time
    assert usage.get(conn, "itv_2")["voice_seconds"] >= 0


def test_usage_endpoint_reports_the_session_counters(client, app, scenario):
    candidate = create_interview(client)
    interview_id = candidate["id"]
    before = client.get(f"/api/interviews/{interview_id}/usage")
    assert before.status_code == 200
    assert before.json()["model_calls"] == 0 and before.json()["sandbox_runs"] == 0

    assert client.post(f"/api/interviews/{interview_id}/start", headers=ORIGIN).status_code == 200
    turn = client.post(f"/api/interviews/{interview_id}/turns", json={"text": FIRST_TURN}, headers=ORIGIN)
    assert turn.status_code == 200, turn.text
    assert client.post(f"/api/interviews/{interview_id}/pause", json={"paused": True}, headers=ORIGIN).status_code == 200
    assert client.post(f"/api/interviews/{interview_id}/pause", json={"paused": False}, headers=ORIGIN).status_code == 200
    saved = save_files(client, interview_id, dict(scenario.editable_files))
    started = client.post(
        f"/api/interviews/{interview_id}/runs",
        json={"snapshot_id": saved["snapshot_id"], "check_ids": ["access_filtering"]},
        headers=ORIGIN,
    )
    assert started.status_code == 202, started.text
    wait_for_run(client, interview_id, started.json()["id"])

    after = client.get(f"/api/interviews/{interview_id}/usage").json()
    assert after["interview_id"] == interview_id
    assert after["model_calls"] >= 1
    assert after["sandbox_runs"] == 1
    assert after["sandbox_seconds"] >= 0
    assert after["paused_seconds"] >= 0
    assert after["voice_seconds"] == 0  # no voice service in tests
    assert set(after) == {"interview_id", "updated_at", *usage.COUNTERS}

    become_reviewer(client, candidate)
    assert client.get(f"/api/interviews/{interview_id}/usage").status_code == 200
    client.cookies.clear()
    assert client.get(f"/api/interviews/{interview_id}/usage").status_code == 401


def test_finish_counts_the_assessment_model_calls(client, scenario):
    candidate = create_interview(client)
    interview_id = candidate["id"]
    assert client.post(f"/api/interviews/{interview_id}/start", headers=ORIGIN).status_code == 200
    assert client.post(f"/api/interviews/{interview_id}/finish", headers=ORIGIN).status_code == 200
    after = client.get(f"/api/interviews/{interview_id}/usage").json()
    assert after["model_calls"] >= 1
