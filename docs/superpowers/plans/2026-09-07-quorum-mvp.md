# Quorum MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the hackathon release of Quorum: a live AI interview where a candidate edits and runs a small Python app while a three-role AI panel questions them, ending in an evidence-linked, replayable, correctable assessment.

**Architecture:** One Next.js 16 app proxies `/api/*` to one FastAPI worker. Agora Conversational AI calls the backend's custom-LLM endpoint per candidate turn; the backend's controller picks stage and role, asks one OpenAI-compatible model for spoken text, and records every segment, snapshot, run, claim, link, and finding in SQLite. E2B executes runs and replays in a fresh sandbox.

**Tech Stack:** Next.js 16, TypeScript, Tailwind, `@monaco-editor/react`, `@xyflow/react`, `agora-rtc-sdk-ng`, `agora-rtc-react`, `agora-rtm`, `agora-agent-client-toolkit`, `@phosphor-icons/react`; FastAPI, Pydantic v2, pydantic-settings, `openai`, `agora-agents`, `e2b`, `sse-starlette`, pytest, Playwright.

**Spec:** [PRD.md](../../../PRD.md) (binding). Plan summary and assumptions: [PLAN.md](../../../PLAN.md). Shared names and shapes: [2026-09-07-quorum-interfaces.md](2026-09-07-quorum-interfaces.md) (every task reads it; call it "the interfaces doc"). Frontend design system: `design-system/quorum/MASTER.md`.

## Global Constraints

- Backend runs as a single worker; SQLite plus a snapshot directory are the only stores. Python 3.12 managed with `uv` inside `server/`.
- Limits (PRD §9): 20-second execution deadline, 64 KB output cap, 100 KB total editable source, one active run per interview, 20 runs per session. A timeout is an execution failure, never a result.
- Sandboxes: fresh per run or replay, `allow_internet_access=False`, `secure=True`, no application or provider secrets passed in, killed in `finally`.
- The backend never trusts a printed pass/fail; it compares returned document ids to expectations held outside candidate code.
- Candidate source and transcript are untrusted input: never change the rubric, never select host paths, never executed on the host outside the local executor's temp directory.
- Application code controls stage transitions, permissions, execution, evidence identifiers, and replay. The model only writes spoken text and drafts interpretations.
- Stream only spoken text to Agora. No tool arguments, ids, or assessment objects in the speech channel.
- Evidence links are rows with validated references and relation `supports | challenges | revises`. Findings reference only records that exist for that interview.
- Observation levels are exactly `demonstrated | partly_demonstrated | not_observed`; review status `ok | needs_review` is separate. No overall score, no ranking, no personality, emotion, accent, or honesty judgments anywhere in prompts or UI.
- Replay never modifies the original run; a differing replay marks dependent findings `needs_review` and keeps both results. A dispute never modifies the original segment; dependent findings become `needs_review`.
- Auth: capability tokens are random, stored hashed, exchanged for HTTP-only cookies; an interview id alone never grants access; cookie-authenticated mutations require a same-origin `Origin`. The Agora endpoint requires a per-interview bearer token.
- AI disclosure before consent and persistent "AI" role labels in the UI.
- Default retention 7 days with immediate deletion; expiry cleanup removes rows and snapshot files.
- Test doubles (`LLM_PROVIDER=scripted`, `EXECUTOR=local`) are labeled as test or development paths in code and README; they are never described as the demo path.
- Commit after every task with a conventional message; never commit `.env` or `data/`.

## File structure

```
server/                          uv project (pyproject.toml, .python-version 3.12)
  app/main.py                    app factory, lifespan, routers, health
  app/config.py                  Settings
  app/ids.py                     new_id, now_iso
  app/storage/db.py              connect, init_schema
  app/storage/repo.py            row functions (interfaces doc)
  app/storage/events.py          EventBus, emit
  app/storage/snapshots.py       validate_files, write_snapshot, read_snapshot, content_hash, delete_interview_dir
  app/scenario/loader.py         Scenario, Check, load_scenario, public_check
  app/execution/runner_protocol.py
  app/execution/checks.py
  app/execution/executor.py      LocalExecutor, E2BExecutor, UnavailableExecutor, build_executor
  app/execution/runs.py          start_run, execute_run, start_replay, run_view
  app/routes/deps.py             auth helpers
  app/routes/auth.py             POST /api/auth/exchange
  app/routes/interviews.py       create, get, start, pause, finish, delete
  app/routes/files.py            PUT files, GET snapshot
  app/routes/runs.py             runs, replays
  app/routes/events.py           SSE
  app/routes/turns.py            text turns, transcript status
  app/routes/llm.py              Agora custom LLM endpoint
  app/routes/assessment.py       assessment, disputes
  app/interview/llm_client.py    OpenAICompatibleClient, ScriptedLLM, build_llm
  app/interview/prompts.py       prompt builders
  app/interview/state.py         ControllerState
  app/interview/stages.py        next_stage
  app/interview/roles.py         select_role
  app/interview/controller.py    InterviewController
  app/interview/agora.py         AgoraVoiceService, NullVoiceService
  app/evidence/claims.py, links.py, validate.py, findings.py, disputes.py
  app/cleanup.py                 delete_interview, expire_interviews
  tests/conftest.py              app fixture (scripted LLM, local executor, temp dirs), client, helpers
  tests/test_*.py
scenarios/document-search/
  brief.md
  application/search.py, cache.py, permissions.py     editable
  application/index.py                                read-only
  fixtures/v1/users.json, documents.json, permissions.json
  checks/v1/checks.json, runner.py
  checks/v1/solutions/{partial,complete,disabled}/search.py   reference solutions for tests
  rubric.json
web/                             Next.js 16 app (app router, TypeScript, Tailwind)
  app/page.tsx                   disclosure + consent + create
  app/interview/[id]/page.tsx    workspace
  app/assessment/[id]/page.tsx   report
  app/review/[token]/page.tsx    reviewer exchange
  components/interview/          RoleLabel, Captions, MicControls, TextInput, ScenarioNotice, SessionTimer
  components/workspace/          FileList, CodeEditor, RunPanel, ResultsPanel, BriefPanel
  components/evidence/           DimensionCard, FindingList, EvidenceMap, EvidenceDrawer, DiffView, RunCompare, DisputeForm, DisputeList
  lib/api.ts, lib/types.ts, lib/events.ts, lib/voice.ts
  tests/e2e.spec.ts              Playwright
scripts/seed_demo.py, scripts/smoke_test.py
.env.example, README.md, PLAN.md
```

---

### Task 1: Backend scaffold, settings, database, event bus

**Files:**
- Create: `server/pyproject.toml`, `server/.python-version`, `server/app/__init__.py`, `server/app/main.py`, `server/app/config.py`, `server/app/ids.py`, `server/app/storage/__init__.py`, `server/app/storage/db.py`, `server/app/storage/repo.py`, `server/app/storage/events.py`, `server/tests/__init__.py`, `server/tests/conftest.py`, `server/tests/test_storage.py`, `server/tests/test_events.py`, `.gitignore`
- Interfaces: implement exactly the Settings, `create_app`, `db.py`, `repo.py`, and `events.py` sections of the interfaces doc.

**Produces:** `create_app(settings)`, `app.state.{settings, db, bus, write_lock}`, `repo.*`, `EventBus`, `emit`, `GET /api/health`. Later tasks add `scenario`, `llm`, `executor`, `voice`, `controller` to `app.state` inside `main.py`'s lifespan; leave clearly marked hook points (`# task 2: scenario`, etc.) so those tasks only edit `main.py` in one place.

