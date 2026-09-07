# Quorum product requirements

Version 1.0 | 6 September 2026 | EchoSphere 2026 Agora Conversational AI Hackathon

This document specifies the first Quorum product, its technical design, a three-day build sequence, and a plan to test whether employers will pay for it. The product is proposed; its hiring benefits have not yet been validated. The repository currently contains the specification, not a working application.

## 1. The idea in plain words

Quorum is an AI recruitment interview where a software engineer investigates and changes a working application while an AI panel questions their decisions. The final assessment connects what they said to what their code actually did.

Basically, give someone a small app with a believable problem. Let them investigate, explain their thinking, and fix it while talking to AI interviewers. Then change one important condition and see how they respond. At the end, the hiring manager can check the work behind the assessment, including rerunning the relevant tests.

The central question is whether this candidate can make a sensible engineering decision, test it, and revise it when the evidence changes.

The first product replaces one technical screening round for backend engineers. It gives an engineering manager a short, inspectable account of the candidate's work. It does not make the hiring decision.

## 2. The problem and the buyer

A polished explanation does not establish that a proposed change works. A test result alone does not explain whether the candidate understood the customer problem. When interviews produce separate transcripts, code submissions, and scores, a hiring manager must reconstruct the connection between them.

There is also an interpretation problem. A candidate who changes their answer after discovering a bug may be doing good engineering. An assessment that simply labels the answers contradictory can miss that distinction. Quorum preserves the original answer, the new evidence, and the revision so a person can judge what happened.

Our initial buyer is an engineering manager at a small software company hiring Python backend engineers. The recruiter coordinates the interview and reads the summary. The manager inspects the engineering evidence. The candidate needs a clear task, a usable workspace, and a way to correct misunderstandings.

Start with one role and a supplied case. Candidate-owned repositories, CV claim verification, and arbitrary company code imports are later possibilities. The MVP does not establish who originally wrote a project or whether a candidate is being honest about their employment history.

The commercial hypothesis is that managers will pay to review demonstrated work faster without losing the ability to question the assessment. We must test this hypothesis with actual hiring teams.

## 3. What research changes about the product

Coinbase describes replacing parts of its engineering interview process with work in existing repositories and assessment of candidates' judgment about AI output. Its account supports choosing realistic engineering work, but its early results do not validate Quorum. [Coinbase interview redesign](https://www.coinbase.com/en-in/blog/interviewing-engineers-in-the-ai-era-lessons-from-a-year-of-rebuilding), published 13 July 2026.

The market already includes close alternatives. The following descriptions come from the providers' own product pages, not independent product tests.

| Alternative | What already exists | Consequence for Quorum |
| --- | --- | --- |
| Merge | Candidates review a pull request and respond to revisions from an AI teammate. | Reviewing real code with AI is not a novelty claim. |
| Woven | GitHub pull-request assessment with human scoring. | We must explain why live follow-ups and inspectable evidence are useful. |
| BrightHire | AI interviews with structured assessments and evidence. | Transcript-linked findings alone are insufficient differentiation. |
| Sova Immerse | Adaptive scenarios with simulated colleagues and customers. | Multiple roles and workplace simulations are already commercial products. |

