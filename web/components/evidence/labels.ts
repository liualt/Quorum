/**
 * Human labels for the wire vocabularies the report displays.
 *
 * Every string a reviewer reads for an enum value comes from here, so a
 * vocabulary change in `lib/types.ts` is a change in one file and the compiler
 * points at every table that needs a new row.
 */

import type {
  AssessmentEvidence,
  ClaimType,
  Dimension,
  ObservationLevel,
  Ref,
  Relation,
  Role,
  RunStatus,
  RunView,
  SegmentKind,
  Speaker,
  Stage,
} from "@/lib/types";

/** Rubric titles, keyed by dimension id (`scenarios/document-search/rubric.json`). */
export const DIMENSION_TITLES: Record<Dimension, string> = {
  understanding_problem: "Understanding the problem",
  implementing_checking_fix: "Implementing and checking a fix",
  explaining_consequences: "Explaining customer and release consequences",
  responding_to_new_evidence: "Responding to new evidence",
};

export const LEVEL_LABELS: Record<ObservationLevel, string> = {
  demonstrated: "Demonstrated",
  partly_demonstrated: "Partly demonstrated",
  not_observed: "Not observed",
};

export const RELATION_LABELS: Record<Relation, string> = {
  supports: "supports",
  challenges: "challenges",
  revises: "revises",
};

export const KIND_LABELS: Record<SegmentKind, string> = {
  turn: "Turn",
  greeting: "Greeting",
  hint: "Hint",
  scenario_notice: "Scenario notice",
  follow_up: "Follow-up",
  clarification: "Clarification",
};

export const STAGE_LABELS: Record<Stage, string> = {
  briefing: "Briefing",
  initial_review: "Initial review",
  investigation: "Investigation",
  changed_condition: "Changed condition",
  release_discussion: "Release discussion",
  assessment: "Assessment",
};

export const CLAIM_TYPE_LABELS: Record<ClaimType, string> = {
  diagnosis: "Diagnosis",
  release_decision: "Release decision",
  fix_description: "Fix description",
  test_plan: "Test plan",
  uncertainty: "Uncertainty",
  question: "Question",
  other: "Statement",
};

export const RUN_STATUS_LABELS: Record<RunStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  timeout: "Timed out",
  failed: "Failed",
  unavailable: "Unavailable",
};

/*
 * The role names without the "AI" word: the design system requires the AI
 * disclosure to be the `AIBadge` component, rendered beside these, never a
 * word inside a string.
 */
const ROLE_LABELS: Record<Role, string> = {
  technical: "Technical interviewer",
  product: "Product manager",
  customer: "Customer administrator",
};

export function isAISpeaker(speaker: Speaker): speaker is Role {
  return speaker in ROLE_LABELS;
}

export function speakerLabel(speaker: Speaker): string {
  if (speaker === "candidate") return "Candidate";
  if (speaker === "system") return "System";
  return ROLE_LABELS[speaker];
}

/** "3 of 4 checks passed" for a completed run, otherwise its status. */
export function runOutcome(run: RunView): string {
  if (run.status !== "completed") return RUN_STATUS_LABELS[run.status];
  const results = run.results ?? [];
  const passed = results.filter((result) => result.passed).length;
  return `${passed} of ${results.length} checks passed`;
}

/**
 * A review reason as the backend writes it (`disputes.py::dispute_reason`,
 * `runs.py::execute_run`) into a sentence.
 */
export function reviewReasonLabel(reason: string): string {
  if (reason === "replay_differs") return "A rerun produced a different result";
  if (reason.startsWith("dispute:")) {
    return `Correction ${reason.slice("dispute:".length)} is open`;
  }
  return reason;
}

/** "access_filtering" → "Access filtering"; the fallback when the scenario's
 *  check names are not loaded. */
export function humanizeId(id: string): string {
  const words = id.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The first characters of a content hash — enough to tell two snapshots apart. */
export function shortHash(hash: string): string {
  return hash.slice(0, 12);
}

const dateTime = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

export function formatTime(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : dateTime.format(date);
}

/** Milliseconds since the session started as m:ss. */
export function formatOffset(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

export interface RefDescription {
  label: string;
  /** The record is an AI utterance, so the label needs the disclosure badge. */
  ai: boolean;
}

/** What to call a reference in a chip or a node heading. */
export function describeRef(ref: Ref, evidence: AssessmentEvidence): RefDescription {
  switch (ref.type) {
    case "segment": {
      const segment = evidence.segments[ref.id];
      if (!segment) return { label: `Segment ${ref.id}`, ai: false };
      return {
        label: `${speakerLabel(segment.speaker)} · ${KIND_LABELS[segment.kind]}`,
        ai: isAISpeaker(segment.speaker),
      };
    }
    case "claim": {
      const claim = evidence.claims[ref.id];
      return {
        label: claim ? CLAIM_TYPE_LABELS[claim.claim_type] : `Claim ${ref.id}`,
        ai: false,
      };
    }
    case "run": {
      const run = evidence.runs[ref.id];
      return { label: run ? `Run · ${runOutcome(run)}` : `Run ${ref.id}`, ai: false };
    }
    case "snapshot": {
      const snapshot = evidence.snapshots[ref.id];
      return {
        label: snapshot ? `Snapshot ${shortHash(snapshot.content_hash)}` : `Snapshot ${ref.id}`,
        ai: false,
      };
    }
  }
}
