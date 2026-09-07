# Quorum

Quorum is an AI recruitment interview for software engineers: a panel of three AI interviewers puts one realistic engineering case to a candidate, who investigates a real defect, changes the code, and runs the checks while the panel questions the decisions. The report it produces is not a score — it is four dimensions of observation, each one linked to the transcript segment, code snapshot and test run behind it, which a human reviewer can open, replay and dispute.

- [Product requirements](PRD.md) — the specification this is built from.
- [Build plan](PLAN.md) — how the PRD was turned into code, the assumptions made, and the checkpoint status.
- [Shared interfaces](docs/superpowers/plans/2026-09-07-quorum-interfaces.md) — the names, JSON shapes and event types the two halves agree on.

## How it fits together

```text
Browser (Next.js 16, Monaco, React Flow)
  |  /api/*  and  /llm/*  (Next.js rewrites, so the session cookie stays first-party)
  v
FastAPI backend (single uvicorn worker)
  |     ^
  |     |  POST /llm/{id}/chat/completions   <---- Agora Conversational AI (voice)
  |
  +-- one OpenAI-compatible model     follow-ups, claim extraction, assessment drafting
  +-- E2B sandbox                     one fresh sandbox per run, no internet, killed after
  +-- SQLite + snapshot directory     events, runs, and immutable code versions
```

- The browser only ever talks to the Next.js origin. Next rewrites `/api/*` and `/llm/*` to the backend.
- Agora's agent runs in Agora's cloud and calls the backend's custom-model endpoint directly over HTTPS, which is why that endpoint needs a public URL.
- Application code owns stage transitions, permissions, execution, evidence identifiers and replay. The model writes spoken text and drafts interpretations; a prompt is never an authorization mechanism.

## Quick start (text mode)

Text mode needs no credentials at all: the interview runs over typed turns, and the checks execute in a local subprocess instead of a sandbox. It is the fastest way to see the whole flow, and it is what the automated tests use.

