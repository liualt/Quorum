import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import ids
from app.config import Settings
from app.main import create_app
from app.scenario import load_scenario
from app.storage import db, repo, snapshots

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPLETE_SOLUTION = REPO_ROOT / "scenarios/document-search/checks/v1/solutions/complete/search.py"

# Every mutation is origin-checked, so route tests have to look like the browser.
ORIGIN = {"Origin": "http://localhost:3000"}

INITIAL_CHECK = "cross_company_isolation"
CHANGED_CHECK = "revocation_next_request"
INITIAL_CHECKS = ["access_filtering", "cross_company_isolation", "repeat_search_efficiency"]

# What the candidate says in the full-flow tests. `ScriptedLLM` reads the first
# as a cross-company diagnosis and the second as a release decision plus a test plan.
FIRST_TURN = "The cache key only uses the query, so another company can see our documents"
SECOND_TURN = "I would not ship it today. I will add the company to the cache key and check it again."


@pytest.fixture
def settings(tmp_path):
    return Settings(
        DATABASE_PATH=str(tmp_path / "quorum.db"),
        SNAPSHOT_DIR=str(tmp_path / "snapshots"),
        SESSION_SECRET="test",
        LLM_PROVIDER="scripted",
        EXECUTOR="local",
        SCENARIO_DIR=str(REPO_ROOT / "scenarios"),
    )


@pytest.fixture
def conn(settings):
    connection = db.connect(settings.DATABASE_PATH)
    db.init_schema(connection)
    yield connection
    connection.close()


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client


@pytest.fixture
async def live_app(app):
    """`app` with its lifespan entered on the test's own event loop.

    `client` runs the lifespan on a portal thread; tests that call service
    functions directly need the loop that schedules background tasks to be the
    loop the test awaits on.
    """
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
def scenario():
    return load_scenario(REPO_ROOT / "scenarios", "document-search")


def create_interview(client, display_name="Ada Lovelace"):
    """Create an interview through the API; `client` keeps the candidate cookie."""
    response = client.post(
        "/api/interviews",
        json={"display_name": display_name, "consent": True},
        headers=ORIGIN,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def candidate(client):
    """An interview created through the API, with `client` holding its cookie."""
    return create_interview(client)


def seed_interview(app, *, state_json="{}"):
    """Insert an interview row directly, bypassing the routes."""
    expires_at = datetime.now(UTC) + timedelta(days=app.state.settings.RETENTION_DAYS)
    return repo.create_interview(
        app.state.db,
        id=ids.new_id("itv"),
        display_name="Ada Lovelace",
        scenario_id=app.state.scenario.id,
        scenario_version=app.state.scenario.version,
        consent_at=ids.now_iso(),
        expires_at=expires_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        state_json=state_json,
        stage="briefing",
        active_role="technical",
    )


def seed_snapshot(app, interview_id, files):
    """Write a snapshot to disk and insert its row, bypassing the routes."""
    snapshot_id = ids.new_id("snap")
    snapshots.write_snapshot(app.state.settings.SNAPSHOT_DIR, interview_id, snapshot_id, files)
    return repo.insert_snapshot(
        app.state.db,
        id=snapshot_id,
        interview_id=interview_id,
        files_json=json.dumps(files),
        content_hash=snapshots.content_hash(files),
        byte_size=sum(len(content.encode("utf-8")) for content in files.values()),
    )


def become_reviewer(client, candidate):
    """Exchange the reviewer token so `client` now holds only the reviewer cookie."""
    client.cookies.clear()
    response = client.post(
        "/api/auth/exchange", json={"token": candidate["reviewer_token"]}, headers=ORIGIN
    )
    assert response.status_code == 200, response.text


def event_types(app, interview_id):
    return [event["type"] for event in repo.list_events(app.state.db, interview_id, 0)]


async def drain(app):
    """Await every background task in flight (runs, follow-ups, claim extractions)."""
    tasks = list(getattr(app.state, "background_tasks", ()))
    if tasks:
        await asyncio.gather(*tasks)


def completed_run(app, interview_id: str, check_ids: list[str], passed: dict | None = None,
                  *, status: str = "completed", replay_of: str | None = None):
    """A terminal run row, results included, without going through the executor."""
    snapshot = repo.latest_snapshot(app.state.db, interview_id) or seed_snapshot(
        app, interview_id, dict(app.state.scenario.editable_files)
    )
    run_id = ids.new_id("run")
    repo.insert_run(
        app.state.db,
        id=run_id,
        interview_id=interview_id,
        snapshot_id=snapshot["id"],
        fixture_version="v1",
        check_version="v1",
        check_ids_json=json.dumps(check_ids),
        input_hash="hash",
        status="queued",
        executor="local",
        replay_of=replay_of,
    )
    results = None
    if status == "completed":
        results = json.dumps(
            [
                {"check_id": check_id, "passed": bool((passed or {}).get(check_id, False)),
                 "steps": [], "search_calls": None, "max_search_calls": None,
                 "efficiency_ok": None, "error": None}
                for check_id in check_ids
            ]
        )
    return repo.update_run(
        app.state.db,
        run_id,
        status=status,
        results_json=results,
        started_at=ids.now_iso(),
        finished_at=ids.now_iso(),
    )


def save_files(client, interview_id, files):
    response = client.put(
        f"/api/interviews/{interview_id}/files", json={"files": files}, headers=ORIGIN
    )
    assert response.status_code == 200, response.text
    return response.json()


def wait_for_run(client, interview_id, run_id, timeout=10.0):
    """Poll until the background task has finished the run."""
    deadline = time.monotonic() + timeout
    while True:
        response = client.get(f"/api/interviews/{interview_id}/runs/{run_id}")
        assert response.status_code == 200, response.text
        body = response.json()
        if body["status"] not in ("queued", "running"):
            return body
        if time.monotonic() > deadline:
            raise AssertionError(f"run {run_id} was still {body['status']} after {timeout}s")
        time.sleep(0.1)


def run_full_interview(client, scenario, *, finish=True):
    """Create, start, speak twice, save the complete solution, run it, and finish.

    Returns the create response, the completed run view, and the finish response
    body (None when `finish` is False). `client` holds the candidate cookie.
    """
    candidate = create_interview(client)
    interview_id = candidate["id"]
    assert client.post(f"/api/interviews/{interview_id}/start", headers=ORIGIN).status_code == 200
    for text in (FIRST_TURN, SECOND_TURN):
        response = client.post(f"/api/interviews/{interview_id}/turns", json={"text": text}, headers=ORIGIN)
        assert response.status_code == 200, response.text
    files = {**scenario.editable_files, "search.py": COMPLETE_SOLUTION.read_text(encoding="utf-8")}
    saved = save_files(client, interview_id, files)
    started = client.post(
        f"/api/interviews/{interview_id}/runs",
        json={"snapshot_id": saved["snapshot_id"], "check_ids": INITIAL_CHECKS},
        headers=ORIGIN,
    )
    assert started.status_code == 202, started.text
    run = wait_for_run(client, interview_id, started.json()["id"])
    assert run["status"] == "completed", run
    finished = None
    if finish:
        response = client.post(f"/api/interviews/{interview_id}/finish", headers=ORIGIN)
        assert response.status_code == 200, response.text
        finished = response.json()
    return {"candidate": candidate, "run": run, "snapshot_id": saved["snapshot_id"], "finish": finished}
