"""Capability cookies, token exchange, and the same-origin guard on mutations.

The interview has no accounts: a cookie holding a capability token is the whole
session. These tests pin the refusals, because getting one of them wrong hands
somebody else's interview to the wrong reader.
"""

from fastapi import Depends

from app.routes import deps
from tests.conftest import ORIGIN, create_interview


def test_create_returns_201_and_sets_the_candidate_cookie(client):
    response = client.post(
        "/api/interviews",
        json={"display_name": "Ada Lovelace", "consent": True},
        headers=ORIGIN,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"].startswith("itv_")
    assert body["candidate_path"] == f"/interview/{body['id']}"
    assert body["reviewer_path"] == f"/review/{body['reviewer_token']}"
    assert client.cookies["quorum_candidate"]

    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    assert "max-age=604800" in cookie  # RETENTION_DAYS
    assert "secure" not in cookie  # every allowed origin here is http


def test_create_without_consent_is_422(client):
    response = client.post(
        "/api/interviews",
        json={"display_name": "Ada Lovelace", "consent": False},
        headers=ORIGIN,
    )

    assert response.status_code == 422


def test_get_without_a_cookie_is_401(client, candidate):
    client.cookies.clear()

    assert client.get(f"/api/interviews/{candidate['id']}").status_code == 401


def test_get_with_an_unknown_cookie_is_401(client, candidate):
    client.cookies.set("quorum_candidate", "not-a-real-token")

    assert client.get(f"/api/interviews/{candidate['id']}").status_code == 401


def test_a_cookie_for_another_interview_is_403(client, candidate):
    create_interview(client)  # replaces the candidate cookie with the new one

    assert client.get(f"/api/interviews/{candidate['id']}").status_code == 403


def test_exchange_sets_the_reviewer_cookie_and_reads_as_the_reviewer(client, candidate):
    client.cookies.clear()

    exchanged = client.post(
        "/api/auth/exchange", json={"token": candidate["reviewer_token"]}, headers=ORIGIN
    )

    assert exchanged.status_code == 200
    assert exchanged.json() == {"interview_id": candidate["id"], "kind": "reviewer"}
    assert client.cookies["quorum_reviewer"]

    view = client.get(f"/api/interviews/{candidate['id']}")
    assert view.status_code == 200
    assert view.json()["me"] == "reviewer"


def test_exchange_with_an_unknown_token_is_404(client):
    response = client.post("/api/auth/exchange", json={"token": "nope"}, headers=ORIGIN)

    assert response.status_code == 404


def test_the_reviewer_may_not_use_a_candidate_route(client, candidate):
    client.cookies.clear()
    client.post("/api/auth/exchange", json={"token": candidate["reviewer_token"]}, headers=ORIGIN)

    response = client.put(
        f"/api/interviews/{candidate['id']}/files",
        json={"files": {"search.py": "x = 1\n"}},
        headers=ORIGIN,
    )

    assert response.status_code == 403


def test_a_mutation_without_an_origin_is_403(client):
    response = client.post("/api/interviews", json={"display_name": "A", "consent": True})

    assert response.status_code == 403


def test_a_mutation_from_an_unlisted_origin_is_403(client):
    response = client.post(
        "/api/interviews",
        json={"display_name": "A", "consent": True},
        headers={"Origin": "http://evil.example"},
    )

    assert response.status_code == 403


def test_a_mutation_may_present_its_origin_in_the_referer(client):
    response = client.post(
        "/api/interviews",
        json={"display_name": "A", "consent": True},
        headers={"Referer": "http://localhost:3000/"},
    )

    assert response.status_code == 201


def test_a_read_does_not_need_an_origin(client, candidate):
    assert client.get(f"/api/interviews/{candidate['id']}").status_code == 200


def test_every_api_mutation_is_origin_checked(client, app, candidate):
    """Sweep the whole surface: a route added later cannot quietly skip this."""
    placeholders = {
        "{interview_id}": candidate["id"],
        "{snapshot_id}": "snap_unused",
        "{run_id}": "run_unused",
    }
    checked = set()
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith("/api"):
            continue
        url = path
        for token, value in placeholders.items():
            url = url.replace(token, value)
        for method in operations:
            if method.upper() in ("GET", "HEAD", "OPTIONS"):
                continue
            response = client.request(method.upper(), url, json={})
            assert response.status_code == 403, f"{method.upper()} {path} answered {response!r}"
            checked.add(f"{method.upper()} {path}")

    assert checked >= {
        "POST /api/interviews",
        "POST /api/auth/exchange",
        "POST /api/interviews/{interview_id}/start",
        "POST /api/interviews/{interview_id}/pause",
        "PUT /api/interviews/{interview_id}/files",
        "POST /api/interviews/{interview_id}/runs",
        "POST /api/interviews/{interview_id}/finish",
        "DELETE /api/interviews/{interview_id}",
    }


def test_require_reviewer_refuses_the_candidate(app, client, candidate):
    """No route needs it until the dispute resolution one does; pin it anyway."""

    @app.get("/api/reviewer-only/{interview_id}")
    async def reviewer_only(row=Depends(deps.require_reviewer)):
        return {"seen": row["id"]}

    assert client.get(f"/api/reviewer-only/{candidate['id']}").status_code == 403

    client.cookies.clear()
    client.post("/api/auth/exchange", json={"token": candidate["reviewer_token"]}, headers=ORIGIN)
    assert client.get(f"/api/reviewer-only/{candidate['id']}").json() == {"seen": candidate["id"]}


def test_hash_token_is_keyed_by_the_session_secret(settings):
    other = settings.model_copy(update={"SESSION_SECRET": "a different secret"})

    assert deps.hash_token(settings, "t") == deps.hash_token(settings, "t")
    assert deps.hash_token(settings, "t") != deps.hash_token(other, "t")
    assert deps.hash_token(settings, "t") != deps.hash_token(settings, "u")


def test_llm_token_is_per_interview_and_keyed_by_its_own_secret(settings):
    settings = settings.model_copy(update={"CUSTOM_LLM_AUTH_SECRET": "llm secret"})
    other = settings.model_copy(update={"CUSTOM_LLM_AUTH_SECRET": "another"})

    assert deps.llm_token(settings, "itv_a") != deps.llm_token(settings, "itv_b")
    assert deps.llm_token(settings, "itv_a") != deps.llm_token(other, "itv_a")