- [ ] **Step 1: Create the uv project.** `cd server && uv init --no-workspace --python 3.12 --name quorum-server` then set dependencies in `pyproject.toml`: `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `pydantic-settings`, `sse-starlette`, `httpx`, `openai`, `agora-agents`, `e2b`, `python-dotenv`; dev: `pytest`, `pytest-asyncio`, `anyio`. Set `[tool.pytest.ini_options] asyncio_mode = "auto"`, `testpaths = ["tests"]`. Run `uv sync`. Add `.gitignore` at repo root: `node_modules/`, `.next/`, `.venv/`, `__pycache__/`, `data/`, `.env`, `.env.local`, `server/.env`, `web/.env.local`, `.superpowers/`, `test-results/`, `playwright-report/`.
- [ ] **Step 2: Write failing tests** in `tests/test_storage.py`: schema creates all tables listed in the interfaces doc; `create_interview` then `get_interview` round-trips; `insert_segment` assigns increasing `seq` per interview (two interviews interleaved keep independent sequences); `list_segments(limit=2)` returns the last two in ascending order; `append_event` returns increasing `seq` and `list_events(after_seq)` filters; `delete_interview_rows` removes rows from every table (insert one row per table first); `findings_referencing` finds a finding by ref. In `tests/test_events.py`: `emit` publishes to two subscribers and persists; `unsubscribe` stops delivery. `conftest.py` provides `settings` (temp `DATABASE_PATH` and `SNAPSHOT_DIR`, `SESSION_SECRET="test"`, `LLM_PROVIDER="scripted"`, `EXECUTOR="local"`, `SCENARIO_DIR` pointing at the repo's `scenarios/`), `conn`, and `app` via `create_app(settings)` (the app fixture must keep working when later tasks add state; use `TestClient(app)` as `client` with `raise_server_exceptions=True`).
- [ ] **Step 3: Run tests, confirm they fail** (`uv run pytest -q`).
- [ ] **Step 4: Implement** `ids.py`, `config.py`, `db.py`, `repo.py`, `events.py`, `main.py`. `main.py` lifespan: `os.makedirs` for data dirs, `connect` + `init_schema`, `EventBus()`, `write_lock`. Health route reports placeholders `executor="none"`, `llm_provider=settings.LLM_PROVIDER`, `llm_model=settings.LLM_MODEL`, `voice_enabled=settings.voice_configured` until later tasks fill real objects. `repo.update_*` functions build `SET` clauses from kwargs and always set `updated_at` where the table has it.
- [ ] **Step 5: Run tests, confirm they pass; output pristine** (no warnings; configure `filterwarnings` only for third-party deprecation noise you can name).
- [ ] **Step 6: Commit** `feat(server): scaffold app, settings, sqlite schema, event bus`.

---

### Task 2: Scenario package and runner

**Files:**
- Create: `scenarios/document-search/brief.md`, `application/{search.py,cache.py,permissions.py,index.py}`, `fixtures/v1/{users.json,documents.json,permissions.json}`, `checks/v1/checks.json`, `checks/v1/runner.py`, `checks/v1/solutions/{partial,complete,disabled}/search.py`, `rubric.json`, `server/app/scenario/__init__.py`, `server/app/scenario/loader.py`, `server/tests/test_scenario.py`
- Modify: `server/app/main.py` (lifespan hook: `app.state.scenario = load_scenario(...)`; health unchanged)

**Consumes:** Task 1 app factory. **Produces:** `Scenario`, `Check`, `CheckStep`, `load_scenario`, `public_check` per the interfaces doc; the runner's stdout protocol (below).

The scenario content is fixed by this task; implement it verbatim.

- [ ] **Step 1: Application files** (`scenarios/document-search/application/`).

`index.py` (read-only during interviews):

```python
"""Expensive document index. Not editable during the interview.

Every call to expensive_search is counted so the checks can measure how
much repeated work a cache avoids.
"""
import json
import os
import re

FIXTURE_DIR = os.environ.get(
    "QUORUM_FIXTURE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures"),
)

SEARCH_CALLS = 0


def _load_documents():
    with open(os.path.join(FIXTURE_DIR, "documents.json"), encoding="utf-8") as fh:
        return json.load(fh)["documents"]


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def expensive_search(query):
    """Return every document whose title or body contains all query words."""
    global SEARCH_CALLS
    SEARCH_CALLS += 1
    wanted = _tokens(query)
    hits = []
    for doc in _load_documents():
        haystack = _tokens(doc["title"] + " " + doc["body"])
        if wanted and wanted <= haystack:
            hits.append({"id": doc["id"], "title": doc["title"], "company_id": doc["company_id"]})
    return hits
```

`permissions.py` (editable):

```python
"""Company membership and document permissions.

Data comes from the fixture files. The caller never supplies a company
identifier; it is derived from the authenticated user.
"""
import json
import os

import index

_users = None
_grants = None


def _load():
    global _users, _grants
    if _users is None:
        with open(os.path.join(index.FIXTURE_DIR, "users.json"), encoding="utf-8") as fh:
            _users = {u["id"]: u for u in json.load(fh)["users"]}
        with open(os.path.join(index.FIXTURE_DIR, "permissions.json"), encoding="utf-8") as fh:
            _grants = {(g["user_id"], g["document_id"]) for g in json.load(fh)["grants"]}


def company_of(user_id):
    _load()
    return _users[user_id]["company_id"]


def can_read(user_id, document_id):
    _load()
    return (user_id, document_id) in _grants


def revoke(user_id, document_id):
    """Remove a user's access to one document. Called by admin tooling."""
    _load()
    _grants.discard((user_id, document_id))
```

`cache.py` (editable):

```python
"""In-memory cache for search results.

Added in the recent caching change so repeated searches skip the
expensive index scan.
"""
_entries = {}


def get(key):
    return _entries.get(key)


def put(key, value):
    _entries[key] = value


def clear():
    _entries.clear()
```

`search.py` (editable, contains the seeded bug):

```python
"""Document search entry point used by the API layer.

search(user_id, query) returns the documents the authenticated user may
read, as a list of {"id", "title"} dictionaries.
"""
import cache
import index
import permissions


def _normalise(query):
    return " ".join(query.lower().split())


def search(user_id, query):
    key = _normalise(query)
    cached = cache.get(key)
    if cached is not None:
        return cached

    results = []
    for doc in index.expensive_search(query):
        if permissions.can_read(user_id, doc["id"]):
            results.append({"id": doc["id"], "title": doc["title"]})

    cache.put(key, results)
    return results
```

- [ ] **Step 2: Fixtures** (`fixtures/v1/`).

`users.json`: `{"users":[{"id":"u_alice","name":"Alice Moreno","company_id":"co_acme"},{"id":"u_bob","name":"Bob Tan","company_id":"co_acme"},{"id":"u_carol","name":"Carol Osei","company_id":"co_birch"}]}`

`documents.json`:

```json
{"documents":[
 {"id":"doc_acme_q3","company_id":"co_acme","title":"Q3 quarterly report","body":"Acme revenue and margin summary for the third quarter."},
 {"id":"doc_acme_forecast","company_id":"co_acme","title":"Finance quarterly forecast","body":"Acme confidential forecast prepared by finance."},
 {"id":"doc_acme_onboarding","company_id":"co_acme","title":"Engineering onboarding handbook","body":"How new Acme engineers get set up."},
 {"id":"doc_birch_q3","company_id":"co_birch","title":"Q3 quarterly report","body":"Birch revenue and hiring summary for the third quarter."},
 {"id":"doc_birch_roadmap","company_id":"co_birch","title":"Product roadmap quarterly review","body":"Birch roadmap review for the coming quarter."},
 {"id":"doc_birch_handbook","company_id":"co_birch","title":"Employee handbook","body":"Birch policies for all employees."}
]}
```

`permissions.json`: grants for `u_alice`: `doc_acme_q3, doc_acme_forecast, doc_acme_onboarding`; `u_bob`: `doc_acme_q3, doc_acme_onboarding`; `u_carol`: `doc_birch_q3, doc_birch_roadmap, doc_birch_handbook`. Shape: `{"grants":[{"user_id":"u_alice","document_id":"doc_acme_q3"}, ...]}`.

- [ ] **Step 3: Checks** (`checks/v1/checks.json`):

```json
{"version":"v1","checks":[
 {"id":"access_filtering","name":"Permission filtering","behavior":"A user can see only documents allowed by their current permissions.","description":"Three searches by Acme users with different grants.","introduced_at":"initial",
  "steps":[{"op":"search","user":"u_alice","query":"quarterly","expect":["doc_acme_q3","doc_acme_forecast"]},
           {"op":"search","user":"u_bob","query":"handbook","expect":["doc_acme_onboarding"]},
           {"op":"search","user":"u_bob","query":"forecast","expect":[]}]},
 {"id":"cross_company_isolation","name":"Cross-company isolation","behavior":"Identical searches by different companies cannot leak documents across companies.","description":"Alice at Acme and Carol at Birch run the same query.","introduced_at":"initial",
  "steps":[{"op":"search","user":"u_alice","query":"quarterly report","expect":["doc_acme_q3"]},
           {"op":"search","user":"u_carol","query":"quarterly report","expect":["doc_birch_q3"]}]},
 {"id":"revocation_next_request","name":"Revocation takes effect","behavior":"Removing a user's access takes effect on the next request, including a cached request.","description":"Alice searches, an administrator revokes one document, Alice searches again.","introduced_at":"changed_condition",
  "steps":[{"op":"search","user":"u_alice","query":"quarterly","expect":["doc_acme_q3","doc_acme_forecast"]},
           {"op":"revoke","user":"u_alice","document":"doc_acme_forecast"},
           {"op":"search","user":"u_alice","query":"quarterly","expect":["doc_acme_q3"]}]},
 {"id":"repeat_search_efficiency","name":"Repeated searches avoid work","behavior":"Repeated authorized searches avoid repeating the expensive search operation where possible.","description":"Three searches for the same query; the index may be scanned at most twice.","introduced_at":"initial","max_search_calls":2,
  "steps":[{"op":"search","user":"u_alice","query":"quarterly","expect":["doc_acme_q3","doc_acme_forecast"]},
           {"op":"search","user":"u_alice","query":"quarterly","expect":["doc_acme_q3","doc_acme_forecast"]},
           {"op":"search","user":"u_bob","query":"quarterly","expect":["doc_acme_q3"]}]}
]}
```

- [ ] **Step 4: Runner** (`checks/v1/runner.py`), read-only, copied into every sandbox next to the application files:

```python
"""Quorum check runner. Not editable.

Reads a JSON script from stdin, runs each check in a fresh interpreter so
module state (cache contents, permissions) cannot leak between checks, and
prints one JSON object describing what search() returned. It never decides
pass or fail; the backend compares against expectations it holds itself.
"""
import json
import os
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PER_CHECK_TIMEOUT = 8


