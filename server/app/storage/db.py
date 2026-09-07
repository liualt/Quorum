"""SQLite connection setup and schema."""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS interviews (
    id TEXT PRIMARY KEY,
    created_at TEXT,
    updated_at TEXT,
    display_name TEXT,
    scenario_id TEXT,
    scenario_version TEXT,
    consent_at TEXT,
    status TEXT,
    stage TEXT,
    active_role TEXT,
    state_json TEXT,
    agora_channel TEXT,
    agora_agent_id TEXT,
    agora_uid INTEGER,
    agora_agent_uid INTEGER,
    voice_status TEXT,
    model_id TEXT,
    expires_at TEXT,
    paused INTEGER DEFAULT 0,
    paused_ms INTEGER DEFAULT 0,
    paused_at TEXT,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS capabilities (
    id TEXT PRIMARY KEY,
    interview_id TEXT,
    kind TEXT,
    token_hash TEXT UNIQUE,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id TEXT PRIMARY KEY,
    interview_id TEXT,
    seq INTEGER,
    speaker TEXT,
    kind TEXT,
    text TEXT,
    spoken_text TEXT,
    status TEXT,
    stage TEXT,
    generation INTEGER,
    start_ms INTEGER,
    end_ms INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS code_snapshots (
    id TEXT PRIMARY KEY,
    interview_id TEXT,
    files_json TEXT,
    content_hash TEXT,
    byte_size INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS test_runs (
    id TEXT PRIMARY KEY,
    interview_id TEXT,
    snapshot_id TEXT,
    fixture_version TEXT,
    check_version TEXT,
    check_ids_json TEXT,
    input_hash TEXT,
    inputs_hash TEXT,
    status TEXT,
    results_json TEXT,
    stdout_excerpt TEXT,
    stderr_excerpt TEXT,
    executor TEXT,
    sandbox_id TEXT,
    started_at TEXT,
    finished_at TEXT,
    replay_of TEXT,
    differs_from_original INTEGER,
    idempotency_key TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    interview_id TEXT,
    segment_id TEXT,
    statement TEXT,
    claim_type TEXT,
    scope TEXT,
    stage TEXT,
    clarity TEXT,
    interpretation_status TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS evidence_links (
    id TEXT PRIMARY KEY,
    interview_id TEXT,
    source_type TEXT,
    source_id TEXT,
    target_type TEXT,
    target_id TEXT,
    relation TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS assessments (
    id TEXT PRIMARY KEY,
    interview_id TEXT,
    status TEXT,
    rubric_version TEXT,
    prompt_version TEXT,
    model_id TEXT,
    summary TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    interview_id TEXT,
    assessment_id TEXT,
    dimension TEXT,
    is_dimension INTEGER,
    title TEXT,
    observation_level TEXT,
    explanation TEXT,
    assistance TEXT,
    uncertainty TEXT,
    follow_up TEXT,
    review_status TEXT,
    review_reasons_json TEXT,
    position INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS finding_refs (
    finding_id TEXT,
    ref_type TEXT,
    ref_id TEXT,
    role TEXT
);

CREATE TABLE IF NOT EXISTS disputes (
    id TEXT PRIMARY KEY,
    interview_id TEXT,
    segment_id TEXT,
    original_text TEXT,
    proposed_text TEXT,
    reason TEXT,
    affected_finding_ids_json TEXT,
    status TEXT,
    resolution TEXT,
    created_at TEXT,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS session_events (
    interview_id TEXT,
    seq INTEGER,
    ts TEXT,
    type TEXT,
    payload_json TEXT,
    PRIMARY KEY(interview_id, seq)
);

CREATE TABLE IF NOT EXISTS session_usage (
    interview_id TEXT PRIMARY KEY,
    voice_seconds REAL DEFAULT 0,
    paused_seconds REAL DEFAULT 0,
    model_calls INTEGER DEFAULT 0,
    model_input_tokens INTEGER DEFAULT 0,
    model_output_tokens INTEGER DEFAULT 0,
    sandbox_runs INTEGER DEFAULT 0,
    sandbox_seconds REAL DEFAULT 0,
    provider_failures INTEGER DEFAULT 0,
    voice_started_at TEXT,
    updated_at TEXT
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# Columns added after a table first shipped; `CREATE TABLE IF NOT EXISTS` will
# not add them to an existing database, so they are applied one by one.
ADDED_COLUMNS = (
    ("test_runs", "inputs_hash", "TEXT"),
)


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for table, column, declaration in ADDED_COLUMNS:
        present = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in present:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
    conn.commit()
