"""Plain functions over the sqlite schema. Every function takes `conn` first.

Writes serialize on the module-level `_lock`; `main.py` exposes this same lock as
`app.state.write_lock` so callers outside this module can serialize compound
operations against it too.
"""

import json
import threading

from app import ids

_lock = threading.Lock()


def row_json(row, column):
    value = row[column]
    if value is None:
        return None
    return json.loads(value)


def _fetch_one(conn, table, id):
    return conn.execute(f"SELECT * FROM {table} WHERE id = ?", (id,)).fetchone()


def _update_fields(conn, table, id, fields: dict) -> None:
    if not fields:
        return
    set_clause = ", ".join(f"{key} = ?" for key in fields)
    values = [*fields.values(), id]
    conn.execute(f"UPDATE {table} SET {set_clause} WHERE id = ?", values)


# --- interviews ---------------------------------------------------------

def create_interview(conn, *, id, display_name, scenario_id, scenario_version, consent_at,
                      expires_at, state_json, stage, active_role):
    with _lock:
        now = ids.now_iso()
        conn.execute(
            """
            INSERT INTO interviews (
                id, created_at, updated_at, display_name, scenario_id, scenario_version,
                consent_at, status, stage, active_role, state_json, expires_at, paused, paused_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'created', ?, ?, ?, ?, 0, 0)
            """,
            (id, now, now, display_name, scenario_id, scenario_version, consent_at, stage,
             active_role, state_json, expires_at),
        )
        conn.commit()
    return _fetch_one(conn, "interviews", id)


def get_interview(conn, id):
    return _fetch_one(conn, "interviews", id)


def update_interview(conn, id, **fields):
    with _lock:
        fields = {**fields, "updated_at": ids.now_iso()}
        _update_fields(conn, "interviews", id, fields)
        conn.commit()
    return _fetch_one(conn, "interviews", id)


def count_active_interviews(conn):
    """Interviews that may still cost something: not yet finished or deleted."""
    return conn.execute(
        "SELECT COUNT(*) AS n FROM interviews WHERE status NOT IN ('finished', 'deleted')"
    ).fetchone()["n"]


def list_expired_interviews(conn, now_iso):
    return conn.execute(
        "SELECT * FROM interviews WHERE (expires_at IS NOT NULL AND expires_at <= ?) OR status = 'deleted'",
        (now_iso,),
    ).fetchall()


def delete_interview_rows(conn, id) -> None:
    with _lock:
        conn.execute(
            "DELETE FROM finding_refs WHERE finding_id IN (SELECT id FROM findings WHERE interview_id = ?)",
            (id,),
        )
        conn.execute("DELETE FROM findings WHERE interview_id = ?", (id,))
        conn.execute("DELETE FROM disputes WHERE interview_id = ?", (id,))
        conn.execute("DELETE FROM assessments WHERE interview_id = ?", (id,))
        conn.execute("DELETE FROM evidence_links WHERE interview_id = ?", (id,))
        conn.execute("DELETE FROM claims WHERE interview_id = ?", (id,))
        conn.execute("DELETE FROM test_runs WHERE interview_id = ?", (id,))
        conn.execute("DELETE FROM code_snapshots WHERE interview_id = ?", (id,))
        conn.execute("DELETE FROM transcript_segments WHERE interview_id = ?", (id,))
        conn.execute("DELETE FROM capabilities WHERE interview_id = ?", (id,))
        conn.execute("DELETE FROM session_events WHERE interview_id = ?", (id,))
        conn.execute("DELETE FROM interviews WHERE id = ?", (id,))
        conn.commit()


# --- capabilities --------------------------------------------------------

def create_capability(conn, *, id, interview_id, kind, token_hash):
    with _lock:
        conn.execute(
            "INSERT INTO capabilities (id, interview_id, kind, token_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (id, interview_id, kind, token_hash, ids.now_iso()),
        )
        conn.commit()
    return _fetch_one(conn, "capabilities", id)


def find_capability(conn, token_hash):
    return conn.execute("SELECT * FROM capabilities WHERE token_hash = ?", (token_hash,)).fetchone()


# --- transcript segments --------------------------------------------------

