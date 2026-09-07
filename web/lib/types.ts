/**
 * Wire types for the Quorum backend.
 *
 * Every interface here mirrors a view in
 * `docs/superpowers/plans/2026-09-07-quorum-interfaces.md` by name and by field
 * name. The string unions come from that document's "Value vocabularies"
 * section. Nothing in this file is derived or reshaped: what the server sends
 * is what these types describe.
 */

/* ---------------------------------------------------------------- vocabularies */

export type InterviewStatus =
  | "created"
  | "live"
  | "finishing"
  | "finished"
  | "deleted";

export type Stage =
  | "briefing"
  | "initial_review"
  | "investigation"
  | "changed_condition"
  | "release_discussion"
  | "assessment";

export type Role = "technical" | "product" | "customer";

export type VoiceStatus = "off" | "connecting" | "connected" | "disconnected";

export type Speaker = "candidate" | Role | "system";

export type SegmentKind =
  | "turn"
  | "greeting"
  | "hint"
  | "scenario_notice"
  | "follow_up"
  | "clarification";

export type SegmentStatus = "complete" | "interrupted" | "pending";

export type RunStatus =
  | "queued"
  | "running"
  | "completed"
  | "timeout"
  | "failed"
  | "unavailable";

export type Executor = "e2b" | "local" | "none";

export type ClaimType =
  | "diagnosis"
  | "release_decision"
  | "fix_description"
  | "test_plan"
  | "uncertainty"
  | "question"
  | "other";

export type ClaimScope =
  | "cross_company"
  | "revocation"
  | "efficiency"
  | "access"
  | "general";

export type Clarity = "clear" | "vague";

export type Relation = "supports" | "challenges" | "revises";

export type RefType = "segment" | "run" | "claim" | "snapshot";

export type Dimension =
  | "understanding_problem"
  | "implementing_checking_fix"
  | "explaining_consequences"
  | "responding_to_new_evidence";

export type ObservationLevel =
  | "demonstrated"
  | "partly_demonstrated"
  | "not_observed";

export type ReviewStatus = "ok" | "needs_review";

export type AssessmentStatus = "complete" | "pending";

export type DisputeStatus = "open" | "resolved";

/** Which capability the current viewer holds. */
export type Participant = "candidate" | "reviewer";

/** File name to file content, as snapshots and scenarios are carried on the wire. */
export type FileMap = Record<string, string>;

/* ----------------------------------------------------------------------- views */

export interface CheckView {
  id: string;
  name: string;
  description: string;
  behavior: string;
  introduced_at: string;
  available: boolean;
}

export interface ScenarioView {
  id: string;
  version: string;
  brief: string;
  editable_files: FileMap;
  readonly_files: FileMap;
  checks: CheckView[];
}

export interface InterviewView {
  id: string;
  display_name: string;
  status: InterviewStatus;
  stage: Stage;
  active_role: Role;
  paused: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  me: Participant;
  /** Null until the interview has actually spoken to a model. */
  model_id: string | null;
  voice_enabled: boolean;
  voice_status: VoiceStatus;
  scenario: ScenarioView;
  latest_snapshot_id: string | null;
  runs_used: number;
  run_limit: number;
  session_cap_minutes: number;
}

/**
 * What the browser needs to join the voice channel.
 *
 * A union rather than one optional-field shape, because the server really does
 * send only `{enabled: false}` when voice is off or the agent failed to start —
 * `app/routes/interviews.py::_join_voice`. Checking `enabled` first is therefore
 * the only safe way to reach the Agora fields, and the compiler enforces it.
 */
export type JoinView =
  | {
      enabled: true;
      app_id: string;
      channel: string;
      uid: number;
      token: string;
      agent_uid: number;
      agent_id: string;
    }
  | {
      enabled: false;
      /** Present only when voice was configured but the agent could not start. */
      reason?: string;
    };

export interface SnapshotView {
  id: string;
  files: FileMap;
  content_hash: string;
  byte_size: number;
  created_at: string;
}

/**
 * One step of a check. Every field but `index` and `op` can be null: when the
 * runner returns no result for a step, `checks.py::_step_result` fills it with
 * nulls rather than inventing a failure. `ok: null` therefore means "not
 * observed", which is not the same as "failed" — render it as unknown.
 */
export interface CheckStepResult {
  index: number;
  op: string;
  /** Document ids the step expected. Null for a step with nothing to compare. */
  expected: string[] | null;
  actual: string[] | null;
  ok: boolean | null;
  error: string | null;
}

/**
 * One check's outcome. The counters are null when the check has no search
 * budget or the runner reported none, and `efficiency_ok` is null when there
 * was no budget to judge against — again "not measured", not "within budget".
 */
export interface CheckResultDict {
  check_id: string;
  passed: boolean;
  steps: CheckStepResult[];
  search_calls: number | null;
  max_search_calls: number | null;
  efficiency_ok: boolean | null;
  error: string | null;
}

