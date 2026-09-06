# Quorum shared interfaces

Every implementation task reads this file. It fixes the names, signatures, JSON shapes, and event types that tasks share. If a task needs to change something here, it must say so in its report so the controller can update this file before the next dispatch.

Spec: [PRD.md](../../../PRD.md). Plan summary: [PLAN.md](../../../PLAN.md).

## Conventions

- Backend: Python 3.12, FastAPI, Pydantic v2, stdlib `sqlite3`. Package root is `server/app`. Import as `from app.storage import repo`.
- IDs: `app.ids.new_id(prefix)` returns `f"{prefix}_{secrets.token_hex(8)}"`. Prefixes: `itv` interview, `cap` capability, `seg` transcript segment, `snap` snapshot, `run` test run, `clm` claim, `lnk` evidence link, `asm` assessment, `fnd` finding, `dsp` dispute.
- Timestamps: ISO 8601 UTC strings with `Z`, produced by `app.ids.now_iso()`.
- JSON columns are TEXT; `repo.row_json(row, column)` parses them.
- Enumerations are plain strings (Literal types), never Python enums, so they serialize directly.

## Settings (`server/app/config.py`)

`class Settings(BaseSettings)` with `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`:

| Field | Default | Meaning |
| --- | --- | --- |
| `AGORA_APP_ID` | `""` | Agora project app id |
| `AGORA_APP_CERTIFICATE` | `""` | Agora app certificate (token minting and REST auth) |
| `AGORA_ASR_MODEL` | `"nova-3"` | Deepgram model, managed credentials |
| `AGORA_TTS_MODEL` | `"speech_2_6_turbo"` | MiniMax model, managed credentials |
| `AGORA_TTS_VOICE_ID` | `"English_captivating_female1"` | MiniMax voice |
| `CUSTOM_LLM_PUBLIC_BASE_URL` | `""` | Public HTTPS origin of this backend (tunnel), no trailing slash |
| `CUSTOM_LLM_AUTH_SECRET` | `""` | HMAC key for per-interview bearer tokens on `/llm/{id}/chat/completions` |
| `LLM_PROVIDER` | `"openai"` | `openai` or `scripted` (test double) |
| `LLM_BASE_URL` | `"https://api.openai.com/v1"` | OpenAI-compatible base URL |
| `LLM_API_KEY` | `""` | |
| `LLM_MODEL` | `""` | Model identifier recorded with every assessment |
| `E2B_API_KEY` | `""` | |
| `EXECUTOR` | `"e2b"` | `e2b` or `local` (development and tests only) |
| `SESSION_SECRET` | `""` | HMAC key for capability token hashes |
| `DATABASE_PATH` | `"./data/quorum.db"` | |
| `SNAPSHOT_DIR` | `"./data/snapshots"` | |
| `ALLOWED_ORIGINS` | `"http://localhost:3000"` | comma separated |
| `RETENTION_DAYS` | `7` | |
| `RUN_TIMEOUT_SECONDS` | `20` | |
| `RUN_OUTPUT_CAP_BYTES` | `65536` | |
| `SOURCE_LIMIT_BYTES` | `102400` | total editable source |
| `MAX_RUNS_PER_INTERVIEW` | `20` | |
| `SESSION_CAP_MINUTES` | `30` | excludes paused time |
| `SCENARIO_DIR` | `"../scenarios"` | relative to `server/` |
| `FOLLOW_UP_DELAY_SECONDS` | `6.0` | quiet time after a run before the panel speaks |
| `SCENARIO_ID` | `"document-search"` | |

`get_settings()` returns a cached instance. Property helpers: `allowed_origins: list[str]`, `voice_configured: bool` (app id and certificate set), `llm_endpoint_enabled: bool` (`CUSTOM_LLM_AUTH_SECRET` and `CUSTOM_LLM_PUBLIC_BASE_URL` set).

## App state (`server/app/main.py`)

`create_app(settings: Settings | None = None) -> FastAPI`. Lifespan initialises and stores on `app.state`:

- `settings`, `db` (sqlite connection), `bus` (`EventBus`), `scenario` (`Scenario`), `llm` (`LLMClient`), `executor` (`Executor`), `voice` (`VoiceService`), `controller` (`InterviewController`), `write_lock` (`threading.Lock`, held by repo writes).

