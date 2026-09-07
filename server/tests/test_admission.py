"""Admission to `POST /api/interviews`: the demo access key and the creation quotas (A13)."""

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.routes import deps
from app.storage import repo
from tests.conftest import ORIGIN, create_interview

KEY = "let-me-in"
BODY = {"display_name": "Ada Lovelace", "consent": True}


@contextmanager
def client_for(settings, **overrides):
    """A fresh app, so the per-process creation window starts empty."""
    app = create_app(settings.model_copy(update=overrides))
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client, app


@pytest.fixture
def keyed(settings):
    with client_for(settings, DEMO_ACCESS_KEY=KEY) as pair:
        yield pair


# ------------------------------------------------------------------ admission


def test_admission_is_open_without_a_configured_key(client):
    response = client.get("/api/admission")
    assert response.status_code == 200
    assert response.json() == {"access_key_required": False}


def test_admission_reports_a_configured_key(keyed):
    client, _ = keyed
    assert client.get("/api/admission").json() == {"access_key_required": True}


# ------------------------------------------------------------------ access key


def test_no_key_configured_leaves_creation_open(client):
    assert create_interview(client)["id"].startswith("itv_")


def test_a_missing_key_is_refused_with_a_reason(keyed):
    client, _ = keyed
    response = client.post("/api/interviews", json=BODY, headers=ORIGIN)
    assert response.status_code == 403
    assert "access key" in response.json()["detail"]


def test_a_wrong_key_is_refused_and_named_as_wrong(keyed):
    client, _ = keyed
    response = client.post("/api/interviews", json={**BODY, "access_key": "nope"}, headers=ORIGIN)
    assert response.status_code == 403
    assert "not valid" in response.json()["detail"]


def test_the_key_is_accepted_in_the_body(keyed):
    client, _ = keyed
    response = client.post("/api/interviews", json={**BODY, "access_key": KEY}, headers=ORIGIN)
    assert response.status_code == 201, response.text
    assert deps.COOKIE_CANDIDATE in response.cookies


def test_the_key_is_accepted_in_the_header(keyed):
    client, _ = keyed
    response = client.post(
        "/api/interviews", json=BODY, headers={**ORIGIN, deps.ACCESS_KEY_HEADER: KEY}
    )
    assert response.status_code == 201, response.text


def test_a_refused_key_does_not_use_up_the_hourly_window(settings):
    with client_for(settings, DEMO_ACCESS_KEY=KEY, MAX_INTERVIEWS_PER_HOUR=1) as (client, _):
        for _ in range(3):
            client.post("/api/interviews", json=BODY, headers=ORIGIN)
        response = client.post("/api/interviews", json={**BODY, "access_key": KEY}, headers=ORIGIN)
        assert response.status_code == 201, response.text


# ------------------------------------------------------------------ hourly quota


def test_repeated_creates_beyond_the_hourly_window_are_429(settings):
    with client_for(settings, MAX_INTERVIEWS_PER_HOUR=2, MAX_ACTIVE_INTERVIEWS=100) as (client, _):
        for _ in range(2):
            create_interview(client)
        response = client.post("/api/interviews", json=BODY, headers=ORIGIN)
        assert response.status_code == 429
        assert "2 new interviews per hour" in response.json()["detail"]


def test_the_hourly_window_slides(settings):
    quota = deps.CreateQuota(limit_per_hour=1)
    quota.record("1.2.3.4", now=0.0)
    with pytest.raises(Exception) as refused:
        quota.check("1.2.3.4", now=10.0)
    assert refused.value.status_code == 429
    quota.check("1.2.3.4", now=deps.SECONDS_PER_HOUR + 1.0)  # the old create has aged out


def test_the_window_is_keyed_by_the_forwarded_address_but_bounded_in_total():
    quota = deps.CreateQuota(limit_per_hour=2)
    quota.record("10.0.0.1", now=0.0)
    quota.record("10.0.0.1", now=1.0)
    with pytest.raises(Exception) as refused:
        quota.check("10.0.0.1", now=2.0)
    assert refused.value.status_code == 429
    # Another address is also refused: the total window is full.
    with pytest.raises(Exception):
        quota.check("10.0.0.2", now=2.0)


def test_client_ip_prefers_the_first_forwarded_hop(settings):
    with client_for(settings, MAX_INTERVIEWS_PER_HOUR=1, MAX_ACTIVE_INTERVIEWS=100) as (client, app):
        first = client.post(
            "/api/interviews", json=BODY, headers={**ORIGIN, "X-Forwarded-For": "1.1.1.1, 9.9.9.9"}
        )
        assert first.status_code == 201
        assert "1.1.1.1" in app.state.create_quota._windows
        assert "9.9.9.9" not in app.state.create_quota._windows


# ------------------------------------------------------------------ active quota


def test_too_many_active_interviews_is_429(settings):
    with client_for(settings, MAX_ACTIVE_INTERVIEWS=1) as (client, _):
        create_interview(client)
        response = client.post("/api/interviews", json=BODY, headers=ORIGIN)
        assert response.status_code == 429
        assert "1 interviews in progress" in response.json()["detail"]


def test_finished_and_deleted_interviews_free_the_active_quota(settings):
    with client_for(settings, MAX_ACTIVE_INTERVIEWS=1) as (client, app):
        first = create_interview(client)
        repo.update_interview(app.state.db, first["id"], status="finished")
        assert repo.count_active_interviews(app.state.db) == 0
        second = create_interview(client)
        repo.update_interview(app.state.db, second["id"], status="deleted")
        assert repo.count_active_interviews(app.state.db) == 0
        create_interview(client)


def test_the_active_quota_applies_with_a_key_too(settings):
    with client_for(settings, DEMO_ACCESS_KEY=KEY, MAX_ACTIVE_INTERVIEWS=1) as (client, _):
        with_key = {**BODY, "access_key": KEY}
        assert client.post("/api/interviews", json=with_key, headers=ORIGIN).status_code == 201
        assert client.post("/api/interviews", json=with_key, headers=ORIGIN).status_code == 429