def run_one(check):
    sys.path.insert(0, HERE)
    import index
    import permissions
    import search

    steps_out = []
    for step in check["steps"]:
        entry = {"returned": None, "error": None}
        try:
            if step["op"] == "search":
                result = search.search(step["user"], step["query"])
                entry["returned"] = [item["id"] if isinstance(item, dict) else str(item) for item in list(result)]
            elif step["op"] == "revoke":
                permissions.revoke(step["user"], step["document"])
                entry["returned"] = []
            else:
                entry["error"] = "unknown op %s" % step["op"]
        except Exception:
            entry["error"] = traceback.format_exc(limit=3)[-1500:]
        steps_out.append(entry)
    return {"check_id": check["id"], "steps": steps_out,
            "search_calls": getattr(index, "SEARCH_CALLS", None), "error": None}


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--one":
        print("\n" + json.dumps(run_one(json.loads(sys.argv[2]))))
        return
    script = json.load(sys.stdin)
    results = []
    for check in script["checks"]:
        try:
            proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--one", json.dumps(check)],
                                  capture_output=True, text=True, cwd=HERE, timeout=PER_CHECK_TIMEOUT)
        except subprocess.TimeoutExpired:
            results.append({"check_id": check["id"], "steps": [], "search_calls": None,
                            "error": "check timed out after %ss" % PER_CHECK_TIMEOUT})
            continue
        parsed = None
        for line in reversed(proc.stdout.strip().splitlines()):
            try:
                parsed = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        if proc.returncode == 0 and isinstance(parsed, dict) and parsed.get("check_id") == check["id"]:
            results.append(parsed)
        else:
            results.append({"check_id": check["id"], "steps": [], "search_calls": None,
                            "error": (proc.stderr or proc.stdout)[-2000:] or "exit %s" % proc.returncode})
    print(json.dumps({"results": results}))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Reference solutions** under `checks/v1/solutions/<name>/search.py`. `partial`: identical to the seeded file except `key = (user_id, _normalise(query))`. `disabled`: no cache calls at all (filter `index.expensive_search` per request). `complete`:

```python
import cache
import index
import permissions


def _normalise(query):
    return " ".join(query.lower().split())


def search(user_id, query):
    key = _normalise(query)
    hits = cache.get(key)
    if hits is None:
        hits = index.expensive_search(query)
        cache.put(key, hits)
    return [{"id": d["id"], "title": d["title"]} for d in hits if permissions.can_read(user_id, d["id"])]
```

- [ ] **Step 6: Brief and rubric.** `brief.md` (≤ 90 lines): the product (multi-company document search), the recent change ("PR 418: cache search results to speed up repeated searches"), the four expected behaviors verbatim from the PRD §4, which files are editable, the `search(user_id, query)` and `permissions.revoke(user_id, document_id)` contracts that must keep their names and signatures, that `index.expensive_search` is the expensive call and counts invocations, how checks run (fresh interpreter per check), and that disabling caching is an acceptable containment decision whose performance cost the checks will show. `rubric.json`: `{"version":"v1","dimensions":[{"id":"understanding_problem","title":"Understanding the problem","guidance":"..."},{"id":"implementing_checking_fix","title":"Implementing and checking a fix","guidance":"..."},{"id":"explaining_consequences","title":"Explaining customer and release consequences","guidance":"..."},{"id":"responding_to_new_evidence","title":"Responding to new evidence","guidance":"..."}],"observation_levels":["demonstrated","partly_demonstrated","not_observed"],"rules":["A machine-observed pass supports a behavior under recorded conditions only.","Represent explanation and implementation evidence separately.","Disabling caching is valid containment; note the unresolved performance objective rather than penalising it.","A changed answer after new evidence is a revision unless facts and scope were unchanged.","Never produce an overall score, ranking, or judgments about personality, emotion, accent, or honesty."]}` with one-sentence guidance per dimension drawn from PRD §6.

- [ ] **Step 7: Loader and tests.** `load_scenario` reads the files above (`readonly_files` keys: `index.py`, `runner.py`, `fixtures/users.json`, `fixtures/documents.json`, `fixtures/permissions.json`; `fixture_version` and `check_version` come from the directory names `v1`). Tests in `test_scenario.py`: loads three editable files and five readonly files; four checks with the ids above; `public_check` omits `expect`; running `runner.py` directly through `subprocess` in a temp dir assembled from the seeded files with the full script produces parseable JSON whose `cross_company_isolation` second step returns `["doc_acme_q3"]` (the bug is observable) and whose `access_filtering` steps return the expected ids.
- [ ] **Step 8: Run tests, then commit** `feat(scenario): document-search case, checks, runner, reference solutions`.

---

### Task 3: Execution: check evaluation, executors, run and replay services

**Files:**
- Create: `server/app/execution/__init__.py`, `runner_protocol.py`, `checks.py`, `executor.py`, `runs.py`, `server/app/storage/snapshots.py`, `server/tests/test_checks_matrix.py`, `server/tests/test_executor.py`, `server/tests/test_runs.py`
- Modify: `server/app/main.py` (lifespan: `app.state.executor = build_executor(settings)`; health reports `executor.name`)

**Consumes:** Task 1 repo and bus; Task 2 `Scenario`/`Check`. **Produces:** everything in the interfaces doc's Execution section plus `snapshots.py`:

```python
ALLOWED_FILES = ("search.py", "cache.py", "permissions.py")
class SnapshotError(ValueError): ...
def validate_files(files: dict[str, str], limit_bytes: int) -> None      # unknown name, non-str, total size > limit, NUL bytes -> SnapshotError
def content_hash(files: dict[str, str]) -> str                            # sha256 of sorted "name\0content\0" pairs
def write_snapshot(snapshot_dir, interview_id, snapshot_id, files) -> None  # <dir>/<interview>/<snapshot>/<name>
def read_snapshot(snapshot_dir, interview_id, snapshot_id) -> dict[str, str]
def delete_interview_dir(snapshot_dir, interview_id) -> None
```

Behavior of `runs.start_run`: 404 if snapshot not found or belongs to another interview; 409 if `active_run` exists; 409 if `count_runs >= MAX_RUNS_PER_INTERVIEW`; 400 if any check id is not in `app.state.controller.allowed_check_ids(interview_id)` when a controller exists (Task 6 adds it; until then use all `introduced_at == "initial"` checks plus `changed_condition` ones only if the interview `state_json` has `"revocation_introduced": true`; implement that rule in a helper `allowed_check_ids(app, interview_id)` in `runs.py` so Task 6 can delegate to it); idempotency: same key returns the existing run. Inserts run `queued`, emits `run_started`, schedules `execute_run` with `asyncio.create_task`, returns the row. `execute_run`: sets `running` + `started_at`, builds workspace files from the scenario and the snapshot, runs the executor with `RUN_TIMEOUT_SECONDS` and `RUN_OUTPUT_CAP_BYTES`, then: `completed` → `parse_output` + `evaluate` → `results_json`; parse failure → `failed` with excerpt; `timeout`/`failed`/`unavailable` → same status, `results_json` null (never invented). Store `stdout_excerpt`/`stderr_excerpt` (last 4 KB), `sandbox_id`, `finished_at`; emit `run_completed`; if `app.state.controller` exists call `await controller.on_run_completed(interview_id, run_id)` (guard with `getattr`). `start_replay`: original must be `completed`; new run with the original snapshot, fixture and check versions, check ids, `replay_of=original.id`; after completion set `differs_from_original = results_differ(original.results, replay.results)` (null unless both completed); if it differs and `app.state` has an evidence hook `mark_findings_needing_review` (Task 8 sets `app.state.mark_findings_needing_review = lambda interview_id, ref_type, ref_id, reason: ...`), call it with `(interview_id, "run", original_id, "replay_differs")`.

`LocalExecutor` is labeled in its docstring "development and test executor; not the demo path". `E2BExecutor` uses `e2b.AsyncSandbox` exactly as the interfaces doc describes and maps `TimeoutException`/command timeouts to `timeout`, other `SandboxException` to `failed`, missing key to `unavailable`. Output is truncated to `output_cap` bytes with a trailing marker `\n[truncated]`.