Routers mounted: `/api/...` and `/llm/...`. CORS allows `ALLOWED_ORIGINS` with credentials. `GET /api/health` → `{"status":"ok","executor":name,"llm_provider":str,"llm_model":str,"voice_enabled":bool}`.

## Database (`server/app/storage/db.py`, `repo.py`)

`connect(path: str) -> sqlite3.Connection` (`row_factory=sqlite3.Row`, `check_same_thread=False`, WAL, foreign keys on). `init_schema(conn)` runs `CREATE TABLE IF NOT EXISTS` for:

```sql
interviews(id TEXT PRIMARY KEY, created_at TEXT, updated_at TEXT, display_name TEXT, scenario_id TEXT,
  scenario_version TEXT, consent_at TEXT, status TEXT, stage TEXT, active_role TEXT, state_json TEXT,
  agora_channel TEXT, agora_agent_id TEXT, agora_uid INTEGER, agora_agent_uid INTEGER, voice_status TEXT,
  model_id TEXT, expires_at TEXT, paused INTEGER DEFAULT 0, paused_ms INTEGER DEFAULT 0, paused_at TEXT,
  started_at TEXT, finished_at TEXT)
capabilities(id TEXT PRIMARY KEY, interview_id TEXT, kind TEXT, token_hash TEXT UNIQUE, created_at TEXT)
transcript_segments(id TEXT PRIMARY KEY, interview_id TEXT, seq INTEGER, speaker TEXT, kind TEXT, text TEXT,
  spoken_text TEXT, status TEXT, stage TEXT, generation INTEGER, start_ms INTEGER, end_ms INTEGER, created_at TEXT)
code_snapshots(id TEXT PRIMARY KEY, interview_id TEXT, files_json TEXT, content_hash TEXT, byte_size INTEGER, created_at TEXT)
test_runs(id TEXT PRIMARY KEY, interview_id TEXT, snapshot_id TEXT, fixture_version TEXT, check_version TEXT,
  check_ids_json TEXT, input_hash TEXT, status TEXT, results_json TEXT, stdout_excerpt TEXT, stderr_excerpt TEXT,
  executor TEXT, sandbox_id TEXT, started_at TEXT, finished_at TEXT, replay_of TEXT, differs_from_original INTEGER,
  idempotency_key TEXT, created_at TEXT)
claims(id TEXT PRIMARY KEY, interview_id TEXT, segment_id TEXT, statement TEXT, claim_type TEXT, scope TEXT,
  stage TEXT, clarity TEXT, interpretation_status TEXT, created_at TEXT)
evidence_links(id TEXT PRIMARY KEY, interview_id TEXT, source_type TEXT, source_id TEXT, target_type TEXT,
  target_id TEXT, relation TEXT, created_at TEXT)
assessments(id TEXT PRIMARY KEY, interview_id TEXT, status TEXT, rubric_version TEXT, prompt_version TEXT,
  model_id TEXT, summary TEXT, created_at TEXT)
findings(id TEXT PRIMARY KEY, interview_id TEXT, assessment_id TEXT, dimension TEXT, is_dimension INTEGER,
  title TEXT, observation_level TEXT, explanation TEXT, assistance TEXT, uncertainty TEXT, follow_up TEXT,
  review_status TEXT, review_reasons_json TEXT, position INTEGER, created_at TEXT)
finding_refs(finding_id TEXT, ref_type TEXT, ref_id TEXT, role TEXT)
disputes(id TEXT PRIMARY KEY, interview_id TEXT, segment_id TEXT, original_text TEXT, proposed_text TEXT, reason TEXT,
  affected_finding_ids_json TEXT, status TEXT, resolution TEXT, created_at TEXT, resolved_at TEXT)
session_events(interview_id TEXT, seq INTEGER, ts TEXT, type TEXT, payload_json TEXT, PRIMARY KEY(interview_id, seq))
```

Value vocabularies:

