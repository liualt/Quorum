"""Interview lifecycle, snapshots, and runs over HTTP.

These drive the real routes with the real local executor, so a passing run test
means the whole path — cookie, snapshot, background task, run view — works.
"""

import os
import time

from app.storage import repo
from tests.conftest import ORIGIN, create_interview

INITIAL_CHECK = "cross_company_isolation"
CHANGED_CHECK = "revocation_next_request"


def event_types(app, interview_id):
    return [event["type"] for event in repo.list_events(app.state.db, interview_id, 0)]


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


# --- the interview view ---------------------------------------------------

def test_the_interview_view_reports_the_scenario_and_the_limits(client, app, candidate, scenario):
    body = client.get(f"/api/interviews/{candidate['id']}").json()

    assert body["me"] == "candidate"
    assert body["status"] == "created"
    assert body["stage"] == "briefing"
    assert body["active_role"] == "technical"
    assert body["paused"] is False
    assert body["voice_enabled"] is False
    assert body["voice_status"] == "off"
    assert body["latest_snapshot_id"] is None
    assert body["runs_used"] == 0
    assert body["run_limit"] == app.state.settings.MAX_RUNS_PER_INTERVIEW
    assert body["session_cap_minutes"] == app.state.settings.SESSION_CAP_MINUTES
    assert body["scenario"]["editable_files"] == scenario.editable_files
    assert body["scenario"]["readonly_files"] == scenario.readonly_files

    available = {check["id"]: check["available"] for check in body["scenario"]["checks"]}
    assert available[INITIAL_CHECK] is True
    assert available[CHANGED_CHECK] is False
    assert "expect" not in body["scenario"]["checks"][0]


# --- start and pause ------------------------------------------------------

def test_start_marks_the_interview_live_and_reports_voice_off(client, app, candidate):
    response = client.post(f"/api/interviews/{candidate['id']}/start", headers=ORIGIN)

    assert response.status_code == 200
    assert response.json() == {"voice": {"enabled": False}}

    row = repo.get_interview(app.state.db, candidate["id"])
    assert row["status"] == "live"
    assert row["started_at"] is not None
    assert row["voice_status"] == "off"
    # The greeting opens the transcript whether or not anyone says it aloud.
    assert event_types(app, candidate["id"]) == ["transcript_segment", "voice_status"]


def test_start_twice_keeps_the_original_start_time(client, app, candidate):
    client.post(f"/api/interviews/{candidate['id']}/start", headers=ORIGIN)
    started_at = repo.get_interview(app.state.db, candidate["id"])["started_at"]

    client.post(f"/api/interviews/{candidate['id']}/start", headers=ORIGIN)

    assert repo.get_interview(app.state.db, candidate["id"])["started_at"] == started_at


def test_pause_then_resume_records_paused_time_and_emits(client, app, candidate):
    paused = client.post(
        f"/api/interviews/{candidate['id']}/pause", json={"paused": True}, headers=ORIGIN
    )

    assert paused.status_code == 200
    assert paused.json() == {"paused": True}
    row = repo.get_interview(app.state.db, candidate["id"])
    assert row["paused"] == 1
    assert row["paused_at"] is not None

    resumed = client.post(
        f"/api/interviews/{candidate['id']}/pause", json={"paused": False}, headers=ORIGIN
    )

    assert resumed.json() == {"paused": False}
    row = repo.get_interview(app.state.db, candidate["id"])
    assert row["paused"] == 0
    assert row["paused_at"] is None
    assert row["paused_ms"] >= 0
    assert event_types(app, candidate["id"]) == ["pause_changed", "pause_changed"]


def test_pausing_an_already_paused_interview_emits_nothing(client, app, candidate):
    client.post(f"/api/interviews/{candidate['id']}/pause", json={"paused": True}, headers=ORIGIN)
    client.post(f"/api/interviews/{candidate['id']}/pause", json={"paused": True}, headers=ORIGIN)

    assert event_types(app, candidate["id"]) == ["pause_changed"]


# --- files and snapshots --------------------------------------------------

def test_put_files_rejects_a_path_traversal_name(client, candidate):
    response = client.put(
        f"/api/interviews/{candidate['id']}/files",
        json={"files": {"../../../etc/passwd": "owned"}},
        headers=ORIGIN,
    )

    assert response.status_code == 400


def test_put_files_rejects_a_read_only_scenario_file(client, candidate):
    response = client.put(
        f"/api/interviews/{candidate['id']}/files",
        json={"files": {"index.py": "print('hi')"}},
        headers=ORIGIN,
    )

    assert response.status_code == 400


def test_put_files_over_the_source_limit_is_400(client, app, candidate):
    oversized = "#" * (app.state.settings.SOURCE_LIMIT_BYTES + 1)

    response = client.put(
        f"/api/interviews/{candidate['id']}/files",
        json={"files": {"search.py": oversized}},
        headers=ORIGIN,
    )

    assert response.status_code == 400