- [ ] **Step 1: Failing tests.** `test_checks_matrix.py` (uses `LocalExecutor` end to end through `build_workspace_files` + `evaluate`): parametrised over `seeded`, `partial`, `complete`, `disabled` snapshots (seeded = scenario editable files; others swap `search.py` from the reference solutions) asserting the exact pass matrix: seeded `{access_filtering: True, cross_company_isolation: False, revocation_next_request: False, repeat_search_efficiency: False}`; partial `{True, True, False, True}`; complete all `True`; disabled `{True, True, True, False}` with `efficiency_ok False` and `search_calls == 3`. Also: a `search.py` that raises produces `passed False` with `error` populated and no exception; a `search.py` with `while True: pass` yields `ExecResult.status == "timeout"` within `timeout_s=2`. `test_executor.py`: `build_executor` returns `UnavailableExecutor` when `EXECUTOR=e2b` and no key (and its `run` returns `unavailable`), `LocalExecutor` for `local`; output cap truncation. `test_runs.py` (via the app fixture, calling service functions directly with a seeded interview and snapshot rows): idempotency key returns the same run; second concurrent run → `RunError 409`; 21st run → 409; unknown check id → 400; `revocation_next_request` rejected until `state_json` marks revocation introduced; execute_run stores results and emits `run_completed`; replay creates a new row with `replay_of` and leaves the original row's `results_json` byte-identical; a replay whose results differ (monkeypatch the executor to return altered output) sets `differs_from_original=1`. Snapshot tests: `validate_files` rejects `index.py`, `../search.py`, oversize; `content_hash` stable across key order.
- [ ] **Step 2: Run tests, confirm failure.**
- [ ] **Step 3: Implement** the modules.
- [ ] **Step 4: Run tests, confirm pass, output pristine.**
- [ ] **Step 5: Commit** `feat(execution): check evaluation, local and E2B executors, run and replay services`.

---

### Task 4: Auth, interview lifecycle routes, files, runs, SSE

**Files:**
- Create: `server/app/routes/__init__.py`, `deps.py`, `auth.py`, `interviews.py`, `files.py`, `runs.py`, `events.py`, `server/tests/test_auth.py`, `server/tests/test_interview_routes.py`, `server/tests/test_sse.py`
- Modify: `server/app/main.py` (include routers; CORS)

**Consumes:** Tasks 1–3. **Produces:** the routes in the interfaces doc except `/turns`, `/transcript`, `/llm`, `/finish`, `/assessment`, `/replays`, `/disputes` (Tasks 6 and 8 add those; `finish` is added here as a stub that returns 501 so the client contract is fixed, and Task 8 replaces the body).

Details:

- `POST /api/interviews`: requires `consent is True` (422 otherwise), creates the interview (`status="created"`, `stage="briefing"`, `active_role="technical"`, `expires_at = now + RETENTION_DAYS`, `state_json = ControllerState().to_json()` when Task 6 exists; until then `"{}"`; write it through a small helper `initial_state_json()` in `interviews.py` that Task 6 rewires), candidate and reviewer capabilities, sets the candidate cookie, returns `reviewer_token` once. Response 201.
- `GET /api/interviews/{id}` builds `InterviewView` from the row, the scenario, `latest_snapshot`, `count_runs`, `MAX_RUNS_PER_INTERVIEW`, `SESSION_CAP_MINUTES`, `voice_enabled = app.state.voice.enabled if present else settings.voice_configured`, and `checks` with `available` computed by `runs.allowed_check_ids`.
- `POST /start`: sets `status="live"`, `started_at`; if `app.state.voice` exists and is enabled, call it (Task 7 wires this; here return `{"voice": {"enabled": False}}` when no voice service) and emit `voice_status`.
- `POST /pause`: toggles `paused`, tracks `paused_at`/`paused_ms`, emits `pause_changed`.
- `PUT /files`: `validate_files`, `content_hash`, `write_snapshot`, `insert_snapshot`, emit `snapshot_saved`. 400 on `SnapshotError`, 409 if the interview is not `created` or `live`.
- `GET /snapshots/{sid}`: 404 when the snapshot belongs to another interview.
- `POST /runs` → `start_run` (map `RunError` to its status); `GET /runs`, `GET /runs/{rid}`.
- `GET /events`: `EventSourceResponse` from `sse_starlette`; replay `list_events(after)`, then subscribe; heartbeat 15 s; unsubscribe on disconnect.
- `DELETE /{id}`: `delete_interview_rows` + `delete_interview_dir` (Task 8 moves this into `cleanup.delete_interview`; implement it here in `interviews.py` as `delete_interview(app, id)` and Task 8 relocates it).
- `POST /api/auth/exchange`: hashes the token, finds the capability, sets the cookie for its kind, returns `{interview_id, kind}`; 404 for unknown tokens.
- `require_same_origin` is applied to every non-GET `/api` route via a dependency; it accepts requests whose `Origin` (or the origin part of `Referer`) is in `ALLOWED_ORIGINS`. Tests use `TestClient` with `headers={"Origin": "http://localhost:3000"}`.

- [ ] **Step 1: Failing tests.** `test_auth.py`: create returns 201 and sets `quorum_candidate`; `GET` without cookie → 401; a candidate cookie for interview A on interview B → 403; `exchange` with the reviewer token sets `quorum_reviewer` and allows `GET` with `me == "reviewer"`; unknown token → 404; mutation without `Origin` → 403; `Origin` not in the allowlist → 403. `test_interview_routes.py`: `PUT /files` with a path traversal name → 400; with `index.py` → 400; valid save returns a snapshot id and emits `snapshot_saved`; `POST /runs` with the snapshot and `["cross_company_isolation"]` → 202 and, after awaiting the background task (poll `GET /runs/{rid}` up to 10 s), status `completed` with `passed False`; `revocation_next_request` → 400 before introduction; `DELETE` → 204 and subsequent `GET` → 404 and the snapshot directory is gone. `test_sse.py`: using `httpx.AsyncClient(transport=ASGITransport(app))` stream `GET /events?after=0` after two events exist and read both replayed events with correct `seq` and `event:` lines.
- [ ] **Step 2: Run, confirm failure. Step 3: Implement. Step 4: Run, pass, pristine.**
- [ ] **Step 5: Commit** `feat(api): auth, interview lifecycle, snapshots, runs, SSE`.

---

### Task 5: Model client, scripted test double, and prompts

**Files:**
- Create: `server/app/interview/__init__.py`, `llm_client.py`, `prompts.py`, `server/tests/test_llm_client.py`, `server/tests/test_prompts.py`
- Modify: `server/app/main.py` (lifespan: `app.state.llm = build_llm(settings)`; health reports `llm.model_id`)

**Consumes:** interfaces doc LLM and Prompts sections. **Produces:** `OpenAICompatibleClient`, `ScriptedLLM`, `build_llm`, all prompt builders.

`OpenAICompatibleClient` uses `openai.AsyncOpenAI(base_url, api_key, http_client=...)`; `stream_text` yields `delta.content` strings from `chat.completions.create(stream=True)`; `complete_json` calls with `response_format={"type": "json_object"}` and parses; both wrap SDK errors in `LLMError`. `build_llm`: `scripted` → `ScriptedLLM`; `openai` → requires `LLM_API_KEY` and `LLM_MODEL` (raise `RuntimeError` naming the missing variable).

`ScriptedLLM` (documented as a test double): reads the `# quorum-task:` marker of the first system message.

- `spoken_turn`: returns a deterministic sentence built from the context embedded in the prompt: it must include the role label, the instruction kind, and, when the prompt's `pending_runs` block is non-empty, the phrase `"your latest run"` plus each failed check name; when `instruction_kind == "scenario_notice"` the text is `"Customer administrator here. I just removed an employee's access to a document. Can they still retrieve it from a search they ran earlier?"`; when `hint` the text starts with `"Here is a narrower question:"`. Chunked by words.
- `claims`: keyword heuristics over the candidate text: mentions of `cache key|keyed by|query only|same key|shared cache|leak|other company|cross` → claim `diagnosis`/`cross_company`; `revoke|revocation|permission change|stale` → `revocation`; `ship|don't ship|block the release|roll back|disable the cache|hold` → `release_decision`/`general`; `test|check|assert` → `test_plan`; `not sure|maybe|might|I think|unclear` → `clarity: vague`; if the text contains `"actually"` or `"I was wrong"` or `"changed my mind"` and a prior claim with the same scope exists in the prompt's prior-claims block, set `revises_claim_id` to that claim id. `covered` flags follow: `initial_explanation` true when any diagnosis claim; `release_decision` when any release claim; `cross_company`/`revocation` when a diagnosis of that scope; `final_recommendation` when a release claim after the prompt's stage block says `release_discussion`.
- `assessment`: builds four dimension findings and two expanded findings using the ids listed in the prompt's record block (first segment id, every completed run id, first claim id); `observation_level` is `demonstrated` when the record shows a run passing the related check, `partly_demonstrated` when a related claim exists without a passing run, else `not_observed`. If the prompt contains the marker `[[scripted:invalid-refs]]` it returns a payload referencing `seg_nope` (used by Task 8 tests).