- `interviews.status`: `created | live | finishing | finished | deleted`
- `interviews.stage`: `briefing | initial_review | investigation | changed_condition | release_discussion | assessment`
- `interviews.active_role`: `technical | product | customer`
- `interviews.voice_status`: `off | connecting | connected | disconnected`
- `transcript_segments.speaker`: `candidate | technical | product | customer | system`
- `transcript_segments.kind`: `turn | greeting | hint | scenario_notice | follow_up | clarification`
- `transcript_segments.status`: `complete | interrupted | pending`
- `test_runs.status`: `queued | running | completed | timeout | failed | unavailable`
- `test_runs.executor`: `e2b | local | none`
- `claims.claim_type`: `diagnosis | release_decision | fix_description | test_plan | uncertainty | question | other`
- `claims.scope`: `cross_company | revocation | efficiency | access | general`
- `claims.clarity`: `clear | vague`
- `claims.interpretation_status`: always `interpretation`
- `evidence_links.relation`: `supports | challenges | revises`
- `evidence_links.*_type`, `finding_refs.ref_type`: `segment | run | claim | snapshot`
- `finding_refs.role`: `supports | challenges`
- `findings.dimension`: `understanding_problem | implementing_checking_fix | explaining_consequences | responding_to_new_evidence`
- `findings.observation_level`: `demonstrated | partly_demonstrated | not_observed`
- `findings.review_status`: `ok | needs_review`
- `assessments.status`: `complete | pending`
- `disputes.status`: `open | resolved`

`repo.py` exposes plain functions, each taking `conn` first. All writes acquire `conn` via the caller; the module has `_lock = threading.Lock()` used inside every writing function. Functions:

```
create_interview(conn, *, id, display_name, scenario_id, scenario_version, consent_at, expires_at, state_json, stage, active_role) -> Row
get_interview(conn, id) -> Row | None
update_interview(conn, id, **fields) -> Row
list_expired_interviews(conn, now_iso) -> list[Row]
delete_interview_rows(conn, id) -> None                      # deletes every row of every table for the interview
create_capability(conn, *, id, interview_id, kind, token_hash) -> Row
find_capability(conn, token_hash) -> Row | None
insert_segment(conn, *, id, interview_id, speaker, kind, text, stage, generation, status, start_ms=None, end_ms=None, spoken_text=None) -> Row   # assigns seq = max(seq)+1
update_segment(conn, id, **fields) -> Row
get_segment(conn, id) -> Row | None
list_segments(conn, interview_id, *, limit=None) -> list[Row]  # ordered by seq asc; limit takes the LAST n
insert_snapshot(conn, *, id, interview_id, files_json, content_hash, byte_size) -> Row
get_snapshot(conn, id) -> Row | None
list_snapshots(conn, interview_id) -> list[Row]
latest_snapshot(conn, interview_id) -> Row | None
insert_run(conn, *, id, interview_id, snapshot_id, fixture_version, check_version, check_ids_json, input_hash, status, executor, replay_of=None, idempotency_key=None) -> Row
update_run(conn, id, **fields) -> Row
get_run(conn, id) -> Row | None
list_runs(conn, interview_id) -> list[Row]
count_runs(conn, interview_id) -> int
active_run(conn, interview_id) -> Row | None                  # status in (queued, running)
find_run_by_idempotency(conn, interview_id, key) -> Row | None
insert_claim(conn, *, id, interview_id, segment_id, statement, claim_type, scope, stage, clarity) -> Row
get_claim(conn, id) -> Row | None
list_claims(conn, interview_id) -> list[Row]
insert_link(conn, *, id, interview_id, source_type, source_id, target_type, target_id, relation) -> Row
list_links(conn, interview_id) -> list[Row]
insert_assessment(conn, *, id, interview_id, status, rubric_version, prompt_version, model_id, summary) -> Row
latest_assessment(conn, interview_id) -> Row | None
insert_finding(conn, *, id, interview_id, assessment_id, dimension, is_dimension, title, observation_level, explanation, assistance, uncertainty, follow_up, position) -> Row   # review_status 'ok', review_reasons_json '[]'
update_finding(conn, id, **fields) -> Row
list_findings(conn, assessment_id) -> list[Row]               # ordered by is_dimension desc, position asc
insert_finding_ref(conn, *, finding_id, ref_type, ref_id, role) -> None
list_finding_refs(conn, finding_id) -> list[Row]
findings_referencing(conn, interview_id, ref_type, ref_id) -> list[Row]   # findings of the latest assessment with a ref to (ref_type, ref_id)
insert_dispute(conn, *, id, interview_id, segment_id, original_text, proposed_text, reason, affected_finding_ids_json) -> Row
get_dispute(conn, id) -> Row | None
update_dispute(conn, id, **fields) -> Row
list_disputes(conn, interview_id) -> list[Row]
append_event(conn, interview_id, type, payload: dict) -> dict  # returns {seq, ts, type, payload}; seq = max+1 per interview
list_events(conn, interview_id, after_seq: int) -> list[dict]
row_json(row, column) -> Any
```