Sources: [Merge](https://mergeoa.com/), [Woven code review assessment](https://www.woventeams.com/gen-ai-code-review/), [BrightHire candidate experience](https://brighthire.com/ai-interviewer/candidate-experience/), [Sova Immerse](https://www.sovaassessment.com/immerse). Accessed 6 September 2026.

Quorum's proposed distinction is a continuous connection between a live question, the candidate's answer, an executed code version, the observed result, and a reviewable assessment. The final map lets a reviewer open and rerun the work supporting a finding. This is a product hypothesis, not proof that no competitor has the same capability.

Structured interviewing also creates a constraint. OPM describes using consistent questions and rating standards. Our adaptation must retain common core tasks and record hints and additional challenges. We cannot compare two candidates as if they received identical conditions when they did not. [OPM structured interviews](https://www.opm.gov/policy-data-oversight/assessment-and-selection/structured-interviews/).

## 4. The single interview case

The case is a small document-search application used by several companies. A recent caching change improves repeated searches but can return another company's documents. The candidate reviews the change, investigates the behavior, and decides whether it can ship.

The application uses Python and synthetic data. Keep the editable implementation below roughly 200 lines across three files. Provide a short brief and a readable list of expected behaviors. This is a backend interview, so the candidate does not have to build a frontend.

### Application behavior

The supplied function accepts an authenticated user identifier and a search query, then returns document identifiers and titles. Company membership and document permissions come from fixture data. The caller cannot grant access by submitting a different company identifier.

The seeded cache incorrectly uses only the query as its key and stores previously filtered results. A query by a user at Company A can therefore affect what a user at Company B sees. A partial repair that separates users or companies may still serve stale results after permission revocation.

The required behaviors are:

- A user can see only documents allowed by their current permissions.
- Identical searches by different companies cannot leak documents across companies.
- Removing a user's access takes effect on the next request, including a cached request.
- Repeated authorized searches avoid repeating the expensive search operation where possible.

Use an instrumented search-call counter to measure avoided work. Do not claim a production latency improvement from a tiny synthetic benchmark.

Disabling caching is a valid immediate containment decision. It passes access checks but leaves the performance objective unresolved. The assessment must acknowledge that tradeoff rather than demand one preferred implementation.

### Interview roles

| Role | Main concern | Example follow-up |
| --- | --- | --- |
| Technical interviewer | Correctness, diagnosis, and testing. | "Which part of your change stops one company's search affecting another?" |
| Product manager | Release tradeoffs and business consequences. | "Would you ship the slower safe version today? What would you tell the team?" |
| Customer administrator | Current access and customer expectations. | "I removed an employee's access. Can they still retrieve a document they searched for earlier?" |

The roles can disagree about priorities, but they must use the same recorded facts. They must not manufacture conflict after the candidate has already addressed the concern.

### Interview sequence

1. Explain AI involvement, the task, data handling, and criteria. Test the microphone and offer text input.
2. Give the candidate the brief, application files, and basic tests. Allow quiet reading time.
3. Ask the candidate to explain the change and their initial release decision.
4. Let them inspect, edit, and run code. Follow up on their actual answer and observed results.
5. Introduce the access-revocation condition. Ask the candidate to check their solution under that condition.
6. Ask for a final release recommendation, remaining uncertainties, and next checks.
7. End the interview and show the assessment with its evidence map and correction option.

A normal session targets 20 minutes, with a 30-minute cap excluding explicit pauses. The live presentation uses a clearly labeled five-minute demonstration of the same workflow. Timing is configurable for accommodations; response speed is not an assessment dimension.

Every session covers the same core access conditions. Follow-ups can become more demanding when the candidate handles them independently. If they struggle, give a narrower prompt and record that help. If they identify both issues immediately, ask about limits or tests instead of pretending they missed the bug.

## 5. The user experience

During the interview, show a code editor, a small file tree, test output, captions, and the active interviewer's role. Keep microphone, pause, and end controls visible. Show a brief notice when new scenario information arrives. Do not show a growing graph during the conversation.

Save code when the candidate selects Save or Run. Display unsaved changes explicitly. A run always uses a saved snapshot. The panel cannot describe unsaved text as tested code.

The candidate can interrupt a mistaken premise, ask for clarification, or request thinking time. The panel must respond to the correction before continuing its previous line of questioning. Silence while reading code should not trigger repeated questions.

### The final evidence map

Start with four assessment dimensions and at most six expanded findings. A reviewer selects a finding to open its evidence path. Use fixed columns with readable cards, not a force-directed network.

```text
Statement -> Challenge -> Code and result -> Revision -> Finding
```

A typical finding could be: "The candidate corrected cross-company caching, then checked permission revocation after the customer prompt." It links to the original explanation, the hint, the code change, and both test runs.

Evidence links distinguish support, challenge, and revision. They represent recorded relationships; the visual must not imply that a graph proves causation or reveals the candidate's hidden thought process.

The reviewer can open the exact transcript segment, inspect the code difference, compare before and after results, and select Rerun test. A code-related finding without a runnable check can still link to the transcript and code, but must not display a replay control.

Replay restores the original code snapshot, scenario fixture, and check version. It creates a new run next to the original. If results differ, mark the finding for review and retain both results. Do not silently recalculate the historical assessment.

### Candidate correction

The candidate can flag a transcript mistake or a misunderstood statement and provide a correction. Preserve the original and the proposed correction. Mark findings that depend on that segment as needing review. Do not automatically accept the candidate's correction or defend the model's first interpretation.

The candidate sees their own report and corrections. A reviewer has a separate permission to inspect and resolve a dispute. This is a limited correction workflow, not a formal legal appeals system.

## 6. The assessment

Use four dimensions: understanding the problem, implementing and checking a fix, explaining customer and release consequences, and responding to new evidence.

Each dimension contains a finding, supporting and opposing evidence references, assistance received, remaining uncertainty, and one useful human follow-up if needed. Use demonstrated, partly demonstrated, or not observed. Keep needs review as a separate review status.

Example: "Partly demonstrated checking a fix. The candidate's revision passed company-separation checks. Revocation remained untested when the session ended. Ask how they would check cached access after a permission change."

A machine-observed pass supports a particular behavior under the recorded conditions. It does not prove that the code is secure, production-ready, or written without outside help. A candidate can explain a sound approach without finishing the code; represent the explanation and implementation evidence separately.

Do not generate an overall hire score, rank candidates, infer personality or emotion, grade accent, or label someone dishonest. The human hiring team decides whether to proceed.

## 7. Required hackathon behavior

| Requirement | MVP behavior |
| --- | --- |
| Real-time interruptible voice | Agora conversation yields when the candidate starts speaking. |
| Multiple interviewer roles | Technical, product, and customer roles have distinct objectives. |
| Shared context | Every role reads the same session record and completed runs. |
| Dynamic follow-ups | Questions refer to the latest answer, code version, or test result. |
| Controlled turn-taking | One controller selects the only role allowed to speak. |
| Scenario questions | The panel introduces revoked access in the running case. |
| Difficulty adjustment | Deeper probes or recorded hints follow candidate performance. |
| Vague or contradictory answers | Ask for clarification and check timing, scope, and new evidence. |
| Transcript-linked feedback | Every interpretive finding references actual interview segments. |
| Structured final assessment | Four dimensions, evidence, limitations, and human follow-up. |
| AI disclosure | Notice before joining and persistent AI role labels. |
| Meaningful external action | E2B executes candidate code and supports replay. |

Agora Conversational AI is the primary voice layer. E2B changes what can be assessed because questions can refer to executed behavior. The event's submission requirements include a working demonstration and supporting repository material. [EchoSphere on Commudle](https://www.commudle.com/communities/knotic/hackathons/echosphere).

The build sequence below uses the team's stated two to three days of available work. The published event schedule previously showed a different submission and evaluation window; this plan does not establish permission to change a project during evaluation.

## 8. System architecture

```text
Browser
  Next.js workspace, Monaco editor, captions, React Flow report
       | application requests                 | audio
       v                                      v
FastAPI backend <------------------- Agora Conversational AI
  Session controller                 custom streaming endpoint
  Evidence service
  Assessment service
       |
       +-- Configured language model
       +-- SQLite and immutable code snapshots
       +-- E2B sandbox execution
```

Use one Next.js frontend and one publicly reachable FastAPI backend. Run a single backend worker for the MVP so session locks and local SQLite remain consistent. Next.js proxies application requests to the backend. Agora calls the backend's custom model endpoint directly over HTTPS.

The language model generates questions and drafts interpretations. Application code controls stage transitions, permissions, execution, evidence identifiers, and replay. A prompt is not an authorization mechanism.

### Tools and why they are included

| Tool | Use |
| --- | --- |
| Next.js and TypeScript | Browser workspace and assessment pages. |
| Monaco Editor | Familiar editing and code comparison. |
| Agora Conversational AI | Live speech, interruption, and role conversation. |
| FastAPI and Pydantic | HTTP routes, streaming, and validated records. |
| One configurable language model | Follow-ups, claim extraction, and assessment drafting. |
| E2B Python SDK | Isolated execution of candidate code. |
| SQLite and local snapshot storage | Session events, results, and reproducible versions. |
| React Flow | Interactive findings with direct evidence controls. |
| pytest and Playwright | Backend checks and critical browser-flow verification. |

Use the official Agora handoff recipe as the starting reference. It demonstrates server-side role routing through a custom endpoint, but its supplied conversation is a mock and must be replaced. Start with its managed speech configuration, Deepgram nova-3 for recognition and MiniMax for speech, subject to account availability. One voice with explicit role labels is acceptable for the MVP. [Agora handoff recipe](https://recipes.agora.io/recipes/agent-handoff).

The model endpoint and model identifier are deployment configuration. Select one available, tool-capable model through an OpenAI-compatible API, record its identifier with every assessment, and use it consistently in the demo. Do not require a second model, agent framework, vector database, or graph database.

React Flow nodes can contain normal interface controls. Use that capability for opening evidence and starting replay. Fixed columns avoid the need for a graph-layout service. [React Flow custom nodes](https://reactflow.dev/learn/customization/custom-nodes).

## 9. Conversation and execution behavior

### One speech controller

The controller tracks the interview stage, active role, covered core tasks, hints, latest completed runs, open questions, and response generation number. Interview stages are briefing, initial review, investigation, changed condition, release discussion, and assessment.

Use one Agora session rather than three simultaneous speech agents. All roles receive the relevant shared state. Changing a role changes its instructions and visible label; it does not create a second speaker.

On candidate interruption, stop speech and cancel the current model response. Discard late speech chunks from the cancelled generation. A completed execution result is still stored, but cannot cause an old response to resume. Queue a newly relevant finding until the candidate finishes speaking. Agora provides an interruption-handling reference for this path. [Agora interruption recipe](https://recipes.agora.io/recipes/interruptions).

Stream only spoken text to Agora. Keep tool arguments, record identifiers, and assessment objects in application messages. Use a bounded recent transcript plus structured session state instead of repeatedly sending every event and code file to the model.

Before describing an answer as contradictory, check whether its scope or the available facts changed. Ask a neutral clarification if ambiguity remains. Store a proposed contradiction as an interpretation, never a verified fact.

### Runs and snapshots

Each Run action freezes the saved code, scenario data, and check definitions. Hash those inputs and keep their versions with the run. Use a fresh short-lived sandbox for each run or replay, with a prebuilt template that already contains dependencies. No package installation is needed during the interview.

The candidate implementation exposes a small JSON request and response protocol through a supplied wrapper. The backend sends scenario inputs to the isolated process and checks returned document identifiers against expected outcomes held outside candidate code. It does not trust a printed pass/fail label. This still does not make the assessment resistant to every deliberate attempt to game a known test.

Start with a 20-second execution deadline, 64 KB output cap, 100 KB total editable source limit, one active run per interview, and 20 runs per standard session. These are MVP defaults. A timeout is an execution failure, not proof of poor ability.

E2B sandboxes have internet access enabled by default in the SDK. Explicitly disable it, use secure access, and pass no application or provider secrets to the sandbox. Only the backend can create and control sandboxes. Kill them on completion and enforce a short lifetime if cleanup fails. [E2B sandbox SDK](https://github.com/e2b-dev/E2B/blob/main/packages/python-sdk/e2b/sandbox_sync/main.py).

Candidate source and transcript content are untrusted inputs. They cannot change the rubric, invoke arbitrary backend tools, select host file paths, or instruct the assessor to ignore previous rules.

### Failure behavior

- If voice disconnects, pause the interview, retain saved work, and allow reconnect or text continuation. Record any affected section.
- If execution fails, display unavailable and allow a bounded retry. Do not invent a result.
- If a model response contains invalid evidence references, retry validation once, then show the available observations with assessment pending.
- If the candidate edits code during a run, keep that run attached to its original snapshot.
- If repeated requests arrive, use an idempotency key so they do not create duplicate runs or assessments.
- If a replay differs, preserve both results and mark the related finding for review.

## 10. Data records and API

SQLite stores relational records. A separate directory stores source snapshots. Evidence relationships are ordinary rows with validated references, not free-form model-generated connections.

| Record | Required information |
| --- | --- |
| Interview | ID, scenario version, consent, status, stage, active role. |
| Transcript segment | ID, speaker, text, start/end timing, completion status. |
| Code snapshot | ID, allowed files, content hash, creation time. |
| Test run | ID, snapshot, fixture and check versions, results, execution status. |
| Claim | ID, source segment, statement, scope, interpretation status. |
| Evidence link | Source and target IDs, supports/challenges/revises relationship. |
| Finding | Dimension, observation level, explanation, references, review status. |
| Dispute | Original segment, proposed correction, affected findings, resolution. |
| Session event | Interview ID, sequence number, timestamp, event type, payload. |

Use immutable identifiers and append events when evidence changes. An assessment also records the rubric, prompt, and model versions. Referenced code snapshots remain unchanged until the interview is deleted.

### Application endpoints

| Endpoint | Purpose |
| --- | --- |
| POST /api/interviews | Create an interview after disclosure and consent. |
| POST /api/interviews/{id}/start | Return short-lived Agora join data and start the AI session. |
| PUT /api/interviews/{id}/files | Save allowed files and return a snapshot ID. |
| POST /api/interviews/{id}/runs | Execute a snapshot against the selected allowed checks. |
| GET /api/interviews/{id}/events | Stream ordered session events over SSE. |
| POST /api/interviews/{id}/finish | Stop voice and produce the assessment once active work settles. |
| GET /api/interviews/{id}/assessment | Read the report and evidence relationships. |
| POST /api/interviews/{id}/replays | Rerun a recorded run without changing its history. |
| POST /api/interviews/{id}/disputes | Attach a candidate correction and flag dependent findings. |
| POST /api/interviews/{id}/disputes/{disputeId}/resolve | Record a human reviewer's resolution. |
| DELETE /api/interviews/{id} | Delete app-owned interview records and snapshots. |
| POST /llm/{id}/chat/completions | Authenticated streaming endpoint called by Agora. |

These are proposed Quorum APIs, not Agora SDK method names. Document concrete request and response examples during implementation using FastAPI's generated OpenAPI schema.

Use separate candidate and reviewer capabilities, stored as hashed tokens server-side and exchanged for secure HTTP-only session cookies. An interview ID alone never grants access. Protect the Agora endpoint with a server-validated credential tied to the session. Validate origin and CSRF protection for cookie-authenticated mutations.

SSE events include role changes, final transcript segments, snapshot saves, run completion, pause state, assessment completion, and dispute updates. Sequence numbers allow a reconnecting browser to request missed events. Partial captions never become final assessment evidence without a completed segment.

### Configuration and deployment

Backend configuration includes AGORA_APP_ID, AGORA_APP_CERTIFICATE, CUSTOM_LLM_PUBLIC_BASE_URL, CUSTOM_LLM_AUTH_SECRET, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, E2B_API_KEY, SESSION_SECRET, DATABASE_PATH, SNAPSHOT_DIR, and ALLOWED_ORIGINS. Commit an example with variable names and explanations only.

Use local Next.js and FastAPI with an HTTPS tunnel for the first working demonstration. For a hosted demo, deploy Next.js separately and run FastAPI as a single persistent container with a disk for SQLite and snapshots. An ephemeral serverless filesystem is unsuitable for the stored evidence. Verify credentials, public callback reachability, speech support, and sandbox connectivity in the first build stage.

## 11. Proposed file structure

The application directories below describe the intended implementation.

```text
Quorum/
  README.md
  PRD.md
  PRD.docx
  .env.example
  web/
    app/
      interview/[id]/page.tsx
      assessment/[id]/page.tsx
    components/
      interview/       # panel, captions, microphone, pause
      workspace/       # editor, file list, test results
      evidence/        # findings, map, diff, replay, correction
    lib/
      api.ts
      agora.ts
      types.ts
    tests/
  server/
    app/
      main.py
      config.py
      routes/          # session, files, runs, reports, Agora
      interview/       # controller, role prompts, shared state
      evidence/        # claims, validation, findings, disputes
      execution/       # E2B adapter, checks, replay
      storage/         # models, event log, snapshots
    tests/
  scenarios/
    document-search/
      brief.md
      application/     # candidate-editable Python implementation
      fixtures/        # synthetic users, permissions, documents
      checks/          # versioned checks and expected outcomes
      rubric.json
  scripts/
    seed_demo.py
    smoke_test.py
```

## 12. Privacy and trust

Keep raw audio recording off in the application. Agora and the chosen speech/model providers still process audio or text. Do not describe this as zero retention. Before real recruitment, verify account-specific retention, training use, processing regions, and contractual terms.

Use only synthetic data for public demonstrations. Do not require a CV, webcam, identity document, or access to a private repository. Collect a display name or pseudonym and a session identifier. Disable analytics that capture full transcripts or code.

Default app-owned demo data to seven days of retention, with immediate deletion available. Implement expiry cleanup for database records and snapshots. For the hackathon demo, avoid backups containing interview content. Production backups, provider deletion, and legal retention requirements require a separate documented policy before a real employer pilot.

Show AI disclosure before consent and during the session. Allow pause, captions, and text input. Do not infer ability from accent, facial expression, typing speed, or apparent confidence. A transcript correction changes the review state, not the original record.

Human review does not by itself establish legal compliance. Any real hiring deployment needs review for its jurisdiction and actual use. Employment assessment accessibility and discrimination obligations remain relevant. [EEOC AI and disability resources](https://www.eeoc.gov/eeoc-disability-related-resources/artificial-intelligence-and-ada).

## 13. Build sequence and acceptance

### First day

Connect a real Agora conversation through the custom backend. Demonstrate interruption and a role change that retains context. Build the supplied case, editor, snapshot save, and one genuine sandbox run. Verify the buggy and corrected fixtures produce the expected different results.

The exit condition is a candidate explaining a change, running it, and receiving a relevant spoken follow-up based on the actual result. A scripted transcript or fabricated test response does not satisfy this condition.

### Second day

Complete the shared session record, scenario change, adaptive follow-ups, event stream, and structured assessment. Tie every finding to valid transcript or execution references. Add the candidate correction path and make changed answers distinguishable from unresolved contradictions.

### Third day

Build the final evidence map and replay interaction. Test interruption, reconnect, execution failure, and evidence accuracy. Rehearse a five-minute live demo and record the submission video. Keep the README accurate about what works and what remains limited.

Cut additional scenarios, distinct voices, avatars, arbitrary repository imports, scheduling, ATS connections, and general graph editing before cutting actual execution or evidence replay.

### Acceptance checks

| Check | Passing behavior |
| --- | --- |
| Candidate interruption | Speech stops and the next response addresses the correction. |
| Role handoff | The next role uses the prior answer and completed run correctly. |
| Turn-taking | At most one interviewer speaks at a time. |
| Code identity | Every result opens the exact source version that produced it. |
| Known fixtures | Buggy, partial, and complete solutions produce distinct expected outcomes. |
| Adaptive interview | Correct, vague, and incomplete answers lead to relevant different follow-ups. |
| Assessment references | All displayed links resolve to real session evidence. |
| Revision handling | New evidence followed by a changed answer can appear as a reasoned revision. |
| Replay | Original inputs are restored and original results remain unchanged. |
| Correction | Dependent findings become needs review without deleting the original. |
| Isolation | Cross-session reads and unauthorized file paths are rejected. |
| Failure | Timeout or model failure never becomes an invented candidate result. |
| Cleanup | Expired sessions and app-owned snapshots are removed. |

Test the controller and evidence rules with pytest. Use a browser end-to-end test for save, run, finish, evidence inspection, replay, and correction. Manually test live voice with actual devices, including interrupting just before a role change.

Target an audible stop within 500 milliseconds of detected interruption and roughly two seconds to first response audio for ordinary turns. These are proposed targets, not measured results or provider guarantees. Measure on the actual demo setup and report failures honestly.

## 14. The five minute demonstration

Start by showing the hiring question and the small app. In the first minute, the candidate reviews the cache and explains an initial decision. In the second, they reproduce the company-separation failure and make a partial fix. In the third, the customer role introduces revoked access and the candidate interrupts to refine the assumption, then checks the new condition.

Use the fourth minute for the final release explanation and assessment. Use the last minute to open one finding, inspect the earlier and later code results, and rerun the relevant check. Show where a candidate could flag a misunderstanding.

The demonstration may use a rehearsed participant and prepared starting code, but the conversation and execution must be live. Do not present prerecorded results as fresh execution. If replay fails, show that failure and the preserved original evidence.

The strongest moment is a reviewer checking the interviewer's conclusion and seeing exactly what the candidate demonstrated. The graph is only the route to that evidence.

## 15. Business model

### First paying customer

Start with software companies that have roughly 10 to 100 engineers, hire Python backend developers repeatedly, and currently ask senior engineers to run technical screens. These company sizes are a targeting choice, not a researched market-size estimate. Seek an engineering manager who can compare Quorum with an existing screening round and a recruiter who can help manage candidate invitations.

Avoid launching across every profession. A staffing agency may offer volume later, but it also adds role variety and pressure to rank candidates automatically. Large enterprises introduce procurement and compliance work before the product has established its value.

Sell a completed interview and its reviewable evidence. Do not charge candidates to apply or sell their interview data. Do not charge per rejection or promise a replacement for the final human interview.

### Proposed pricing experiment

Offer a paid pilot at USD 299 for up to 10 completed interviews using the supplied scenario, one onboarding session, and a review of the pilot results. This is a willingness-to-pay experiment, not a validated price. Infrastructure failures should not consume a paid completed-interview credit. Define completion as reaching the assessment stage with a usable evidence record.

After successful pilots, test USD 39 per completed interview with a monthly minimum of 10 interviews. The minimum makes ongoing support more predictable. Do not offer unlimited interviews or replay before measuring costs. Include a stated number of replays per completed interview, initially three, and a retention limit in any real commercial offer.

Custom company scenarios would require a separate setup fee because job analysis, fixture preparation, rubric review, and maintenance take human time. Do not include unlimited custom scenario creation in the basic price.

### Cost model

Agora currently lists audio tasks at USD 0.10 per minute, with selected speech and model services included. It states that bringing your own key does not reduce that unit rate. A 20-minute interview therefore has a USD 2.00 Agora audio-task component before other applicable charges. [Agora pricing](https://www.agora.io/en/pricing/conversational-ai-engine/), accessed 6 September 2026.

E2B separately bills running compute. Its published rates include USD 0.000028 per second for two vCPUs and USD 0.0000045 per GiB-second of memory. An illustrative 1,200 aggregate sandbox-seconds at two vCPUs and one GiB costs approximately USD 0.039 in compute. Actual template size, startup, retries, replay, and plan charges can change the total. Free promotional credits are not the basis of the business model. [E2B pricing](https://e2b.dev/pricing), accessed 6 September 2026.

Use this operating equation:

```text
Cost per completed interview =
  voice minutes and applicable media charges
  + model tokens outside included services
  + sandbox compute including failed runs and replay
  + hosting and storage allocation
  + support and scenario-maintenance allocation
```

Set an initial target of less than USD 5 in direct infrastructure cost per completed standard interview. This target is unmeasured. At a USD 39 price it would leave USD 34 before support, sales, scenario development, taxes, and other costs. It is not a profit forecast.

Record provider usage per session and include failed sessions when calculating the cost of delivering a successful interview. Set application limits on minutes, runs, and replays; do not let a public demo start unlimited paid sessions.

## 16. Marketing and sales

### Positioning

Use a concrete message: "See what an engineer demonstrated, and check the work behind the interview assessment."

Lead with the manager's review problem. Show an answer, a real code result, and the candidate's response to new information. Do not lead with agent counts, a knowledge graph, model names, or an unsupported claim of unbiased hiring.

The initial website needs one short live-product video, one synthetic sample assessment, a clear account of the candidate experience, and an invitation to a pilot. Explain the correction process and data handling before asking employers to involve candidates.

### First customer acquisition

After the hackathon, identify approximately 20 relevant engineering managers through existing relationships and engineering communities. Treat this as a proposed outreach target, not a contact list already assembled. Ask about the last technical screen they reviewed, what they could not verify, and how long that review took.

Demonstrate the final evidence review before giving a feature tour. Ask managers to inspect a sample and explain what remains uncertain. Invite a small number to a pilot only when the product addresses a problem they recognize.

Publish a short technical walkthrough of the case and a synthetic sample report. A practical post showing how a changed answer can represent good debugging is a better starting asset than broad claims about transforming recruitment. Share it where engineering managers already discuss interviewing, following community rules.

### Sales process

Start with a manager interview, then a product demonstration, then a voluntary pilot with a written scope. Agree on the role, scenario, retention, candidate disclosure, reviewer responsibilities, and success measures before inviting anyone.

For the first pilot, use volunteers or a parallel evaluation that does not determine candidate progression. Ask for payment for a subsequent limited pilot if the review workflow proves useful. A free demonstration is not proof of willingness to pay.

End each pilot with a decision: continue at the proposed price, revise the product around a specific recurring problem, or stop. Do not interpret praise for the graph as demand for the service.

## 17. Measuring impact and deciding what comes next

### Product validation

The first study should answer whether a manager can review the evidence faster while reaching a well-supported understanding of the candidate's work. It cannot establish long-term hiring quality from a handful of interviews.

Recruit three to five engineering reviewers and prepare at least 10 synthetic or consented interview records covering complete, partial, and unsuccessful solutions. Have each record reviewed in both formats by different reviewers: transcript plus code, and the Quorum report. Rotate assignments so a reviewer does not assess the same candidate twice from memory.

Before the exercise, prepare a reference account of what the code checks establish and which transcript statements are relevant. For subjective findings, have human reviewers record disagreement instead of pretending there is one mechanically correct grade.

| Measure | Initial success target |
| --- | --- |
| Review time | Median time at least 30% lower than transcript-plus-code review. |
| Evidence correctness | All displayed evidence references resolve to the correct records. |
| Reviewer understanding | Faster review does not reduce accuracy on reference questions. |
| Disagreement visibility | Reviewers can locate supporting and opposing evidence for disputed findings. |
| Candidate clarity | At least 80% of pilot respondents understand how a finding was supported. |
| Commercial interest | At least two target managers agree to a paid follow-on pilot. |

These are proposed decision thresholds, not achieved results. Report sample sizes, raw counts, and failures. Small samples can reveal usability problems but do not establish fairness across populations or predictive validity.

### Product measures after launch

Track invitation-to-start, start-to-completion, technical failure rate, time to assessment, evidence-link errors, correction frequency, reviewer time, cost per completed session, and paid repeat use. Distinguish voluntary abandonment from provider failure or an accessibility problem.

Store aggregate operational measurements separately from interview content. Do not collect audio or full code in analytics logs simply because it is convenient.

### Expansion order

First improve the existing case and review workflow. Add a second backend case only when users need repeat interviews and scenario reuse becomes a problem. Then test importing a carefully prepared employer scenario. Add ATS export when managers repeatedly ask to move the finished report into an existing hiring process.

Candidate-owned projects, additional languages, broader role coverage, and AI coding assistance inside the editor are later experiments. They must not delay a reliable first interview. Outside tools are neither policed nor represented as detectable in the MVP; Quorum makes no claim that it proves unaided performance.

### What might become hard to copy

The visual map, voice panel, and test runner are copyable. A more lasting advantage would come from well-reviewed scenarios, consistent evidence handling, trusted candidate experience, and proof that managers find the reports useful. That advantage must be earned through repeated use and maintenance. It does not exist on hackathon day.

## 18. Attack the idea before the judges do

"This is a coding assessment with a graph." That criticism is fair if the graph only summarizes the conversation. Demonstrate a reviewer opening a contested finding and rerunning its evidence. If that does not help a manager understand the candidate, simplify or remove the map.

"Merge or Woven could add this." They could. Do not claim otherwise. Our immediate opportunity is to demonstrate an unusually clear, interactive evidence review within a live multi-role interview. Longer-term differentiation needs customer validation, not more features.

"Your model can still judge incorrectly." Yes. Separate execution facts from interpretations, validate references, and expose uncertainty and corrections. The product should make a bad inference easier to notice rather than give it a more authoritative-looking diagram.

"This only works on a rehearsed puzzle." One scenario is a deliberate MVP limit. Demonstrate more than one candidate path and test complete, partial, and uncertain answers. The next milestone is a second case and review by people outside the team.

"Why does this need voice?" The candidate is changing code while discussing its consequences with different stakeholders. A correction can change the next question immediately, and the customer can introduce a new constraint without making the candidate abandon the task to fill out a form. Demonstrate interruption and shared context; do not rely on this explanation alone.

"A different team has a better live experience." That can win. Reliable speech, clear questions, fast evidence inspection, and a truthful demonstration matter more than feature count. Preserve those before adding presentation effects.

## 19. Release boundary

The hackathon release is complete when one candidate can finish the live interview, change and execute the supplied code, receive an evidence-linked assessment, replay a saved check, and flag a misunderstanding. It must satisfy the interview requirements without fabricated results.

The commercial release requires more: external reviewer validation, tested access and deletion controls, verified provider terms, appropriate legal review, stable costs, and an employer willing to pay. A successful stage demonstration does not establish those conditions.

PRD.md is the authoritative source. PRD.docx contains the same substantive text, tables, links, and technical examples with simple Word formatting. Future changes should update the Markdown first and regenerate the Word copy.