`prompts.py` system prompts must include (spoken_turn): the AI disclosure that the speaker is an AI interviewer in the given role; role objective text from PRD §4 (technical: correctness, diagnosis, testing; product: release tradeoffs and business consequences; customer: current access and customer expectations); shared rules (one question at a time, at most 60 words, plain speech with no markdown or code, refer to the latest answer or run result when present, never re-raise a concern the candidate already addressed, never call an answer contradictory; ask a neutral clarification instead, never comment on personality, confidence, accent or honesty, do not mention internal ids); the structured state block as JSON; the instruction block for `instruction_kind` (`hint`: give a narrower prompt and say it is a hint; `scenario_notice`: introduce the access-revocation condition in one or two sentences and ask the candidate to check their solution under it; `clarify`: ask what scope or timing the candidate meant; `run_follow_up`: name the run outcome first, then one question; `wrap_up`: ask for the final release recommendation, remaining uncertainties, and next checks; `probe_deeper`: ask about limits or tests of the approach instead of the bug they already found); the latest files (fenced, name-labelled) when present; recent transcript lines as `Speaker: text`. `claims_messages` and `assessment_messages` embed the JSON schemas from the interfaces doc verbatim in the instructions, plus the rubric rules for assessment, and list every referenceable id with a one-line description so the model can only pick from real ids. `greeting_text(display_name)` returns the spoken opening used as the Agora greeting: it must contain the phrase "AI interviewers", name the three roles, say the task (review a caching change in a document-search app), mention that speech and code are processed to produce an assessment and that the candidate can type instead of speaking, pause, or ask for thinking time, and end by asking the candidate to say when they have finished reading the brief. `agent_instructions()` returns a one-paragraph system instruction for the Agora agent record (the real instructions arrive per turn from the custom endpoint). `assessment_messages` instruction includes: four dimension entries in the fixed order, at most six expanded findings, every explanation must cite at least one ref, assistance must name hint segments if any, and the exact phrase "Do not generate an overall hire score".

- [ ] **Step 1: Failing tests.** `test_llm_client.py`: `OpenAICompatibleClient.stream_text` against a fake OpenAI server (httpx `MockTransport` returning an SSE body with two chunks then `[DONE]`) yields the two deltas in order; `complete_json` parses a JSON body; a 500 raises `LLMError`; `build_llm("openai")` without a key raises `RuntimeError` mentioning `LLM_API_KEY`. `ScriptedLLM` behaviors listed above, including the `scenario_notice` sentence and the `revises_claim_id` rule. `test_prompts.py`: each builder's first system line is the marker; spoken prompt contains the role label, the disclosure phrase "AI interviewer", the 60-word rule, and the pending run's failed check names; assessment prompt lists every id from the record and contains the no-score phrase.
- [ ] **Step 2–4:** run, implement, run.
- [ ] **Step 5: Commit** `feat(llm): OpenAI-compatible client, scripted test double, versioned prompts`.

---

### Task 6: Conversation controller, text turns, Agora custom-LLM endpoint