## Event bus (`server/app/storage/events.py`)

```python
class EventBus:
    def subscribe(self, interview_id: str) -> asyncio.Queue
    def unsubscribe(self, interview_id: str, queue: asyncio.Queue) -> None
    def publish(self, interview_id: str, event: dict) -> None      # put_nowait to every subscriber
def emit(conn, bus, interview_id, type, payload) -> dict           # append_event then publish; returns the event
```

Event types and payloads (all events carry `{seq, ts, type, payload}`):

| type | payload |
| --- | --- |
| `stage_changed` | `{stage}` |
| `role_changed` | `{role}` |
| `transcript_segment` | `{segment: SegmentView}` |
| `segment_updated` | `{segment: SegmentView}` |
| `snapshot_saved` | `{snapshot_id, content_hash, files: [names]}` |
| `run_started` | `{run: RunView}` |
| `run_completed` | `{run: RunView}` (any terminal status) |
| `pause_changed` | `{paused: bool}` |
| `scenario_notice` | `{segment_id, text, checks_unlocked: [check ids]}` |
| `assessment_completed` | `{assessment_id, status}` |
| `dispute_updated` | `{dispute: DisputeView}` |
| `voice_status` | `{status}` |
| `interview_finished` | `{}` |

## Scenario (`server/app/scenario/loader.py`)

```python
@dataclass
class CheckStep:
    op: str                  # "search" | "revoke"
    user: str
    query: str | None = None
    document: str | None = None
    expect: list[str] | None = None   # document ids, order-insensitive; None for revoke

@dataclass
class Check:
    id: str
    name: str
    description: str
    behavior: str
    introduced_at: str       # "initial" | "changed_condition"
    steps: list[CheckStep]
    max_search_calls: int | None = None

@dataclass
class Scenario:
    id: str
    version: str
    brief: str
    editable_files: dict[str, str]    # "search.py", "cache.py", "permissions.py"
    readonly_files: dict[str, str]    # "index.py", "runner.py", "fixtures/users.json", "fixtures/documents.json", "fixtures/permissions.json"
    fixture_version: str              # "v1"
    check_version: str                # "v1"
    checks: list[Check]
    rubric: dict

def load_scenario(scenario_root: Path, scenario_id: str) -> Scenario
def public_check(check: Check, available: bool) -> dict     # CheckView (no expectations)
```

`CheckView = {id, name, description, behavior, introduced_at, available}`.

## Execution (`server/app/execution/`)

