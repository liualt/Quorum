# Quorum build plan

Source of truth: [PRD.md](PRD.md). This plan records how the PRD is being turned into code, the assumptions made where the PRD is silent, and the status of each checkpoint.

## 1. Scope

### Demo-critical path (must work end to end)

1. Create an interview after AI disclosure and consent.
2. Candidate joins a live Agora Conversational AI session (voice, interruptible), with captions, text input, pause, and end controls.
3. Candidate reads the brief, edits the three application files in Monaco, saves a snapshot, and runs the checks. Execution happens in a fresh E2B sandbox; results are compared against expected outcomes held outside candidate code.
4. The AI panel (technical, product, customer roles; one speaker at a time) asks follow-ups that refer to the candidate's actual answers and run results. Hints are recorded.
5. The customer role introduces the changed condition (access revocation). The revocation check becomes runnable.
6. Finish produces a structured assessment: four dimensions, findings with validated evidence references, assistance received, uncertainty, and a human follow-up.
7. Reviewer opens the evidence map (fixed columns), inspects the transcript segment, the code diff, the before/after run results, and reruns a check. Replay never changes the original result; differences mark the finding for review.
8. Candidate flags a transcript segment; dependent findings become needs review; a reviewer resolves the dispute.

### Explicit exclusions (per PRD §13, §17, §19)

Additional scenarios, distinct voices, avatars, arbitrary repository imports, scheduling, ATS connections, general graph editing, overall hire score, candidate ranking, personality or emotion inference, raw audio recording, CV or identity collection, candidate-owned repositories, AI coding assistance in the editor.

### Acceptance checks preserved (PRD §13)

Candidate interruption, role handoff, turn-taking, code identity, known fixtures, adaptive interview, assessment references, revision handling, replay, correction, isolation, failure, cleanup.

## 2. Stack (prescribed)

| Layer | Choice |
| --- | --- |
| Browser | Next.js 16 (App Router, TypeScript), `@monaco-editor/react`, `@xyflow/react`, `agora-rtc-sdk-ng` + `agora-rtc-react` + `agora-rtm` + `agora-agent-client-toolkit` |
| Backend | FastAPI + Pydantic, single uvicorn worker, Python 3.12 via uv |
| Voice | Agora Conversational AI through the official `agora-agents` Python SDK (`CustomLLM`, `DeepgramSTT` nova-3, `MiniMaxTTS`, managed credentials) |
| Model | One OpenAI-compatible endpoint via the `openai` client; identifier recorded with every assessment |
| Execution | `e2b` Python SDK, fresh sandbox per run, `allow_internet_access=False`, `secure=True`, killed after each run |
| Storage | SQLite (stdlib `sqlite3`) + snapshot directory |
| Tests | pytest, Playwright |

## 3. Repository layout

```
web/                      Next.js app (see PRD §11)
  app/page.tsx            disclosure + consent + create interview
  app/interview/[id]/     workspace
  app/assessment/[id]/    report + evidence map
  app/review/[token]/     reviewer token exchange
  components/{interview,workspace,evidence}/
  lib/{api.ts,agora.ts,types.ts}
  tests/                  Playwright
server/
  app/main.py, config.py
  app/routes/             interviews, files, runs, events, llm (Agora), assessment, disputes, auth
  app/interview/          controller (stages, roles, hints, generation), prompts, llm client
  app/evidence/           claims, links, findings, validation, disputes
  app/execution/          checks, executors (e2b, local), replay
  app/storage/            db schema, repositories, event log, snapshots
  tests/
scenarios/document-search/
  brief.md, application/, fixtures/v1/, checks/v1/, rubric.json
scripts/seed_demo.py, scripts/smoke_test.py
```

## 4. Data model (SQLite)

Tables mirror PRD §10: `interviews`, `capabilities` (hashed candidate/reviewer tokens), `transcript_segments`, `code_snapshots`, `test_runs`, `claims`, `evidence_links`, `findings`, `assessments`, `disputes`, `session_events`, `hints`. All IDs are random immutable strings. Evidence changes append events; nothing overwrites a historical run or segment.

## 5. API flow