export interface RunView {
  id: string;
  snapshot_id: string;
  status: RunStatus;
  check_ids: string[];
  results: CheckResultDict[] | null;
  executor: Executor;
  sandbox_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  replay_of: string | null;
  differs_from_original: boolean | null;
  fixture_version: string;
  check_version: string;
  input_hash: string;
  stdout_excerpt: string | null;
  stderr_excerpt: string | null;
  created_at: string;
}

export interface SegmentView {
  id: string;
  seq: number;
  speaker: Speaker;
  kind: SegmentKind;
  text: string;
  spoken_text: string | null;
  status: SegmentStatus;
  stage: Stage;
  generation: number;
  start_ms: number | null;
  end_ms: number | null;
  created_at: string;
}

export interface ClaimView {
  id: string;
  segment_id: string;
  statement: string;
  claim_type: ClaimType;
  scope: ClaimScope;
  stage: Stage;
  clarity: Clarity;
  interpretation_status: string;
  created_at: string;
}

export interface LinkView {
  id: string;
  source_type: RefType;
  source_id: string;
  target_type: RefType;
  target_id: string;
  relation: Relation;
}

export interface Ref {
  type: RefType;
  id: string;
}

export interface FindingView {
  id: string;
  dimension: Dimension;
  is_dimension: boolean;
  title: string;
  observation_level: ObservationLevel;
  explanation: string;
  supporting_refs: Ref[];
  opposing_refs: Ref[];
  assistance: string;
  uncertainty: string;
  follow_up: string;
  review_status: ReviewStatus;
  review_reasons: string[];
  has_run_ref: boolean;
}

/** The trimmed snapshot shape carried inside an assessment's evidence bundle. */
export interface SnapshotRef {
  id: string;
  content_hash: string;
  created_at: string;
}

export interface AssessmentEvidence {
  segments: Record<string, SegmentView>;
  runs: Record<string, RunView>;
  claims: Record<string, ClaimView>;
  snapshots: Record<string, SnapshotRef>;
  links: LinkView[];
}

export interface DisputeView {
  id: string;
  segment_id: string;
  original_text: string;
  proposed_text: string;
  reason: string;
  affected_finding_ids: string[];
  status: DisputeStatus;
  resolution: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface AssessmentView {
  id: string;
  status: AssessmentStatus;
  model_id: string;
  rubric_version: string;
  prompt_version: string;
  summary: string;
  created_at: string;
  dimensions: FindingView[];
  findings: FindingView[];
  evidence: AssessmentEvidence;
  disputes: DisputeView[];
  me: Participant;
  interview: { id: string; display_name: string; finished_at: string | null };
}

/* -------------------------------------------------------- request / response shapes */

export interface CreateInterviewResult {
  id: string;
  candidate_path: string;
  reviewer_token: string;
  reviewer_path: string;
}

export interface ExchangeResult {
  interview_id: string;
  kind: Participant;
}

export interface StartInterviewResult {
  voice: JoinView;
}

export interface PausedResult {
  paused: boolean;
}

export interface SaveFilesResult {
  snapshot_id: string;
  content_hash: string;
  created_at: string;
}

export interface TurnResult {
  segment_id: string;
  role: Role;
  text: string;
  stage: Stage;
}

export interface TranscriptResult {
  segment_id: string | null;
}

export interface FinishResult {
  assessment_id: string;
  status: AssessmentStatus;
}

/* --------------------------------------------------------------------- events */

/**
 * Every server-sent event type on `GET /api/interviews/{id}/events`.
 *
 * This is a value, not just a type, because the SSE stream names each event and
 * `lib/events.ts` has to register one `addEventListener` per name. Deriving the
 * union from the array keeps the two from drifting apart.
 */
export const SESSION_EVENT_TYPES = [
  "stage_changed",
  "role_changed",
  "transcript_segment",
  "segment_updated",
  "snapshot_saved",
  "run_started",
  "run_completed",
  "pause_changed",
  "scenario_notice",
  "assessment_completed",
  "dispute_updated",
  "voice_status",
  "interview_finished",
] as const;

export type SessionEventType = (typeof SESSION_EVENT_TYPES)[number];

/**
 * Payloads keyed by event type. Consumers narrow with
 * `if (event.type === "run_completed")`, which resolves `payload` to `{run}`.
 */
export interface SessionEventPayloads {
  stage_changed: { stage: Stage };
  role_changed: { role: Role };
  transcript_segment: { segment: SegmentView };
  segment_updated: { segment: SegmentView };
  snapshot_saved: {
    snapshot_id: string;
    content_hash: string;
    files: string[];
  };
  run_started: { run: RunView };
  run_completed: { run: RunView };
  pause_changed: { paused: boolean };
  scenario_notice: {
    segment_id: string;
    text: string;
    checks_unlocked: string[];
  };
  assessment_completed: { assessment_id: string; status: AssessmentStatus };
  dispute_updated: { dispute: DisputeView };
  voice_status: { status: VoiceStatus };
  interview_finished: Record<string, never>;
}

export type SessionEvent = {
  [T in SessionEventType]: {
    seq: number;
    ts: string;
    type: T;
    payload: SessionEventPayloads[T];
  };
}[SessionEventType];