```python
# runner_protocol.py
def build_workspace_files(scenario: Scenario, snapshot_files: dict[str, str]) -> dict[str, str]  # relative path -> content
def build_script(checks: list[Check]) -> str                 # JSON: {"checks":[{"id","steps":[{"op","user","query","document"}]}]}
def parse_output(stdout: str) -> dict                        # last JSON line; raises ValueError
def input_hash(scenario: Scenario, snapshot_hash: str, check_ids: list[str]) -> str   # sha256 over fixture_version, check_version, snapshot_hash, sorted check ids

# checks.py
@dataclass
class StepResult: index: int; op: str; expected: list[str] | None; actual: list[str] | None; ok: bool | None; error: str | None
@dataclass
class CheckResult:
    check_id: str; passed: bool; steps: list[StepResult]; search_calls: int | None
    max_search_calls: int | None; efficiency_ok: bool | None; error: str | None
    def to_dict(self) -> dict
def evaluate(checks: list[Check], parsed: dict) -> list[CheckResult]
def results_differ(a: list[dict], b: list[dict]) -> bool     # compares passed flags and step actual ids per check id

# executor.py
@dataclass
class ExecResult:
    status: str            # "completed" | "timeout" | "failed" | "unavailable"
    stdout: str; stderr: str; exit_code: int | None; sandbox_id: str | None; duration_ms: int
class Executor(Protocol):
    name: str              # "e2b" | "local" | "none"
    async def run(self, files: dict[str, str], script: str, *, timeout_s: int, output_cap: int) -> ExecResult
class LocalExecutor: ...
class E2BExecutor:  def __init__(self, api_key: str) ...
class UnavailableExecutor: ...
def build_executor(settings: Settings) -> Executor

# runs.py
class RunError(Exception): status_code: int; detail: str
async def start_run(app, interview_id: str, snapshot_id: str, check_ids: list[str], idempotency_key: str | None) -> Row
async def execute_run(app, run_id: str) -> None
async def start_replay(app, interview_id: str, run_id: str) -> Row
def run_view(row) -> dict
```

Sandbox layout (both executors): files are written under a working directory; `runner.py` runs with `cwd` = that directory and `python3 runner.py` reading the script on stdin. E2B: `AsyncSandbox.create(timeout=timeout_s + 40, secure=True, allow_internet_access=False, envs={})`, files under `/home/user/app/`, `commands.run("cd /home/user/app && python3 runner.py", stdin=...)` is not available, so write the script to `/home/user/app/script.json` and run `python3 runner.py < script.json` with `timeout=timeout_s`; always `kill()` in `finally`. Local: `tempfile.mkdtemp()`, `subprocess.run([sys.executable, "runner.py"], input=script, cwd=dir, timeout=timeout_s, env={"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"})`.

## Auth (`server/app/routes/deps.py`)

```python
COOKIE_CANDIDATE = "quorum_candidate"; COOKIE_REVIEWER = "quorum_reviewer"
def new_token() -> str                              # secrets.token_urlsafe(32)
def hash_token(settings, token: str) -> str         # hmac sha256 hex keyed by SESSION_SECRET
def set_capability_cookie(response, name, token, settings) -> None   # httponly, samesite=lax, secure if any allowed origin is https, path=/
async def require_candidate(interview_id: str, request: Request) -> Row      # 401 no cookie / unknown, 403 other interview or wrong kind, 404 deleted
async def require_reviewer(interview_id: str, request: Request) -> Row
async def require_participant(interview_id: str, request: Request) -> tuple[Row, str]   # kind
def require_same_origin(request: Request) -> None   # mutations only: Origin (or Referer origin) must be in ALLOWED_ORIGINS, else 403
def llm_token(settings, interview_id) -> str        # hmac sha256 hex keyed by CUSTOM_LLM_AUTH_SECRET
```

## HTTP API

All `/api` routes are JSON. Errors: `{"detail": str}` with 400/401/403/404/409/422/503.

| Route | Auth | Request | Response |
| --- | --- | --- | --- |
| `POST /api/interviews` | none (Origin check) | `{display_name: str, consent: true}` | 201 `{id, candidate_path, reviewer_token, reviewer_path}`; sets candidate cookie |
| `POST /api/auth/exchange` | none | `{token}` | `{interview_id, kind}`; sets the cookie for that kind |
| `GET /api/interviews/{id}` | participant | | `InterviewView` |
| `POST /api/interviews/{id}/start` | candidate | | `{voice: JoinView}` |
| `POST /api/interviews/{id}/pause` | candidate | `{paused: bool}` | `{paused}` |
| `PUT /api/interviews/{id}/files` | candidate | `{files: {name: content}}` | `{snapshot_id, content_hash, created_at}` |
| `GET /api/interviews/{id}/snapshots/{sid}` | participant | | `SnapshotView` |
| `POST /api/interviews/{id}/runs` | candidate | `{snapshot_id, check_ids: [str], idempotency_key?: str}` | 202 `RunView` |
| `GET /api/interviews/{id}/runs` | participant | | `[RunView]` |
| `GET /api/interviews/{id}/runs/{rid}` | participant | | `RunView` |
| `GET /api/interviews/{id}/events?after=N` | participant | | SSE |
| `POST /api/interviews/{id}/turns` | candidate | `{text}` | `{segment_id, role, text, stage}` |
| `POST /api/interviews/{id}/transcript` | candidate | `{speaker: "agent"\|"candidate", status: "end"\|"interrupted", text, turn_id: int}` | `{segment_id: str\|null}` |
| `POST /llm/{id}/chat/completions` | Bearer llm_token | OpenAI chat request | OpenAI SSE chunks |
| `POST /api/interviews/{id}/finish` | candidate | | `{assessment_id, status}` |
| `GET /api/interviews/{id}/assessment` | participant | | `AssessmentView` |
| `POST /api/interviews/{id}/replays` | participant | `{run_id}` | 202 `RunView` |
| `POST /api/interviews/{id}/disputes` | participant | `{segment_id, proposed_text, reason}` | 201 `DisputeView` |
| `POST /api/interviews/{id}/disputes/{did}/resolve` | reviewer | `{resolution}` | `DisputeView` |
| `DELETE /api/interviews/{id}` | participant | | 204 |