Requirements: [uv](https://docs.astral.sh/uv/), Python 3.12, Node 20+.

```bash
# Backend
cd server
uv sync
cp ../.env.example .env          # every line is commented; uncomment what you set
uv run uvicorn --factory app.main:create_app --port 8000
```

Every setting has a working default, so `server/.env` needs only these for text mode:

```
LLM_PROVIDER=scripted
EXECUTOR=local
SESSION_SECRET=change-me
ALLOWED_ORIGINS=http://localhost:3000
```

`LLM_PROVIDER=scripted` selects the deterministic test double, not a model — see [What is verified with test doubles](#what-is-verified-with-test-doubles). Set `LLM_PROVIDER=openai` with a key to type at a real model without setting up voice.

```bash
# Web app, in a second terminal
cd web
npm install
cp .env.local.example .env.local   # BACKEND_URL=http://localhost:8000
npm run dev
```

Open <http://localhost:3000>, agree to the disclosure, create an interview, and choose **Continue with text** on the pre-join screen.

Two operator scripts talk to a running backend over HTTP (standard library only, no virtual environment needed):

```bash
python3 scripts/smoke_test.py       # saves the seeded code, runs the checks, prints the pass matrix
python3 scripts/seed_demo.py        # creates an interview and prints its candidate and reviewer links
```

Both accept `--base` (backend URL) and `--origin` (web origin), defaulting to `QUORUM_BASE_URL` and `QUORUM_WEB_ORIGIN`, then to `http://localhost:8000` and `http://localhost:3000`.

## Running with real providers

Three credentials turn the demo path on. Each is independent: a real model without Agora gives a typed interview against a real model; Agora without E2B gives a spoken interview whose checks run locally.

**1. A model.** Any OpenAI-compatible endpoint.

```
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=...
LLM_MODEL=...
```

The identifier is recorded on every assessment, so a report always says which model wrote it.

**2. E2B, for execution.**

```
EXECUTOR=e2b
E2B_API_KEY=...
```

Each run creates a fresh sandbox with `secure=True` and `allow_internet_access=False`, runs the fixed runner against the candidate's saved snapshot, and kills the sandbox afterwards. The scenario is pure standard-library Python, so the default template is used and nothing is installed during an interview.

**3. Agora, for voice — and a public HTTPS URL.**

```
AGORA_APP_ID=...
AGORA_APP_CERTIFICATE=...
CUSTOM_LLM_PUBLIC_BASE_URL=https://<your-tunnel-host>
CUSTOM_LLM_AUTH_SECRET=<random string>
```

The agent that carries the conversation runs inside Agora's infrastructure and calls `POST {CUSTOM_LLM_PUBLIC_BASE_URL}/llm/{interview_id}/chat/completions` for every candidate turn. `localhost` is not reachable from there, so local development needs a tunnel:

```bash
cloudflared tunnel --url http://localhost:8000
# or
ngrok http 8000
```

Put the tunnel's HTTPS origin (no trailing slash) in `CUSTOM_LLM_PUBLIC_BASE_URL`, restart the backend, and reload the web app. Voice is offered only when the app id and certificate are both set; with anything missing — or when Agora refuses to start the agent — the interview degrades to text rather than refusing to begin.

For a hosted demo, deploy Next.js separately and run FastAPI as one persistent container with a real disk: SQLite and the snapshot directory are the evidence, and an ephemeral serverless filesystem loses them.

## Tests

```bash
cd server && uv run pytest -q          # 400 passed
cd web && npx playwright install chromium && npm run test:e2e
```

The Playwright suite is one test: the golden flow from consent to a resolved correction. It starts its own backend on port 8010 (scripted model, local executor, fresh database) and its own Next.js dev server on port 3010, so it needs no configuration and touches nothing you are running.

## What works

Verified in this build, by the test suites above:

- **Consent and disclosure.** The AI disclosure is shown before consent; every AI utterance and role label carries an AI badge for the whole session.
- **The workspace.** Brief, Monaco editor over the three editable files and the read-only ones, snapshot save, check selection, runs with per-step expected-versus-actual results, retries after an execution failure, pause, session timer, captions, and typed turns.
- **The conversation.** Stage transitions and role handoffs are decided by application code from recorded facts. The panel raises a completed run unprompted when the candidate has gone quiet, and the customer administrator introduces the changed condition, which unlocks the revocation check.
- **Execution.** The seeded application, and the partial, complete and disabled-cache reference solutions, produce four distinct pass matrices; the runner prints ids and a call counter, and the backend compares them against expectations held outside the candidate's code. A printed pass is never trusted.
- **The assessment.** Four dimensions plus expanded findings, every reference validated against the database before it is stored, a retry with the errors spelled out, and a `pending` assessment carrying only machine observations when the model still cannot produce a valid one.
- **Evidence, replay and correction.** The evidence map in fixed columns, the reference drawer with results and a code diff, a replay that reruns the recorded inputs beside the original without changing it, and a correction that puts dependent findings under review until a reviewer resolves it.
- **Isolation and retention.** Capability cookies (hashed with an HMAC, no accounts), a same-origin guard on every mutation, cross-session reads refused, path and size validation on saved files, and an hourly sweep that deletes an expired interview's rows and snapshots.

## What is verified with test doubles

These three integrations are built against the official SDKs and unit-tested, but **no credentials were available during this build, so none of them has been exercised live**. Nothing below should be described as a working integration until it has been run against the real service.

| Integration | What is actually verified | What is not |
| --- | --- | --- |
| Agora Conversational AI | Token minting, the agent's wire configuration, `/start` and `/finish` wiring, rejoining a live agent, and the custom-LLM endpoint's bearer auth and OpenAI-shaped SSE — all against a fake session (`server/tests/test_voice.py`, `test_llm_endpoint.py`). | A real channel, real speech, real interruption latency. |
| A real model | The OpenAI-compatible client against a fake HTTP server, and every prompt the controller builds (`server/tests/test_llm_client.py`, `test_prompts.py`). Everything else runs on `ScriptedLLM`, a keyword-table double that answers deterministically from the machine-readable blocks in each prompt. | Whether a real model returns usable follow-ups, claims and assessments from these prompts. |
| E2B sandbox | Executor selection, output capping and the error-to-status mapping (`server/tests/test_executor.py`). Every end-to-end run test uses `LocalExecutor`, which runs the same runner in a subprocess. | A real sandbox: its startup time, its limits, and its failure modes. |

`LLM_PROVIDER=scripted` and `EXECUTOR=local` exist for the tests and for offline development. Neither belongs in a real interview, and both are labelled as themselves in the UI and in `GET /api/health`.

## Known limitations

- **One worker.** The backend holds per-interview asyncio locks and a local SQLite file; running more than one uvicorn worker would break both.
- **The Agora session map is in memory.** A restart loses the live agent handles, so a session in progress has to be rejoined.
- **No accounts.** Whoever holds a capability link is the candidate or the reviewer of exactly one interview. The reviewer link is shown once, at creation, and cannot be read back.
- **Replays are capped at three per run**, and a candidate gets 20 runs per interview.
- **`compress: false` in `next.config.ts`** is an interim measure: the dev server's compressor holds small SSE frames back until its buffer fills. The backend sends `Cache-Control: no-transform` on its stream routes, and this flag should go once that is confirmed end to end.
- **One scenario, one voice.** Distinct voices, avatars, additional scenarios, repository imports, scheduling and ATS connections are out of scope (PRD §17).
- **Timing targets are unmeasured.** The PRD proposes an audible stop within 500 ms of an interruption and roughly two seconds to first audio. Neither has been measured, because voice has not been run live.

## Privacy and trust

From PRD §12, and implemented as stated:

- **No raw audio is recorded by this application.** It stores the text transcript, the saved code snapshots and the results of the checks. Agora and the model provider still process audio and text under their own terms — **this is not zero retention**, and account-specific retention, training use, processing regions and contractual terms must be verified before any real recruitment use.
- **Only synthetic data.** The scenario's fixtures are invented. Use nothing else in a public demonstration.
- **Nothing identifying is asked for.** No CV, no webcam, no identity document, no access to a private repository. A display name — a pseudonym is fine — and a session identifier are all that is kept.
- **Seven days, deletable immediately.** Interviews expire after `RETENTION_DAYS` and are swept hourly; a participant can delete everything at once from the report.
- **Disclosure before consent and throughout.** Pause, captions and text input are always available.
- **No inference from accent, expression, typing speed or apparent confidence.** The report describes what was observed on four dimensions and links it to evidence. It does not score, rank or decide; a person makes the hiring decision.
- **A correction changes the review state, not the record.** The original text stays; the proposal sits beside it, and dependent findings are marked for review until a reviewer resolves them.
- Human review does not by itself establish legal compliance. Any real hiring deployment needs review for its jurisdiction and actual use ([EEOC AI and disability resources](https://www.eeoc.gov/eeoc-disability-related-resources/artificial-intelligence-and-ada)).

## Acceptance checks

PRD §13's checks, and where each is verified. "Manual" means it needs credentials this build did not have.

| Check | Where it is verified |
| --- | --- |
| Candidate interruption | pytest `test_controller.py` (a stream stops when the generation moves on), `test_llm_endpoint.py` (disconnect mid-stream). Manual with live voice. |
| Role handoff | pytest `test_stages_roles.py`, `test_controller.py`. Playwright: the product manager takes the follow-up to the passing run. |
| Turn-taking | pytest `test_stages_roles.py` — one role per turn, chosen by code. Manual with live voice. |
| Code identity | pytest `test_runs.py`, `test_storage.py` (snapshot hash and input hash). Playwright: a run reference opens the snapshot that produced it, with a diff. |
| Known fixtures | pytest `test_checks_matrix.py` — seeded, partial, complete and disabled-cache solutions, four distinct matrices. Also `scripts/smoke_test.py` against a live backend. |
| Adaptive interview | pytest `test_controller.py`, `test_stages_roles.py` — clear, vague and uncovered answers select different instructions. |
| Assessment references | pytest `test_assessment.py` — every reference validated before storage, retried once, then `pending`. Playwright opens a run, a statement and a transcript reference from the report. |
| Revision handling | pytest `test_claims_links.py` — a revising claim records a `revises` link rather than replacing the earlier one. |
| Replay | pytest `test_disputes_replay.py`. Playwright: rerun a recorded run, "Matches original", the original result unchanged. |
| Correction | pytest `test_disputes_replay.py`. Playwright: flag a segment, dependent findings show "Needs review", a reviewer resolves it and they return to ok. |
| Isolation | pytest `test_auth.py` (cross-session reads, wrong-side cookies, the same-origin guard), `test_interview_routes.py` and `test_runs.py` (rejected file paths and sizes). Playwright: a browser with no capability gets 401 from `/api/interviews/{id}`. |
| Failure | pytest `test_runs.py` (timeout and unavailable executor are statuses, never results), `test_controller.py` and `test_assessment.py` (a model failure produces a recovery line or a `pending` assessment, never an invented answer). |
| Cleanup | pytest `test_cleanup.py` — expiry on a timer and at startup, by the same path the delete route takes. |

## Repository layout

```
web/                      Next.js app: consent, workspace, assessment, reviewer exchange
  tests/e2e.spec.ts       the Playwright golden flow
server/app/               routes, interview controller, evidence, execution, storage
server/tests/             pytest
scenarios/document-search/  brief, application, fixtures, checks, reference solutions, rubric
scripts/                  smoke_test.py, seed_demo.py
design-system/quorum/     the visual language the web app implements
```