- `POST /api/interviews` → creates interview, candidate cookie, reviewer link.
- `POST /api/interviews/{id}/start` → mints Agora token (RTC+RTM), starts the agent with `CustomLLM` pointed at `CUSTOM_LLM_PUBLIC_BASE_URL/llm/{id}/chat/completions` with a per-interview bearer secret, returns join data.
- `POST /llm/{id}/chat/completions` → Agora calls this per candidate turn. Backend records the candidate segment, runs the controller (stage, role, hints, pending run notices), streams spoken text as OpenAI SSE chunks, records the role segment, then extracts claims in the background.
- `POST /api/interviews/{id}/turns` → same controller path for typed text (used when voice is unavailable, and by the browser e2e test). Returns the spoken text.
- `POST /api/interviews/{id}/transcript` → browser reports final Agora transcript turn status (end or interrupted, spoken text) so the stored segment reflects what was actually heard.
- `PUT /api/interviews/{id}/files` → validate allowed files and sizes, write snapshot, return snapshot id + hash.
- `POST /api/interviews/{id}/runs` → idempotency key, one active run per interview, execute selected allowed checks against a snapshot in a sandbox, store results, emit event, notify the controller.
- `GET /api/interviews/{id}/events?after=N` → SSE with sequence numbers.
- `POST /api/interviews/{id}/finish` → stop agent, wait for active run, build assessment, validate references (retry once), store.
- `GET /api/interviews/{id}/assessment` → findings, evidence links, referenced records.
- `POST /api/interviews/{id}/replays` → rerun a recorded run with its original snapshot, fixture, and check versions; store alongside; mark findings needs review if different.
- `POST /api/interviews/{id}/disputes`, `POST .../disputes/{did}/resolve`.
- `DELETE /api/interviews/{id}`.

## 6. Conversation controller

Stages: briefing → initial_review → investigation → changed_condition → release_discussion → assessment. Roles: technical, product, customer. Code decides stage transitions and the active role from recorded facts (candidate turns in stage, completed runs, hints given, whether revocation has been introduced). The model only writes the spoken text and drafts claim interpretations.

Interruption: each candidate turn increments a generation number; a stream for an older generation stops emitting and cancels its model call. Run results that complete while the candidate is speaking are queued and included in the next turn. If the candidate stays quiet after a run completes, the controller speaks a short follow-up through the Agora `say` API (append priority, interruptable).

## 7. Execution and checks

Checks are JSON scripts (sequences of `search`/`revoke` steps) with expected document ids per step. A fixed `runner.py` wrapper in the sandbox imports the candidate's `search()` and prints returned ids and the search-call counter as JSON. The backend compares against expectations; a printed pass/fail is never trusted. Limits: 20 s deadline, 64 KB output, 100 KB source, 20 runs per session, one active run. The revocation check is only allowed once the changed condition has been introduced.

## 8. Assessment

At finish, the assessment service gives the model the structured record (claims with segment ids, runs with results, hints, stage timeline) and asks for four dimension findings plus up to six expanded findings, each with observation level, explanation, references, assistance, uncertainty, and a human follow-up. Every reference is validated against the database; on failure the call is retried once, then the assessment is stored as pending with the available observations. Rubric, prompt, and model versions are stored with the assessment.

## 9. Assumptions recorded

