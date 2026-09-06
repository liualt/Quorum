"""Smoke tests for create_app's lifespan wiring (app.state, GET /api/health).

Not listed explicitly in the task-1 file list, but the task context calls out that
health must not crash when scenario/executor/llm/voice/controller are absent, and
the `app`/`client` fixtures otherwise go unexercised in this task.
"""

import threading


def test_health_reports_placeholders_when_later_task_state_is_absent(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "executor": "none",
        "llm_provider": "scripted",
        "llm_model": "",
        "voice_enabled": False,
    }


def test_lifespan_sets_core_app_state(app, client):
    assert app.state.settings is not None
    assert app.state.db is not None
    assert app.state.bus is not None
    assert isinstance(app.state.write_lock, type(threading.Lock()))