Views:

```
InterviewView {id, display_name, status, stage, active_role, paused, created_at, started_at, finished_at,
  me: "candidate"|"reviewer", model_id, voice_enabled: bool, voice_status,
  scenario: {id, version, brief, editable_files: {name: content}, readonly_files: {name: content}, checks: [CheckView]},
  latest_snapshot_id: str|null, runs_used: int, run_limit: int, session_cap_minutes: int}
JoinView {enabled: bool, app_id, channel, uid: int, token, agent_uid: int, agent_id}
SnapshotView {id, files: {name: content}, content_hash, byte_size, created_at}
RunView {id, snapshot_id, status, check_ids: [str], results: [CheckResultDict]|null, executor, sandbox_id,
  started_at, finished_at, replay_of, differs_from_original: bool|null, fixture_version, check_version,
  input_hash, stdout_excerpt, stderr_excerpt, created_at}
CheckResultDict {check_id, passed, steps: [{index, op, expected, actual, ok, error}], search_calls,
  max_search_calls, efficiency_ok, error}
SegmentView {id, seq, speaker, kind, text, spoken_text, status, stage, generation, start_ms, end_ms, created_at}
ClaimView {id, segment_id, statement, claim_type, scope, stage, clarity, interpretation_status, created_at}
LinkView {id, source_type, source_id, target_type, target_id, relation}
Ref {type: "segment"|"run"|"claim"|"snapshot", id}
FindingView {id, dimension, is_dimension: bool, title, observation_level, explanation,
  supporting_refs: [Ref], opposing_refs: [Ref], assistance, uncertainty, follow_up,
  review_status, review_reasons: [str], has_run_ref: bool}
AssessmentView {id, status, model_id, rubric_version, prompt_version, summary, created_at,
  dimensions: [FindingView], findings: [FindingView],
  evidence: {segments: {id: SegmentView}, runs: {id: RunView}, claims: {id: ClaimView},
             snapshots: {id: {id, content_hash, created_at}}, links: [LinkView]},
  disputes: [DisputeView], me: "candidate"|"reviewer", interview: {id, display_name, finished_at}}
DisputeView {id, segment_id, original_text, proposed_text, reason, affected_finding_ids: [str], status,
  resolution, created_at, resolved_at}
```

SSE format: `event: <type>\ndata: <json of {seq, ts, type, payload}>\n\n`; a comment line `: ping` every 15 s; on connect, events with `seq > after` are replayed from the database first.

## LLM client (`server/app/interview/llm_client.py`)

```python
class LLMError(Exception): ...
class LLMClient(Protocol):
    model_id: str
    def stream_text(self, messages: list[dict], *, temperature: float = 0.4, max_tokens: int = 220) -> AsyncIterator[str]
    async def complete_json(self, messages: list[dict], *, max_tokens: int = 1500) -> dict
class OpenAICompatibleClient(LLMClient): def __init__(self, base_url, api_key, model, http_client=None)
class ScriptedLLM(LLMClient): model_id = "scripted-test-double"
def build_llm(settings) -> LLMClient
```