**Files:**
- Create: `server/app/interview/state.py`, `stages.py`, `roles.py`, `controller.py`, `server/app/routes/turns.py`, `server/app/routes/llm.py`, `server/tests/test_stages_roles.py`, `server/tests/test_controller.py`, `server/tests/test_llm_endpoint.py`
- Modify: `server/app/main.py` (lifespan: `app.state.controller = InterviewController(app)`; include routers), `server/app/routes/interviews.py` (`initial_state_json` → `ControllerState().to_json()`), `server/app/execution/runs.py` (`allowed_check_ids` delegates to the controller state's `revocation_introduced`; keep the function signature)

**Consumes:** Tasks 1–5. **Produces:** the Controller section of the interfaces doc.

Rules (implement as pure functions with these exact decisions):

`next_stage(state, facts)`:
- `briefing` → `initial_review` on the first candidate turn.
- `initial_review` → `investigation` when `covered.initial_explanation and covered.release_decision`, or `candidate_turns_in_stage >= 3`.
- `investigation` → `changed_condition` when `facts.completed_runs >= 1 and candidate_turns_in_stage >= 2 and not state.pending_run_ids`, or `candidate_turns_in_stage >= 6`, or `facts.elapsed_minutes >= 12`.
- `changed_condition` → `release_discussion` when `state.revocation_introduced and facts.revocation_run_completed and candidate_turns_in_stage >= 1`, or `candidate_turns_in_stage >= 4`, or `facts.elapsed_minutes >= 18`.
- `release_discussion` stays until finish (`assessment` is set by the finish route).
`candidate_turns_in_stage` and `role_turns_in_stage` reset on transition.

`select_role(state, facts)` → `(role, TurnInstruction)`:
- `state.contradiction_note` set → keep the current role, `clarify` with that note (then the controller clears the note).
- `state.last_clarity == "vague"` → current role, `clarify`.
- `initial_review`: `technical`, `normal`; if `candidate_turns_in_stage >= 2 and not covered.cross_company` → `hint` ("The cache key is worth a close look. What does it include, and who else could share it?").
- `investigation`: if `pending_run_ids` → `run_follow_up` by `technical`, except when `role_turns_in_stage.get("product", 0) == 0 and facts.latest_run_passed.get("cross_company_isolation") is True` → `product`, `run_follow_up` ("Ask whether they would ship the slower safe version today and what they would tell the team"). Else if `covered.cross_company and covered.revocation and not state.revocation_introduced` → `technical`, `probe_deeper`. Else if `candidate_turns_in_stage >= 3 and not covered.cross_company` and no hint yet in this stage → `technical`, `hint`. Else `technical`, `normal`.
- `changed_condition`: if `not state.revocation_introduced` → `customer`, `scenario_notice`. Else if `pending_run_ids` and the newest pending run includes `revocation_next_request` and `role_turns_in_stage.get("customer", 0) < 2` → `customer`, `run_follow_up`. Else if `pending_run_ids` → `technical`, `run_follow_up`. Else `technical`, `normal`.
- `release_discussion`: if `not covered.final_recommendation` → `product`, `wrap_up`; else `technical`, `normal` with note "ask for the next checks they would add".

`InterviewController.run_turn` (async generator): lock per interview (`asyncio.Lock` map) only around state read/write, not around streaming. Steps: load interview (finished → yield "The interview has ended. Thank you." and return); increment `generation`; insert candidate segment (`kind="turn"`, `status="complete"`, `generation`); `turns_total`, `candidate_turns_in_stage` += 1; compute `facts`; `new_stage = next_stage`; on change emit `stage_changed`, update `interviews.stage`, reset counters; `role, instruction = select_role`; emit `role_changed` if changed and update `interviews.active_role`; build `TurnContext` (latest snapshot files, last 3 runs as `run_view`, pending runs, last 12 segments); stream `llm.stream_text(spoken_turn_messages(ctx))`; before yielding each chunk compare `current_generation(interview_id)` to this turn's generation and stop if different; insert the role segment (`speaker=role`, `kind` = `hint` for hint, `scenario_notice` for scenario notice, `clarification` for clarify, `follow_up` for run_follow_up, else `turn`; `status` `interrupted` if stopped early else `complete`); for `hint`: append segment id to `hints_given`; for `scenario_notice`: set `revocation_introduced`, `revocation_segment_id`, emit `scenario_notice` with `checks_unlocked=["revocation_next_request"]`; move `pending_run_ids` to `discussed_run_ids`; `role_turns_in_stage[role] += 1`; clear `contradiction_note`; save state; schedule `asyncio.create_task(extract_and_store_claims(app, interview_id, candidate_segment_id))` if `app.state` has `claims_extractor` (Task 8 sets `app.state.claims_extractor = extract_and_store_claims`; store the task in `app.state.background_tasks` set so tests can await them). Any `LLMError` → yield the fixed sentence "Give me a moment, I lost my train of thought. Could you say that again?" and record it as the role segment with `status="pending"`; never fabricate content.

`on_run_completed`: append to `pending_run_ids`, call `links.link_run_to_claims` if the evidence module is present (`getattr(app.state, "link_run", None)`), save, then schedule `proactive_follow_up` after `FOLLOW_UP_DELAY_SECONDS`: if the run id is still pending, the generation is unchanged since scheduling, and the interview is live and not paused, run a turn with `user_text=""` flagged `source="run"` (the controller treats empty text as "no new candidate speech": it does not insert a candidate segment or count a candidate turn, selects the role with `run_follow_up`, streams to completion, records the segment as `kind="follow_up"`) and, if `voice.enabled` and the interview has `agora_agent_id`, `await voice.say(agent_id, text)`.

`apply_transcript_status`: for `speaker == "agent"`, find the most recent role segment (any status) whose normalised text starts with the normalised reported text or vice versa; set `spoken_text=text`, `status = "interrupted" if status == "interrupted" else "complete"`, emit `segment_updated`, return its id; for `candidate`, return null (candidate text is recorded from the LLM endpoint).

Routes: `POST /turns` collects the generator into one string, returns `{segment_id, role, text, stage}` (segment id of the role segment; keep it on `app.state.controller.last_role_segment(interview_id)` or return from the generator via a side channel: implement `run_turn_collect(interview_id, text, source) -> dict` on the controller for this). `POST /transcript` → `apply_transcript_status`. `POST /llm/{id}/chat/completions`: bearer check with `hmac.compare_digest(llm_token(settings, id), provided)` → 401; 503 if `not settings.llm_endpoint_enabled`; body parsed leniently (`messages` list; last `user` message content string or list of `{type:"text"}` parts); `stream` must be true (400 otherwise); response `StreamingResponse(media_type="text/event-stream")` emitting a role chunk, one content chunk per streamed piece, a `finish_reason: "stop"` chunk, then `data: [DONE]`, all in the OpenAI `chat.completion.chunk` shape with `model = "quorum-controller"`.

- [ ] **Step 1: Failing tests.** `test_stages_roles.py`: table-driven tests for every rule above (correct → investigation after explanation+decision; vague → clarify; incomplete after 2 turns → hint; both issues found → probe_deeper; changed_condition first turn → customer/scenario_notice; product interjects once after a passing isolation run; wrap_up in release_discussion; time-based transitions). `test_controller.py` (app fixture with `ScriptedLLM`): first turn moves to `initial_review` and the role segment mentions "Technical interviewer"; run a turn, then `on_run_completed` with a completed run row → next turn text contains "your latest run"; interruption: start `run_turn` as a generator, consume one chunk, call `run_turn` again with new text (which bumps generation), then finish consuming the first generator → it stops early and its segment is stored `interrupted`, the second completes; scenario notice sets `revocation_introduced`, emits `scenario_notice`, and `allowed_check_ids` now includes `revocation_next_request`; proactive follow-up (set `FOLLOW_UP_DELAY_SECONDS=0.05`): after `on_run_completed` with no new turn, a `follow_up` segment appears; an `LLMError` (monkeypatched `stream_text`) yields the fixed sentence and a `pending` segment; `apply_transcript_status` marks the latest role segment `interrupted` with `spoken_text`. `test_llm_endpoint.py`: wrong bearer → 401; correct bearer streams `data:` lines whose JSON has `object == "chat.completion.chunk"`, ends with `[DONE]`, and the concatenated deltas equal the recorded role segment text; content never contains ids (`seg_`, `run_`).
- [ ] **Step 2–4:** run, implement, run.
- [ ] **Step 5: Commit** `feat(interview): controller with stages, roles, hints, interruption; text turns; Agora custom-LLM endpoint`.

---

### Task 7: Agora voice service and start endpoint wiring

**Files:**
- Create: `server/app/interview/agora.py`, `server/tests/test_voice.py`
- Modify: `server/app/main.py` (lifespan: `app.state.voice = build_voice(settings)`; health `voice_enabled = voice.enabled`), `server/app/routes/interviews.py` (`/start` and `/finish`/`DELETE` call the voice service)

**Consumes:** the `agora-agents` SDK (`agora_agent`), Task 6 controller (`greeting_text`, `agent_instructions`, `llm_token`). **Produces:** the Voice section of the interfaces doc.

`AgoraVoiceService(settings)`:
- `make_join(interview_id)`: channel `f"quorum-{interview_id}"`, `uid = random 1000–9999999`, `agent_uid = random 10000000–99999999`, token from `agora_agent.agentkit.token.generate_convo_ai_token(app_id, app_certificate, channel, uid, token_expire=3600)`.
- `start_agent(join, *, llm_url, llm_token, greeting, instructions)`: `AsyncAgora(area=Area.US, app_id, app_certificate)`; `Agent(client, instructions=instructions, greeting=greeting, failure_message="One moment.", max_history=8, turn_detection={"config": {"speech_threshold": 0.5, "start_of_speech": {"mode": "vad", "vad_config": {"interrupt_duration_ms": 160, "prefix_padding_ms": 300}}, "end_of_speech": {"mode": "vad", "vad_config": {"silence_duration_ms": 480}}}}, interruption={"enable": True}, advanced_features={"enable_rtm": True}, parameters={"audio_scenario": "chorus", "data_channel": "rtm", "enable_error_message": True, "enable_metrics": True})`, `.with_stt(DeepgramSTT(model=AGORA_ASR_MODEL, language="en"))`, `.with_llm(CustomLLM(base_url=llm_url, api_key=llm_token, model="quorum-controller", greeting_message=greeting, failure_message="One moment.", max_history=8, max_tokens=220, temperature=0.4))`, `.with_tts(MiniMaxTTS(model=AGORA_TTS_MODEL, voice_id=AGORA_TTS_VOICE_ID))`; `create_async_session(channel, agent_uid=str, remote_uids=[str(uid)], enable_string_uid=False, idle_timeout=120, expires_in=3600)`; `agent_id = await session.start()`; keep `self._sessions[agent_id] = session`. Expose `build_properties(...)` returning `agent.to_properties(...)` so tests can inspect the wire config without network.
- `stop_agent`: session `stop()` if known else `client.stop_agent(agent_id)`; swallow and log errors.
- `say(agent_id, text, interrupt=False)`: `session.say(text, priority="INTERRUPT" if interrupt else "APPEND", interruptable=True)`; `interrupt`: `session.interrupt()`. Both no-ops with a warning when the session is unknown (process restarted).
- `NullVoiceService`: `enabled=False`, `make_join` returns `JoinData(enabled=False)`, other methods no-op.
- `build_voice`: `AgoraVoiceService` when `settings.voice_configured and settings.llm_endpoint_enabled`, else `NullVoiceService` (log which one and why).

`/start` route: `join = voice.make_join(id)`; if enabled: `agent_id = await voice.start_agent(join, llm_url=f"{CUSTOM_LLM_PUBLIC_BASE_URL}/llm/{id}/chat/completions", llm_token=llm_token(settings, id), greeting=greeting_text(display_name), instructions=agent_instructions())`, store `agora_*` columns, `voice_status="connecting"`, emit `voice_status`; on failure store `voice_status="disconnected"`, emit, and return `enabled=False` with a `reason` string (the interview continues in text mode); insert a `greeting` segment (speaker `technical`, kind `greeting`, text = greeting) either way so the transcript starts with the disclosure. `/finish` and `DELETE` call `stop_agent` when an agent id exists.

- [ ] **Step 1: Failing tests.** `test_voice.py`: `build_voice` returns `NullVoiceService` when unconfigured; `AgoraVoiceService.build_properties` (constructed with dummy app id/certificate) produces a dict whose `llm.url` is the given llm url, `llm.api_key` the token, `llm.vendor == "custom"`, `asr.vendor == "deepgram"`, `tts.vendor == "minimax"`, `advanced_features.enable_rtm is True`, `parameters.data_channel == "rtm"`, and `make_join` returns a token string longer than 100 characters with the expected channel prefix; `/start` on the app fixture (NullVoice) returns `enabled False`, sets `status live`, and creates a greeting segment containing "AI".
- [ ] **Step 2–4:** run, implement, run.
- [ ] **Step 5: Commit** `feat(voice): Agora Conversational AI session via agora-agents, join data, say/interrupt`.

---

### Task 8: Evidence: claims, links, assessment, validation, disputes, replay marking, cleanup

**Files:**
- Create: `server/app/evidence/__init__.py`, `claims.py`, `links.py`, `validate.py`, `findings.py`, `disputes.py`, `server/app/cleanup.py`, `server/app/routes/assessment.py`, `server/tests/test_claims_links.py`, `server/tests/test_assessment.py`, `server/tests/test_disputes_replay.py`, `server/tests/test_cleanup.py`
- Modify: `server/app/main.py` (lifespan hooks: `app.state.claims_extractor = extract_and_store_claims`, `app.state.link_run = lambda interview_id, run_row: link_run_to_claims(app.state.db, interview_id, run_row)`, `app.state.mark_findings_needing_review = lambda interview_id, ref_type, ref_id, reason: mark_findings_needing_review(app.state.db, app.state.bus, interview_id, ref_type, ref_id, reason)`; hourly `expire_interviews` task; include router), `server/app/routes/interviews.py` (real `/finish`, `DELETE` → `cleanup.delete_interview`), `server/app/routes/runs.py` (`POST /replays`)

**Consumes:** Tasks 1–7. **Produces:** the Evidence section of the interfaces doc.

- `extract_and_store_claims`: builds `claims_messages` (segment, last 6 segments, all prior claims as `{id, statement, scope, claim_type}`, last 3 runs), calls `llm.complete_json`, validates (drop claims with invalid enums; `revises_claim_id` must be an existing claim of this interview else dropped; at most 6 claims), inserts claims (`interpretation_status="interpretation"`), inserts `revises` links (`claim → claim`), updates `ControllerState.covered` by OR-ing the returned flags, sets `last_clarity` from the claims (vague if any vague), sets `contradiction_note` from the payload only if it is a non-empty string, saves state, and links the most recent hint or scenario-notice segment (if it precedes this segment and follows the previous candidate segment) with `challenges` to the claims it produced via `link_challenge`. On `LLMError` or invalid JSON: log, store nothing, do not raise.
- `link_run_to_claims(conn, interview_id, run_row)`: for each `CheckResult` in the run, for each claim with `scope` mapping to that check (`SCOPE_TO_CHECK`) and `claim_type in ("diagnosis", "fix_description", "release_decision")` created before the run: insert `run →supports→ claim` if passed else `run →challenges→ claim` (skip duplicates for the same run/claim pair).
- `validate_assessment_payload`: returns a list of error strings: missing or extra dimensions, invalid levels, more than 6 findings, refs whose `(type, id)` do not exist for this interview, explanations shorter than 20 characters, any text containing the words "score", "rank", "personality", "honest", "dishonest" (case-insensitive).
- `build_assessment`: assemble `record` (segments, claims, runs with results, hints, scenario notice, links, snapshots), call `assessment_messages(rubric, record)`, `complete_json`, validate; on errors retry once with the errors appended to the user message; still invalid or `LLMError` → insert assessment `status="pending"`, `summary="Assessment pending: the model response could not be validated. Machine observations are shown."`, and findings from `fallback_observations` (one finding per check present in the latest completed run: title = check name, level `demonstrated` if passed else `not_observed`, explanation naming the run id and outcome, supporting or opposing ref to the run; dimension `implementing_checking_fix`, `is_dimension=0`; plus the four dimension findings with level `not_observed`, explanation "Not assessed: model response invalid", no refs). Valid → insert assessment `complete` with `rubric_version`, `PROMPT_VERSION`, `llm.model_id`, findings with refs (`supporting` → role `supports`, `opposing` → `challenges`). Set `interviews.model_id`. Emit `assessment_completed`.
- `assessment_view`: per the interfaces doc; `has_run_ref` true when any ref type is `run`; `evidence` maps include every referenced record plus every link of the interview.
- `disputes.create_dispute`: original text from the segment (404 if not this interview's); affected findings = `findings_referencing("segment")` ∪ findings referencing claims whose `segment_id` is this segment; each marked via `mark_findings_needing_review(..., reason=f"dispute:{dispute_id}")`; emit `dispute_updated`. `resolve_dispute`: sets `resolved`, `resolution`, `resolved_at`; `clear_review_reason(reason)` removes that reason from every finding and sets `review_status="ok"` when no reasons remain; emit. `mark_findings_needing_review` appends the reason (no duplicates), sets `needs_review`, emits `assessment_completed`? No: emit `dispute_updated` only from disputes; for replay marking emit `run_completed` is already sent; add nothing else.
- `/finish`: 409 unless `status in (created, live)`; set `finishing`; `voice.stop_agent` if any; wait up to 25 s for `active_run` to clear (poll 0.5 s); await outstanding claim tasks in `app.state.background_tasks`; `stage="assessment"`, emit `stage_changed`; `build_assessment`; `status="finished"`, `finished_at`; emit `interview_finished`; return `{assessment_id, status}`. Idempotent for `finished`.
- `POST /replays`: participant; `start_replay`; the run service's hook marks findings with `replay_differs`.
- `cleanup.delete_interview`: stop voice agent if any, delete rows, delete snapshot dir. `expire_interviews(now_iso)` deletes every interview with `expires_at < now`; the lifespan starts an hourly task and runs it once at startup.

- [ ] **Step 1: Failing tests.** `test_claims_links.py`: extraction on a segment saying "The cache key only uses the query, so another company can see our documents" creates a `diagnosis/cross_company` claim and sets `covered.cross_company`; `revises_claim_id` pointing at a foreign claim is dropped; a later segment "Actually I was wrong, revocation still returns stale results" creates a `revises` link to the earlier revocation claim; a completed run with `cross_company_isolation` failing links `run →challenges→ claim`; passing links `supports`; a hint segment before the candidate segment produces a `challenges` link from the hint to the new claims. `test_assessment.py`: full flow with the app fixture (create → start → two turns → save fixed code → run → finish) yields `status complete`, four dimensions in order, every ref resolvable in `evidence`, `model_id == "scripted-test-double"`, `rubric_version == "v1"`; with the `[[scripted:invalid-refs]]` marker injected (monkeypatch `assessment_messages` to append it) the assessment is `pending` with fallback observations and the invalid ref never appears; `validate_assessment_payload` catches each error class. `test_disputes_replay.py`: a dispute on the first candidate segment marks the findings that reference it (directly or through a claim) `needs_review` with reason `dispute:<id>` and leaves `segments.text` unchanged; resolve clears it; replay of a run with unchanged code leaves the original untouched and `differs_from_original == 0`; monkeypatched differing replay sets `needs_review` with `replay_differs` on findings that reference the original run. `test_cleanup.py`: an interview with `expires_at` in the past is removed with its snapshot directory; a future one survives; `DELETE` uses the same path.
- [ ] **Step 2–4:** run, implement, run.
- [ ] **Step 5: Commit** `feat(evidence): claims, evidence links, validated assessment, disputes, replay review marking, cleanup`.

---

### Task 9: Web scaffold, design tokens, API client, consent page, reviewer exchange

**Files:**
- Create: `web/` via `npx create-next-app@latest web --ts --app --tailwind --eslint --no-src-dir --import-alias "@/*" --use-npm --yes --turbopack` then adjust; `web/next.config.ts` (rewrites `/api/:path*` and `/llm/:path*` to `process.env.BACKEND_URL ?? "http://localhost:8000"`), `web/app/globals.css` (tokens from `design-system/quorum/MASTER.md`), `web/app/layout.tsx` (fonts via `next/font/google`: IBM Plex Sans body, JetBrains Mono headings and code; dark `color-scheme`), `web/lib/types.ts`, `web/lib/api.ts`, `web/lib/events.ts` (`useSessionEvents(interviewId, onEvent)` with `EventSource`, `after` tracking, reconnect with backoff), `web/components/ui/{Button,Chip,Panel,AIBadge}.tsx`, `web/app/page.tsx`, `web/app/review/[token]/page.tsx`, `web/.env.local.example`
- Test: `npm run lint && npx tsc --noEmit && npm run build`

**Consumes:** the interfaces doc Web and HTTP API sections; `design-system/quorum/MASTER.md` (read it first; its "Quorum application notes" override the generated landing pattern). **Produces:** shared UI primitives, `api.ts`, `types.ts`, `events.ts`.

Consent page (`/`): AI disclosure block (PRD §12: AI interviewers, the task, that Agora and the model provider process audio and text, that raw audio is not recorded by the app, retention 7 days with deletion, criteria: four dimensions, human decision), display name or pseudonym input with a visible label, consent checkbox with the literal text "I understand that AI interviewers will question me and that my speech and code will be processed to produce an assessment", primary button "Create interview" disabled until consent. After creation show: candidate link button "Enter workspace" and a reviewer link field with a copy button and the note "Give this link to the hiring manager. It is shown once." `/review/[token]`: client component calls `exchangeToken`, then `router.replace(`/assessment/${interview_id}`)`; shows an error state for an invalid token.

Install: `@monaco-editor/react`, `@xyflow/react`, `agora-rtc-sdk-ng`, `agora-rtc-react`, `agora-rtm`, `agora-agent-client-toolkit`, `@phosphor-icons/react`, dev `@playwright/test`. Keep `AIBadge` as the single component that renders the "AI" label.

- [ ] **Step 1: Scaffold and configure.** Verify `npm run dev` serves `/`.
- [ ] **Step 2: Implement** tokens, primitives, pages, client modules. Every interactive control has a visible focus ring; buttons ≥ 44px tall; no emoji icons.
- [ ] **Step 3: Verify** `npm run lint`, `npx tsc --noEmit`, `npm run build` pass; with the backend running (`LLM_PROVIDER=scripted EXECUTOR=local`), creating an interview through the page lands on `/interview/{id}` (a placeholder page rendering the interview id is acceptable for this task) and the reviewer link exchange redirects to `/assessment/{id}` (placeholder).
- [ ] **Step 4: Commit** `feat(web): scaffold, design tokens, API client, consent and reviewer pages`.

---

### Task 10: Interview workspace page

**Files:**
- Create: `web/app/interview/[id]/page.tsx` (server component reading params, renders `<Workspace id=…/>`), `web/components/workspace/Workspace.tsx` (client; state owner), `FileList.tsx`, `CodeEditor.tsx` (Monaco, python, dark theme, `onChange` marks dirty), `RunPanel.tsx` (Save, Run, unsaved chip, snapshot id, check selector with unavailable checks disabled and labelled "not yet introduced"), `ResultsPanel.tsx` (run list, per-check status icon + text, expandable steps expected vs actual, search calls, executor label, "unavailable"/"timeout" states with a bounded Retry that starts a new run), `BriefPanel.tsx` (renders brief markdown, simple renderer), `web/components/interview/{RoleLabel,Captions,MicControls,TextInput,ScenarioNotice,SessionTimer,PreJoin}.tsx`, `web/lib/voice.ts` (`useVoice(join: JoinView | null, handlers)`: creates the RTC client, joins with `agora-rtc-react` hooks, publishes the microphone track, subscribes to remote audio, creates the RTM client (`new AgoraRTM.RTM(appId, String(uid))`, `login({token})`, `subscribe(channel)`), initialises `AgoraVoiceAI.init({rtcEngine, rtmConfig: {rtmEngine}, renderMode: TranscriptHelperMode.TEXT})`, `subscribeMessage(channel)`, forwards `TRANSCRIPT_UPDATED`, `AGENT_STATE_CHANGED`, `AGENT_INTERRUPTED`, `AGENT_ERROR`; exposes `sendText(text)` via `voiceAI.sendText(String(agentUid), {messageType: ChatMessageType.TEXT, text, priority: ChatMessagePriority.INTERRUPTED, responseInterruptable: true})`, `setMuted`, `leave`), `web/components/interview/VoicePanel.tsx`
- Test: manual against the backend in text mode; Task 12 adds Playwright.

**Consumes:** Task 9 primitives and client; the interfaces doc views and events. **Produces:** the working workspace.

Behavior:
- Load `getInterview`; show `PreJoin` first: microphone test (getUserMedia level meter with a visible "Microphone working" text state), buttons "Join with voice" (calls `startInterview`; if `voice.enabled` false, show the returned reason and fall back to text) and "Continue with text" (calls `startInterview` too; ignores voice).
- Layout per the design system notes. Header: stage chip (human labels: Briefing, Initial review, Investigation, Changed condition, Release discussion), `RoleLabel` ("AI · Technical interviewer" etc.) driven by `role_changed` events, `SessionTimer` (counts from `started_at`, pauses on `pause_changed`, shows the cap), Pause/Resume (calls `setPaused`, mutes the mic), End interview (confirm dialog, then `finishInterview` → navigate to `/assessment/{id}`).
- Editor: three editable files as tabs; readonly tab group for `index.py`, fixtures and brief; dirty state per file; Save → `saveFiles` with all three current contents → updates snapshot id; Run → disabled while dirty (tooltip "Save first; a run always uses a saved snapshot") → `startRun(snapshot_id, selectedChecks, idempotency_key=crypto.randomUUID())`; results arrive through `run_completed` events and `listRuns` on load.
- Captions: transcript from SSE `transcript_segment`/`segment_updated` (source of truth for the record) merged with live in-progress captions from the voice toolkit (shown muted, never stored). Each entry shows speaker label with `AIBadge` for roles, kind chip for hint ("Hint") and scenario notice, and "interrupted" marker when status is interrupted. Voice toolkit turn events with `TurnStatus.END` or `INTERRUPTED` for the agent call `reportTranscript({speaker: "agent", status, text, turn_id})`.
- `TextInput`: when voice is connected, `sendText` through the toolkit; otherwise `sendTurn` and render the returned text (SSE will also deliver it; de-duplicate by segment id).
- `ScenarioNotice`: banner from `scenario_notice` events ("New scenario information: … The revocation check is now available"); dismissible; re-enables the check in `RunPanel`.
- Voice status chip: connecting / connected / text mode / disconnected. On RTC `connection-state-change` to DISCONNECTED, call `setPaused(true)`, show "Voice disconnected. Your work is saved. Reconnect or continue with text." with a Reconnect button (re-runs `startInterview` and rejoins).
- Silence handling is server-side; the client never re-sends turns on silence.
- Accessibility: captions container `role="log" aria-live="polite"`; all buttons labelled; keyboard operable tabs.

- [ ] **Step 1: Build components** following the design system. Load Monaco and the voice modules with `next/dynamic` (`ssr: false`).
- [ ] **Step 2: Verify manually** with the backend in scripted/local mode: text turn shows role reply; edit, save, run shows real check results; unsaved chip; finish navigates. `npm run lint && npx tsc --noEmit && npm run build` pass. Record in the report exactly what was exercised.
- [ ] **Step 3: Commit** `feat(web): interview workspace with editor, runs, captions, voice and text turns`.

---

### Task 11: Assessment page with evidence map, drawer, replay, and correction

**Files:**
- Create: `web/app/assessment/[id]/page.tsx`, `web/components/evidence/Report.tsx` (client; loads `getAssessment`, subscribes to events for `run_completed`/`dispute_updated`), `DimensionCard.tsx`, `FindingList.tsx`, `EvidenceMap.tsx` (React Flow, custom node types `statement | challenge | code | revision | finding`, fixed column x positions 0/280/560/840/1120, rows by order, edges from `evidence.links` filtered to the selected finding's refs plus links between those refs, edge styles: supports solid, challenges dashed, revises dotted, each with a text label), `EvidenceDrawer.tsx` (side panel with focus trap and Escape to close; tabs for Transcript, Code, Results), `TranscriptSegment.tsx` (text, speaker with `AIBadge`, kind, timing, "Flag this segment" button for candidates and reviewers), `DiffView.tsx` (Monaco `DiffEditor` between the previous snapshot of that interview and the run's snapshot, per file; original vs modified labels with snapshot ids and hashes), `RunCompare.tsx` (before/after: the referenced run and the most recent earlier completed run, per check status icon + text, steps expected vs actual; replay list with "differs" marker), `ReplayButton.tsx` (only rendered when the finding `has_run_ref`; calls `startReplay`, shows "Rerunning…", then the new run beside the original, and the needs-review state when it differs), `DisputeForm.tsx` (proposed correction textarea with label, reason, submit → `createDispute`), `DisputeList.tsx` (original and proposed text side by side, status, affected findings, reviewer-only Resolve form → `resolveDispute`)

**Consumes:** Task 9 client and primitives; `AssessmentView`. **Produces:** the reviewer and candidate report.

Behavior:
- Header: candidate display name, finished time, `model_id`, `rubric_version`, `prompt_version`, status (pending shows the summary and the machine observations). A visible note: "Findings are interpretations linked to recorded evidence. A passing check supports a behavior under the recorded conditions only. Quorum does not make the hiring decision."
- Four `DimensionCard`s in fixed order with level pill (icon + text), explanation, assistance, uncertainty, follow-up, `needs_review` marker with reasons, and ref chips that open the drawer.
- Expanded findings list (≤ 6); selecting one renders `EvidenceMap` for it. Node cards carry buttons that open the drawer at the right tab. No physics; `nodesDraggable={false}`, `fitView`.
- Drawer content per ref type: segment → `TranscriptSegment`; run → `RunCompare` + `DiffView` for its snapshot + `ReplayButton`; claim → statement with its source segment; snapshot → file contents.
- Candidate sees their report and can flag; reviewer additionally sees the Resolve form. `me` from the view.

- [ ] **Step 1: Build components.** `@xyflow/react/dist/style.css` imported once; nodes use the `nodrag` class on buttons.
- [ ] **Step 2: Verify manually** against a finished scripted interview: map renders for a finding, drawer opens each ref type, rerun creates a replay row without changing the original, flagging marks dependent findings and the reviewer resolve clears it. `npm run lint && npx tsc --noEmit && npm run build` pass.
- [ ] **Step 3: Commit** `feat(web): assessment report with evidence map, drawer, diff, replay, correction`.

---

### Task 12: End-to-end test, scripts, environment example, README, plan status

**Files:**
- Create: `web/playwright.config.ts`, `web/tests/e2e.spec.ts`, `scripts/seed_demo.py`, `scripts/smoke_test.py`, `.env.example`
- Modify: `README.md`, `PLAN.md` (status table)

**Consumes:** everything. **Produces:** verification artefacts.

- `playwright.config.ts`: `webServer` starts the backend (`cd ../server && uv run uvicorn app.main:app --port 8010` with env `LLM_PROVIDER=scripted EXECUTOR=local SESSION_SECRET=e2e DATABASE_PATH=./data/e2e.db SNAPSHOT_DIR=./data/e2e-snapshots ALLOWED_ORIGINS=http://localhost:3010`) and the web app (`BACKEND_URL=http://localhost:8010 npm run dev -- -p 3010`), `baseURL http://localhost:3010`, chromium only.
- `e2e.spec.ts` golden flow: consent → create → workspace (Continue with text) → send "The cache key only uses the query, so another company can see our documents. I would not ship this." → reply visible with the AI badge → open `search.py`, replace content with the complete solution → Save (unsaved chip disappears, snapshot id shown) → Run → wait for all initial checks pass → send two more turns until the scenario notice banner appears (the controller introduces it at `changed_condition`) → revocation check becomes selectable → Run again → passes → End interview → assessment page: four dimensions, at least one finding, select a finding, map renders nodes, open a run ref, Rerun → a replay appears and the original result text is unchanged → flag the first candidate segment → the dependent finding shows "Needs review" → open the reviewer link (from the creation step, in a new context) → resolve → status returns to ok. Assert isolation: a second browser context without cookies gets 401 from `/api/interviews/{id}`.
- `scripts/smoke_test.py`: hits `GET /api/health`, creates an interview via HTTP, saves and runs the seeded code, prints the pass matrix and which executor ran it, and exits non-zero on any failure; `scripts/seed_demo.py`: creates an interview and prints candidate and reviewer URLs for a rehearsal.
- `.env.example`: every variable from the Settings table with a one-line explanation, no values.
- `README.md`: what Quorum is, architecture summary, setup (uv, npm), running locally in text mode, running with real providers (Agora, model, E2B) and the HTTPS tunnel requirement for `CUSTOM_LLM_PUBLIC_BASE_URL`, tests (pytest, Playwright), what works, what is verified only in test doubles, known limitations (single worker, in-memory Agora session map, no accounts), and the privacy notes from PRD §12.
- `PLAN.md`: update the status table with what passed.

- [ ] **Step 1: Write the spec and config; run `npx playwright install chromium` if needed.**
- [ ] **Step 2: Run** `npx playwright test`; fix product bugs it finds (report each fix).
- [ ] **Step 3: Run** `uv run pytest -q` in `server/` and `python scripts/smoke_test.py` against a running backend; paste summaries in the report.
- [ ] **Step 4: Commit** `test: Playwright golden flow, smoke and seed scripts, README and env example`.