- **Python 3.12** for the backend (the `agora-agents` SDK and its pinned pydantic are verified there; 3.14 wheels were not checked).
- **Agora REST auth**: the `agora-agents` SDK authenticates with `AGORA_APP_ID` and `AGORA_APP_CERTIFICATE` as the PRD lists. No customer key/secret is required by the SDK.
- **Transcript source of truth**: the backend's custom-LLM endpoint receives each final candidate utterance and produces each role utterance, so it records segments directly. The browser reports Agora turn status so interrupted role segments are marked with the text actually spoken.
- **Text turns** go through the backend directly (`/turns`) rather than through Agora, so they work without voice and during voice outages.
- **Sandbox template**: the scenario is pure standard-library Python, so the default E2B template is used and no package install happens during an interview.
- **Local executor** (`EXECUTOR=local`) runs the same runner in a subprocess for automated tests and development. It is labeled as such and is not the demo path.
- **Scripted model** (`LLM_PROVIDER=scripted`) is a test double used only by automated tests. It is never used in the demo path.
- **Reviewer access** uses a separate token link shown to the interview creator after creation; there is no account system.
- **Pause** mutes the microphone and marks a pause event; the session cap excludes paused time.
- **Replays are capped at three per run** (`MAX_REPLAYS_PER_RUN`), on top of the 20-run session limit. A reviewer reproducing a result does not need more, and the cap keeps a report from becoming a way to spend sandbox time.
- **`/start` rejoins a live agent** rather than starting a second one: it asks Agora whether the stored agent id is still in the channel, and on a reload mints a fresh token for the same channel and identities. A stored id Agora no longer recognises is stopped before a new agent is started, so a half-dead agent cannot hold the channel.
- **Disputes are accepted at any time**, including during the interview when there are no findings yet, and are applied when the assessment is built: `apply_open_disputes` puts the new findings under every open dispute's hold. The original segment text is never rewritten.
- **`compress: false` in `web/next.config.ts`** is an interim measure, not a decision. The dev server's compressor buffers small SSE frames until its buffer fills, so the browser sees nothing until the stream closes. The backend sends `Cache-Control: no-transform` on its stream routes; the flag should be removed once that is confirmed end to end.

## 10. Implementation order and status

This table records the original implementation handoff, not release acceptance.
The current audit, corrective tasks, and fresh verification results are in
[the 7 September audit](docs/audit-2026-09-07.md). Live-provider acceptance remains open.

Built as the twelve tasks of [the implementation plan](docs/superpowers/plans/2026-09-07-quorum-mvp.md), each one reviewed before the next was dispatched.

| # | Task | Status |
| --- | --- | --- |
| 1 | Backend scaffold, settings, SQLite schema, event bus | done — pytest |
| 2 | Scenario package, checks, fixed runner, reference solutions | done — pytest |
| 3 | Check evaluation, local and E2B executors, run and replay services | done — pytest; E2B unit-tested only |
| 4 | Auth, interview lifecycle routes, files, runs, SSE | done — pytest |
| 5 | Model client, scripted test double, prompts | done — pytest; the real client is tested against a fake HTTP server |
| 6 | Conversation controller, text turns, Agora custom-LLM endpoint | done — pytest |
| 7 | Agora voice service and `/start` wiring | done — pytest against a fake session; not exercised live |
| 8 | Claims, links, assessment, validation, disputes, replay marking, cleanup | done — pytest |
| 9 | Web scaffold, design tokens, API client, consent page, reviewer exchange | done — Playwright |
| 10 | Interview workspace page | done — Playwright |
| 11 | Assessment page: evidence map, drawer, replay, correction | done — Playwright |
| 12 | Playwright golden flow, smoke and seed scripts, `.env.example`, README, this table | done — 400 pytest tests pass; the Playwright golden flow passes |

Verification still outstanding, and blocked on credentials this build did not have: live Agora voice (interruption and role handoff with real devices), a real OpenAI-compatible model driving the prompts, and a real E2B sandbox executing a run. Everything else runs on the two labelled test doubles — `LLM_PROVIDER=scripted` and `EXECUTOR=local` — which is stated as such in the README.

## 11. Acceptance checks → tests

| PRD check | Where verified |
| --- | --- |
| Candidate interruption | pytest generation cancel; manual live voice |
| Role handoff, turn-taking | pytest controller rules; manual live voice |
| Code identity | pytest snapshot hash; Playwright opens run → snapshot |
| Known fixtures | pytest runs buggy, partial, complete, disabled-cache solutions |
| Adaptive interview | pytest controller with correct, vague, incomplete claims |
| Assessment references | pytest validator; Playwright opens every link |
| Revision handling | pytest revises link creation |
| Replay | pytest + Playwright rerun |
| Correction | pytest + Playwright dispute |
| Isolation | pytest cross-session and path rejection |
| Failure | pytest timeout and model failure paths |
| Cleanup | pytest expiry |
