"""Aggregate usage per interview (PRD section 15): minutes, calls, runs, failures.

Only counters live here. No transcript text, no code, no model output: enough
to cost a session, including the failures a candidate never sees, and nothing a
reviewer could mistake for evidence. Every writer adds to the counters in place
so a restart mid-session loses nothing that was already recorded.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

from app import ids
from app.storage import repo

COUNTERS = (
    "voice_seconds",
    "paused_seconds",
    "model_calls",
    "model_input_tokens",
    "model_output_tokens",
    "sandbox_runs",
    "sandbox_seconds",
    "provider_failures",
)

#: Whoever is about to call a provider on an interview's behalf sets this, so
#: the client that makes the call can add to that interview's counters without
#: being told which interview it is serving.
usage_scope: ContextVar = ContextVar("usage_scope", default=None)


def record(conn, interview_id: str, **increments) -> None:
    """Add `increments` (counter name -> amount) to the interview's row, creating it."""
    unknown = set(increments) - set(COUNTERS)
    if unknown:
        raise ValueError(f"unknown usage counters: {sorted(unknown)}")
    now = ids.now_iso()
    with repo._lock:
        conn.execute(
            "INSERT OR IGNORE INTO session_usage (interview_id, updated_at) VALUES (?, ?)",
            (interview_id, now),
        )
        if increments:
            assignments = ", ".join(f"{name} = {name} + ?" for name in increments)
            conn.execute(
                f"UPDATE session_usage SET {assignments}, updated_at = ? WHERE interview_id = ?",
                (*increments.values(), now, interview_id),
            )
        conn.commit()


def get(conn, interview_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM session_usage WHERE interview_id = ?", (interview_id,)
    ).fetchone()
    return usage_view(row) if row is not None else None


def usage_view(row) -> dict:
    view = {"interview_id": row["interview_id"], "updated_at": row["updated_at"]}
    for name in COUNTERS:
        view[name] = row[name] or 0
    return view


def voice_started(conn, interview_id: str) -> None:
    """A paid voice session began now; the seconds are banked when it stops."""
    record(conn, interview_id)
    with repo._lock:
        conn.execute(
            "UPDATE session_usage SET voice_started_at = COALESCE(voice_started_at, ?) "
            "WHERE interview_id = ?",
            (ids.now_iso(), interview_id),
        )
        conn.commit()


def voice_stopped(conn, interview_id: str) -> float:
    """Bank the seconds since the voice session started; returns them (0 if none was open)."""
    row = conn.execute(
        "SELECT voice_started_at FROM session_usage WHERE interview_id = ?", (interview_id,)
    ).fetchone()
    started = row["voice_started_at"] if row is not None else None
    if not started:
        return 0.0
    seconds = max(0.0, (datetime.now(UTC) - datetime.fromisoformat(started)).total_seconds())
    record(conn, interview_id, voice_seconds=seconds)
    with repo._lock:
        conn.execute(
            "UPDATE session_usage SET voice_started_at = NULL WHERE interview_id = ?",
            (interview_id,),
        )
        conn.commit()
    return seconds


@contextmanager
def scope(app, interview_id: str):
    """Attribute every provider call made inside the block to `interview_id`."""

    def sink(**increments) -> None:
        record(app.state.db, interview_id, **increments)

    token = usage_scope.set(sink)
    try:
        yield
    finally:
        usage_scope.reset(token)


def record_in_scope(**increments) -> None:
    """Add to the counters of whichever interview the caller is serving, if any."""
    sink = usage_scope.get()
    if sink is not None:
        sink(**increments)
