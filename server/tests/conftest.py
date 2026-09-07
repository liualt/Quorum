import json
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