def insert_segment(conn, *, id, interview_id, speaker, kind, text, stage, generation, status,
                    start_ms=None, end_ms=None, spoken_text=None):
    with _lock:
        next_seq = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM transcript_segments WHERE interview_id = ?",
            (interview_id,),
        ).fetchone()["next_seq"]
        conn.execute(
            """
            INSERT INTO transcript_segments (
                id, interview_id, seq, speaker, kind, text, spoken_text, status, stage,
                generation, start_ms, end_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (id, interview_id, next_seq, speaker, kind, text, spoken_text, status, stage,
             generation, start_ms, end_ms, ids.now_iso()),
        )
        conn.commit()
    return _fetch_one(conn, "transcript_segments", id)


def update_segment(conn, id, **fields):
    with _lock:
        _update_fields(conn, "transcript_segments", id, fields)
        conn.commit()
    return _fetch_one(conn, "transcript_segments", id)


def get_segment(conn, id):
    return _fetch_one(conn, "transcript_segments", id)


def list_segments(conn, interview_id, *, limit=None):
    if limit is None:
        return conn.execute(
            "SELECT * FROM transcript_segments WHERE interview_id = ? ORDER BY seq ASC",
            (interview_id,),
        ).fetchall()
    rows = conn.execute(
        "SELECT * FROM transcript_segments WHERE interview_id = ? ORDER BY seq DESC LIMIT ?",
        (interview_id, limit),
    ).fetchall()
    return list(reversed(rows))


# --- code snapshots --------------------------------------------------------

def insert_snapshot(conn, *, id, interview_id, files_json, content_hash, byte_size):
    with _lock:
        conn.execute(
            """
            INSERT INTO code_snapshots (id, interview_id, files_json, content_hash, byte_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (id, interview_id, files_json, content_hash, byte_size, ids.now_iso()),
        )
        conn.commit()
    return _fetch_one(conn, "code_snapshots", id)


def get_snapshot(conn, id):
    return _fetch_one(conn, "code_snapshots", id)


def list_snapshots(conn, interview_id):
    return conn.execute(
        "SELECT * FROM code_snapshots WHERE interview_id = ? ORDER BY rowid ASC",
        (interview_id,),
    ).fetchall()


def latest_snapshot(conn, interview_id):
    return conn.execute(
        "SELECT * FROM code_snapshots WHERE interview_id = ? ORDER BY rowid DESC LIMIT 1",
        (interview_id,),
    ).fetchone()


# --- test runs ---------------------------------------------------------

def insert_run(conn, *, id, interview_id, snapshot_id, fixture_version, check_version,
                check_ids_json, input_hash, status, executor, replay_of=None, idempotency_key=None,
                inputs_hash=None):
    with _lock:
        conn.execute(
            """
            INSERT INTO test_runs (
                id, interview_id, snapshot_id, fixture_version, check_version, check_ids_json,
                input_hash, inputs_hash, status, executor, replay_of, idempotency_key, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (id, interview_id, snapshot_id, fixture_version, check_version, check_ids_json,
             input_hash, inputs_hash, status, executor, replay_of, idempotency_key, ids.now_iso()),
        )
        conn.commit()
    return _fetch_one(conn, "test_runs", id)


def update_run(conn, id, **fields):
    with _lock:
        _update_fields(conn, "test_runs", id, fields)
        conn.commit()
    return _fetch_one(conn, "test_runs", id)


def get_run(conn, id):
    return _fetch_one(conn, "test_runs", id)


def list_runs(conn, interview_id):
    return conn.execute(
        "SELECT * FROM test_runs WHERE interview_id = ? ORDER BY rowid ASC",
        (interview_id,),
    ).fetchall()


def count_runs(conn, interview_id):
    return conn.execute(
        "SELECT COUNT(*) AS n FROM test_runs WHERE interview_id = ?",
        (interview_id,),
    ).fetchone()["n"]


def active_run(conn, interview_id):
    return conn.execute(
        "SELECT * FROM test_runs WHERE interview_id = ? AND status IN ('queued', 'running') ORDER BY rowid DESC LIMIT 1",
        (interview_id,),
    ).fetchone()


def list_active_runs(conn):
    return conn.execute(
        "SELECT * FROM test_runs WHERE status IN ('queued', 'running') ORDER BY rowid"
    ).fetchall()


def find_run_by_idempotency(conn, interview_id, key):
    return conn.execute(
        "SELECT * FROM test_runs WHERE interview_id = ? AND idempotency_key = ?",
        (interview_id, key),
    ).fetchone()


# --- claims ---------------------------------------------------------------

def insert_claim(conn, *, id, interview_id, segment_id, statement, claim_type, scope, stage, clarity):
    with _lock:
        conn.execute(
            """
            INSERT INTO claims (
                id, interview_id, segment_id, statement, claim_type, scope, stage, clarity,
                interpretation_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'interpretation', ?)
            """,
            (id, interview_id, segment_id, statement, claim_type, scope, stage, clarity, ids.now_iso()),
        )
        conn.commit()
    return _fetch_one(conn, "claims", id)


def get_claim(conn, id):
    return _fetch_one(conn, "claims", id)


def list_claims(conn, interview_id):
    return conn.execute(
        "SELECT * FROM claims WHERE interview_id = ? ORDER BY rowid ASC",
        (interview_id,),
    ).fetchall()


# --- evidence links ---------------------------------------------------------

def insert_link(conn, *, id, interview_id, source_type, source_id, target_type, target_id, relation):
    with _lock:
        conn.execute(
            """
            INSERT INTO evidence_links (
                id, interview_id, source_type, source_id, target_type, target_id, relation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (id, interview_id, source_type, source_id, target_type, target_id, relation, ids.now_iso()),
        )
        conn.commit()
    return _fetch_one(conn, "evidence_links", id)


def list_links(conn, interview_id):
    return conn.execute(
        "SELECT * FROM evidence_links WHERE interview_id = ? ORDER BY rowid ASC",
        (interview_id,),
    ).fetchall()


# --- assessments ---------------------------------------------------------

def insert_assessment(conn, *, id, interview_id, status, rubric_version, prompt_version, model_id, summary):
    with _lock:
        conn.execute(
            """
            INSERT INTO assessments (
                id, interview_id, status, rubric_version, prompt_version, model_id, summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (id, interview_id, status, rubric_version, prompt_version, model_id, summary, ids.now_iso()),
        )
        conn.commit()
    return _fetch_one(conn, "assessments", id)


def latest_assessment(conn, interview_id):
    return conn.execute(
        "SELECT * FROM assessments WHERE interview_id = ? ORDER BY rowid DESC LIMIT 1",
        (interview_id,),
    ).fetchone()


# --- findings ---------------------------------------------------------

def insert_finding(conn, *, id, interview_id, assessment_id, dimension, is_dimension, title,
                    observation_level, explanation, assistance, uncertainty, follow_up, position):
    with _lock:
        conn.execute(
            """
            INSERT INTO findings (
                id, interview_id, assessment_id, dimension, is_dimension, title, observation_level,
                explanation, assistance, uncertainty, follow_up, review_status, review_reasons_json,
                position, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ok', '[]', ?, ?)
            """,
            (id, interview_id, assessment_id, dimension, is_dimension, title, observation_level,
             explanation, assistance, uncertainty, follow_up, position, ids.now_iso()),
        )
        conn.commit()
    return _fetch_one(conn, "findings", id)


def get_finding(conn, id):
    return _fetch_one(conn, "findings", id)


def update_finding(conn, id, **fields):
    with _lock:
        _update_fields(conn, "findings", id, fields)
        conn.commit()
    return _fetch_one(conn, "findings", id)


def list_findings(conn, assessment_id):
    return conn.execute(
        "SELECT * FROM findings WHERE assessment_id = ? ORDER BY is_dimension DESC, position ASC",
        (assessment_id,),
    ).fetchall()


def insert_finding_ref(conn, *, finding_id, ref_type, ref_id, role) -> None:
    with _lock:
        conn.execute(
            "INSERT INTO finding_refs (finding_id, ref_type, ref_id, role) VALUES (?, ?, ?, ?)",
            (finding_id, ref_type, ref_id, role),
        )
        conn.commit()


def list_finding_refs(conn, finding_id):
    return conn.execute(
        "SELECT * FROM finding_refs WHERE finding_id = ? ORDER BY rowid ASC",
        (finding_id,),
    ).fetchall()


def findings_referencing(conn, interview_id, ref_type, ref_id):
    assessment = latest_assessment(conn, interview_id)
    if assessment is None:
        return []
    return conn.execute(
        """
        SELECT DISTINCT f.* FROM findings f
        JOIN finding_refs r ON r.finding_id = f.id
        WHERE f.assessment_id = ? AND r.ref_type = ? AND r.ref_id = ?
        ORDER BY f.is_dimension DESC, f.position ASC
        """,
        (assessment["id"], ref_type, ref_id),
    ).fetchall()


# --- disputes ---------------------------------------------------------

def insert_dispute(conn, *, id, interview_id, segment_id, original_text, proposed_text, reason,
                    affected_finding_ids_json):
    with _lock:
        conn.execute(
            """
            INSERT INTO disputes (
                id, interview_id, segment_id, original_text, proposed_text, reason,
                affected_finding_ids_json, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (id, interview_id, segment_id, original_text, proposed_text, reason,
             affected_finding_ids_json, ids.now_iso()),
        )
        conn.commit()
    return _fetch_one(conn, "disputes", id)


def get_dispute(conn, id):
    return _fetch_one(conn, "disputes", id)


def update_dispute(conn, id, **fields):
    with _lock:
        _update_fields(conn, "disputes", id, fields)
        conn.commit()
    return _fetch_one(conn, "disputes", id)


def list_disputes(conn, interview_id):
    return conn.execute(
        "SELECT * FROM disputes WHERE interview_id = ? ORDER BY rowid ASC",
        (interview_id,),
    ).fetchall()


# --- session events ---------------------------------------------------------

def append_event(conn, interview_id, type, payload: dict) -> dict:
    with _lock:
        next_seq = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM session_events WHERE interview_id = ?",
            (interview_id,),
        ).fetchone()["next_seq"]
        ts = ids.now_iso()
        conn.execute(
            "INSERT INTO session_events (interview_id, seq, ts, type, payload_json) VALUES (?, ?, ?, ?, ?)",
            (interview_id, next_seq, ts, type, json.dumps(payload)),
        )
        conn.commit()
    return {"seq": next_seq, "ts": ts, "type": type, "payload": payload}


def list_events(conn, interview_id, after_seq: int):
    rows = conn.execute(
        "SELECT seq, ts, type, payload_json FROM session_events WHERE interview_id = ? AND seq > ? ORDER BY seq ASC",
        (interview_id, after_seq),
    ).fetchall()
    return [
        {"seq": row["seq"], "ts": row["ts"], "type": row["type"], "payload": json.loads(row["payload_json"])}
        for row in rows
    ]
