/**
 * Which two snapshots a code diff compares, and which run a result compares
 * with — pure lookups over the assessment's evidence and the interview's runs.
 */

import type { AssessmentEvidence, Ref, RunView } from "@/lib/types";

export interface DiffTarget {
  /** The snapshot the reference points at. */
  modifiedId: string;
  /** The interview's snapshot before it, or null when it was the first. */
  originalId: string | null;
}

/**
 * The diff for a run or snapshot reference.
 *
 * There is no list-snapshots route, so the known snapshots are the cited ones
 * (with their own `created_at`) plus every run's snapshot, dated by the run
 * that used it — a run always comes after its snapshot, so that date is a safe
 * upper bound. The previous snapshot is the latest one dated before the target.
 */
export function diffTargetFor(
  ref: Ref,
  evidence: AssessmentEvidence,
  runs: RunView[],
): DiffTarget | null {
  const known = new Map<string, number>();
  const note = (id: string, iso: string) => {
    const at = Date.parse(iso);
    const seen = known.get(id);
    if (seen === undefined || at < seen) known.set(id, at);
  };
  for (const run of runs) note(run.snapshot_id, run.created_at);
  for (const snapshot of Object.values(evidence.snapshots)) {
    note(snapshot.id, snapshot.created_at);
  }

  let modifiedId: string;
  let modifiedAt: number | undefined;
  if (ref.type === "run") {
    const run = runs.find((item) => item.id === ref.id) ?? evidence.runs[ref.id];
    if (!run) return null;
    modifiedId = run.snapshot_id;
    modifiedAt = known.get(run.snapshot_id) ?? Date.parse(run.created_at);
  } else if (ref.type === "snapshot") {
    modifiedId = ref.id;
    modifiedAt = known.get(ref.id);
    if (modifiedAt === undefined) return null;
  } else {
    return null;
  }

  let originalId: string | null = null;
  let originalAt = -Infinity;
  for (const [id, at] of known) {
    if (id === modifiedId || at >= modifiedAt) continue;
    if (at > originalAt) {
      originalAt = at;
      originalId = id;
    }
  }
  return { modifiedId, originalId };
}

/** The candidate's most recent completed run before this one, if any. */
export function runBefore(run: RunView, runs: RunView[]): RunView | null {
  let before: RunView | null = null;
  for (const item of runs) {
    if (item.id === run.id || item.replay_of || item.status !== "completed") continue;
    if (item.created_at >= run.created_at) continue;
    if (!before || item.created_at > before.created_at) before = item;
  }
  return before;
}

/** The reruns of this run, oldest first. */
export function replaysOf(run: RunView, runs: RunView[]): RunView[] {
  return runs
    .filter((item) => item.replay_of === run.id)
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
}

export function isRunActive(run: RunView): boolean {
  return run.status === "queued" || run.status === "running";
}