def test_put_files_saves_a_snapshot_and_emits_snapshot_saved(client, app, candidate, scenario):
    files = dict(scenario.editable_files)

    saved = save_files(client, candidate["id"], files)

    assert saved["snapshot_id"].startswith("snap_")
    assert saved["content_hash"]
    assert saved["created_at"]

    events = repo.list_events(app.state.db, candidate["id"], 0)
    assert [event["type"] for event in events] == ["snapshot_saved"]
    assert events[0]["payload"] == {
        "snapshot_id": saved["snapshot_id"],
        "content_hash": saved["content_hash"],
        "files": sorted(files),
    }

    view = client.get(f"/api/interviews/{candidate['id']}").json()
    assert view["latest_snapshot_id"] == saved["snapshot_id"]


def test_get_snapshot_returns_the_saved_files(client, candidate, scenario):
    files = dict(scenario.editable_files)
    saved = save_files(client, candidate["id"], files)

    response = client.get(f"/api/interviews/{candidate['id']}/snapshots/{saved['snapshot_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == saved["snapshot_id"]
    assert body["files"] == files
    assert body["content_hash"] == saved["content_hash"]
    assert body["byte_size"] == sum(len(c.encode("utf-8")) for c in files.values())


def test_a_snapshot_of_another_interview_is_404(client, candidate, scenario):
    saved = save_files(client, candidate["id"], dict(scenario.editable_files))
    other = create_interview(client)  # the cookie now belongs to `other`

    response = client.get(f"/api/interviews/{other['id']}/snapshots/{saved['snapshot_id']}")

    assert response.status_code == 404


def test_put_files_after_the_interview_finished_is_409(client, app, candidate):
    repo.update_interview(app.state.db, candidate["id"], status="finished")

    response = client.put(
        f"/api/interviews/{candidate['id']}/files",
        json={"files": {"search.py": "x = 1\n"}},
        headers=ORIGIN,
    )

    assert response.status_code == 409


# --- runs -----------------------------------------------------------------

def test_a_run_of_the_seeded_code_completes_and_fails_the_check(client, candidate, scenario):
    saved = save_files(client, candidate["id"], dict(scenario.editable_files))

    started = client.post(
        f"/api/interviews/{candidate['id']}/runs",
        json={"snapshot_id": saved["snapshot_id"], "check_ids": [INITIAL_CHECK]},
        headers=ORIGIN,
    )

    assert started.status_code == 202
    run = started.json()
    assert run["status"] == "queued"
    assert run["check_ids"] == [INITIAL_CHECK]
    assert run["executor"] == "local"
    assert run["results"] is None

    finished = wait_for_run(client, candidate["id"], run["id"])
    assert finished["status"] == "completed"
    assert [result["check_id"] for result in finished["results"]] == [INITIAL_CHECK]
    assert finished["results"][0]["passed"] is False

    listed = client.get(f"/api/interviews/{candidate['id']}/runs").json()
    assert [row["id"] for row in listed] == [run["id"]]
    assert client.get(f"/api/interviews/{candidate['id']}").json()["runs_used"] == 1


def test_a_check_that_has_not_been_introduced_cannot_be_run(client, candidate, scenario):
    saved = save_files(client, candidate["id"], dict(scenario.editable_files))

    response = client.post(
        f"/api/interviews/{candidate['id']}/runs",
        json={"snapshot_id": saved["snapshot_id"], "check_ids": [CHANGED_CHECK]},
        headers=ORIGIN,
    )

    assert response.status_code == 400
    assert CHANGED_CHECK in response.json()["detail"]


def test_a_run_of_an_unknown_snapshot_is_404(client, candidate):
    response = client.post(
        f"/api/interviews/{candidate['id']}/runs",
        json={"snapshot_id": "snap_missing", "check_ids": [INITIAL_CHECK]},
        headers=ORIGIN,
    )

    assert response.status_code == 404


def test_a_run_of_another_interview_is_404(client, candidate, scenario):
    saved = save_files(client, candidate["id"], dict(scenario.editable_files))
    started = client.post(
        f"/api/interviews/{candidate['id']}/runs",
        json={"snapshot_id": saved["snapshot_id"], "check_ids": [INITIAL_CHECK]},
        headers=ORIGIN,
    ).json()
    wait_for_run(client, candidate["id"], started["id"])
    other = create_interview(client)

    response = client.get(f"/api/interviews/{other['id']}/runs/{started['id']}")

    assert response.status_code == 404


# --- finish and delete ----------------------------------------------------

def test_finish_is_not_implemented_yet(client, candidate):
    response = client.post(f"/api/interviews/{candidate['id']}/finish", headers=ORIGIN)

    assert response.status_code == 501
    assert response.json()["detail"] == "finish is implemented in a later task"


def test_delete_removes_the_rows_and_the_snapshot_directory(client, app, candidate, scenario):
    save_files(client, candidate["id"], dict(scenario.editable_files))
    directory = os.path.join(app.state.settings.SNAPSHOT_DIR, candidate["id"])
    assert os.path.isdir(directory)

    response = client.delete(f"/api/interviews/{candidate['id']}", headers=ORIGIN)

    assert response.status_code == 204
    assert response.content == b""
    assert not os.path.exists(directory)
    assert repo.get_interview(app.state.db, candidate["id"]) is None
    assert repo.list_events(app.state.db, candidate["id"], 0) == []
    assert client.get(f"/api/interviews/{candidate['id']}").status_code == 404
