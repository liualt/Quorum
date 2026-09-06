from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage import db

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