Every system prompt built by `prompts.py` starts with the line `# quorum-task: <spoken_turn|claims|assessment>`; `ScriptedLLM` dispatches on it.

## Prompts (`server/app/interview/prompts.py`)

```python
PROMPT_VERSION = "v1"
ROLE_LABELS = {"technical": "Technical interviewer", "product": "Product manager", "customer": "Customer administrator"}
@dataclass
class TurnContext:
    role: str; stage: str; instruction_kind: str; instruction_note: str
    state_summary: dict            # covered flags, hints count, revocation_introduced
    latest_files: dict[str, str] | None
    runs: list[dict]               # RunView dicts, newest last, at most 3
    pending_runs: list[dict]
    recent_segments: list[dict]    # SegmentView dicts, at most 12
    candidate_text: str
def spoken_turn_messages(ctx: TurnContext) -> list[dict]
def claims_messages(segment: dict, recent: list[dict], prior_claims: list[dict], runs: list[dict]) -> list[dict]
def assessment_messages(rubric: dict, record: dict) -> list[dict]
def greeting_text(display_name: str) -> str
def agent_instructions() -> str
```

## Controller (`server/app/interview/`)

```python
# state.py
@dataclass
class ControllerState:
    stage: str = "briefing"; active_role: str = "technical"; generation: int = 0
    candidate_turns_in_stage: int = 0; turns_total: int = 0
    role_turns_in_stage: dict[str, int] = field(default_factory=dict)
    covered: dict[str, bool] = field(default_factory=lambda: {"initial_explanation": False, "release_decision": False,
        "cross_company": False, "revocation": False, "final_recommendation": False})
    hints_given: list[str] = field(default_factory=list)      # segment ids
    revocation_introduced: bool = False; revocation_segment_id: str | None = None
    discussed_run_ids: list[str] = field(default_factory=list); pending_run_ids: list[str] = field(default_factory=list)
    last_candidate_segment_id: str | None = None; last_role_segment_id: str | None = None
    last_clarity: str = "clear"; contradiction_note: str | None = None
    def to_json(self) -> str
    @classmethod
    def from_json(cls, text: str | None) -> "ControllerState"

# stages.py
STAGES = ["briefing", "initial_review", "investigation", "changed_condition", "release_discussion", "assessment"]
@dataclass
class Facts:
    completed_runs: int; revocation_run_completed: bool; elapsed_minutes: float
    latest_run_passed: dict[str, bool]      # check_id -> passed for the newest completed run ({} if none)
def next_stage(state: ControllerState, facts: Facts) -> str

# roles.py
@dataclass
class TurnInstruction:
    kind: str    # normal | hint | scenario_notice | clarify | run_follow_up | wrap_up | probe_deeper
    note: str
def select_role(state: ControllerState, facts: Facts) -> tuple[str, TurnInstruction]

# controller.py
class InterviewController:
    def __init__(self, app: FastAPI)
    def load_state(self, interview_id) -> ControllerState
    def save_state(self, interview_id, state) -> None
    def current_generation(self, interview_id) -> int
    def allowed_check_ids(self, interview_id) -> list[str]
    async def run_turn(self, interview_id: str, user_text: str, *, source: str) -> AsyncIterator[str]
    async def run_turn_collect(self, interview_id: str, user_text: str, *, source: str) -> dict   # {segment_id, role, text, stage}
    async def on_run_completed(self, interview_id: str, run_id: str) -> None
    async def apply_transcript_status(self, interview_id, *, speaker, status, text, turn_id) -> str | None
    def facts(self, interview_id) -> Facts
```

`run_turn` contract: records the candidate segment, advances stage, selects role, streams spoken text chunks, records the role segment, marks pending runs discussed, persists state, schedules claim extraction (`app.state.claims_task`, see evidence). If the generation changes mid-stream, the generator stops and the role segment is stored with `status="interrupted"`.

## Voice (`server/app/interview/agora.py`)

```python
@dataclass
class JoinData: enabled: bool; app_id: str = ""; channel: str = ""; uid: int = 0; token: str = ""; agent_uid: int = 0; agent_id: str = ""
class VoiceService(Protocol):
    enabled: bool
    def make_join(self, interview_id: str) -> JoinData
    async def start_agent(self, join: JoinData, *, llm_url: str, llm_token: str, greeting: str, instructions: str) -> str
    async def stop_agent(self, agent_id: str) -> None
    async def say(self, agent_id: str, text: str, *, interrupt: bool = False) -> None
    async def interrupt(self, agent_id: str) -> None
class AgoraVoiceService(VoiceService): def __init__(self, settings)
class NullVoiceService(VoiceService): enabled = False
def build_voice(settings) -> VoiceService
```

## Evidence (`server/app/evidence/`)

```python
# claims.py
async def extract_and_store_claims(app, interview_id: str, segment_id: str) -> list[Row]
# links.py
def link_run_to_claims(conn, interview_id: str, run_row) -> list[Row]
def link_challenge(conn, interview_id: str, role_segment_id: str, scopes: list[str]) -> list[Row]
SCOPE_TO_CHECK = {"cross_company": "cross_company_isolation", "revocation": "revocation_next_request",
                  "efficiency": "repeat_search_efficiency", "access": "access_filtering"}
# validate.py
def validate_assessment_payload(conn, interview_id: str, payload: dict) -> list[str]
# findings.py
async def build_assessment(app, interview_id: str) -> Row
def assessment_view(conn, interview_id: str, me: str) -> dict
# disputes.py
def create_dispute(conn, bus, interview_id, segment_id, proposed_text, reason) -> Row
def resolve_dispute(conn, bus, interview_id, dispute_id, resolution) -> Row
def mark_findings_needing_review(conn, bus, interview_id, ref_type, ref_id, reason) -> list[str]
# app.state hooks set in main.py by Task 8 (callables used by earlier modules through getattr):
#   app.state.claims_extractor(app, interview_id, segment_id)  -> coroutine
#   app.state.link_run(interview_id, run_row)
#   app.state.mark_findings_needing_review(interview_id, ref_type, ref_id, reason)
def clear_review_reason(conn, bus, interview_id, reason) -> None
# cleanup.py (server/app/cleanup.py)
def delete_interview(app, interview_id: str) -> None
def expire_interviews(app, now_iso: str) -> int
```

Assessment JSON the model must return:

```json
{"summary": "...",
 "dimensions": [{"dimension": "understanding_problem", "title": "...", "observation_level": "demonstrated|partly_demonstrated|not_observed",
                 "explanation": "...", "supporting_refs": [{"type": "segment|run|claim|snapshot", "id": "..."}],
                 "opposing_refs": [], "assistance": "...", "uncertainty": "...", "follow_up": "..."}],
 "findings": [{"dimension": "...", "title": "...", "observation_level": "...", "explanation": "...",
               "supporting_refs": [], "opposing_refs": [], "assistance": "...", "uncertainty": "...", "follow_up": "..."}]}
```

Claims JSON the model must return:

```json
{"claims": [{"statement": "...", "claim_type": "diagnosis", "scope": "cross_company", "clarity": "clear", "revises_claim_id": null}],
 "covered": {"initial_explanation": true, "release_decision": false, "cross_company": true, "revocation": false, "final_recommendation": false},
 "contradiction_note": null}
```

## Web (`web/lib/types.ts`)

TypeScript interfaces named exactly as the views above (`InterviewView`, `JoinView`, `SnapshotView`, `RunView`, `CheckResultDict`, `SegmentView`, `ClaimView`, `LinkView`, `Ref`, `FindingView`, `AssessmentView`, `DisputeView`, `CheckView`, `SessionEvent {seq, ts, type, payload}`). `web/lib/api.ts` exports one function per route with the same names as the route purposes: `createInterview`, `exchangeToken`, `getInterview`, `startInterview`, `setPaused`, `saveFiles`, `getSnapshot`, `startRun`, `listRuns`, `getRun`, `sendTurn`, `reportTranscript`, `finishInterview`, `getAssessment`, `startReplay`, `createDispute`, `resolveDispute`, `deleteInterview`. All use `fetch` with `credentials: "same-origin"` against `/api/...` (proxied by Next.js rewrites to the backend).
