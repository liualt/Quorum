"use client";

import { useCallback, useMemo, useState } from "react";

import { saveFiles, startRun } from "@/lib/api";
import type { CheckView, FileMap, RunStatus, RunView } from "@/lib/types";

import { errorMessage } from "./errorMessage";

/** PRD §9: a bounded retry after an execution failure. */
const MAX_RETRIES_PER_RUN = 2;

const TERMINAL_RUN_STATUSES: ReadonlySet<RunStatus> = new Set([
  "completed",
  "timeout",
  "failed",
  "unavailable",
]);

function isTerminal(run: RunView): boolean {
  return run.finished_at !== null || TERMINAL_RUN_STATUSES.has(run.status);
}

function union(set: Set<string>, ids: string[]): Set<string> {
  const next = new Set(set);
  for (const id of ids) next.add(id);
  return next;
}

/** What the workspace hands over once the interview has loaded. */
export interface CodeSeed {
  files: FileMap;
  snapshotId: string | null;
  /** The server's hash of `files`, when they came from a saved snapshot. */
  contentHash: string | null;
  runs: RunView[];
  availableCheckIds: string[];
}

/**
 * The source last shown as saved, with the snapshot that holds it.
 *
 * The three move together: a snapshot id is only meaningful next to the files
 * it was cut from, so nothing may replace one without the others.
 */
interface SavedSource {
  files: FileMap;
  snapshotId: string | null;
  contentHash: string | null;
}

const NOTHING_SAVED: SavedSource = { files: {}, snapshotId: null, contentHash: null };

/**
 * The code half of the workspace: the editable files, their saved snapshot,
 * the checks to run, and the runs with their results.
 *
 * Runs are keyed by id and upserted from both the `POST /runs` response and
 * the event stream; a run that has already finished is never regressed to an
 * earlier state, whichever of the two arrives second.
 *
 * The saved snapshot is owned by the `PUT /files` response, which is the one
 * place the id and the source it holds are known together. A `snapshot_saved`
 * event carries the id and content hash but not the source, so it is adopted
 * only when its hash matches what is already shown as saved: the stream
 * replays the whole history on every reconnect, and an older snapshot's event
 * must not move the "saved" marker off newer work.
 */
export function useCodeAndRuns(
  interviewId: string,
  scenarioChecks: CheckView[],
  /** Saving and running are only allowed while the interview is live. */
  active: boolean,
) {
  const [files, setFiles] = useState<FileMap>({});
  const [saved, setSaved] = useState<SavedSource>(NOTHING_SAVED);
  const [saving, setSaving] = useState(false);
  const [runs, setRuns] = useState<Map<string, RunView>>(() => new Map());
  const [selectedChecks, setSelectedChecks] = useState<Set<string>>(() => new Set());
  const [unlockedChecks, setUnlockedChecks] = useState<Set<string>>(() => new Set());
  // Retries are counted against the first run of a chain, so retrying a
  // retry does not start the budget over.
  const [retryRoots, setRetryRoots] = useState<Map<string, string>>(() => new Map());
  const [retries, setRetries] = useState<Map<string, number>>(() => new Map());
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  /* ----------------------------------------------------------- inbound */

  const seed = useCallback((data: CodeSeed) => {
    setFiles(data.files);
    setSaved({ files: data.files, snapshotId: data.snapshotId, contentHash: data.contentHash });
    setSelectedChecks(new Set(data.availableCheckIds));
    setRuns(new Map(data.runs.map((run) => [run.id, run])));
  }, []);

  const setFile = useCallback((name: string, content: string) => {
    setFiles((prev) => ({ ...prev, [name]: content }));
  }, []);

  const noteSnapshotSaved = useCallback((snapshotId: string, contentHash: string) => {
    setSaved((prev) =>
      prev.contentHash === contentHash && prev.snapshotId !== snapshotId
        ? { ...prev, snapshotId }
        : prev,
    );
  }, []);

  const upsertRun = useCallback((run: RunView) => {
    setRuns((prev) => {
      const current = prev.get(run.id);
      if (current && isTerminal(current) && !isTerminal(run)) return prev;
      return new Map(prev).set(run.id, run);
    });
  }, []);

  const unlockChecks = useCallback((ids: string[]) => {
    setUnlockedChecks((prev) => union(prev, ids));
    setSelectedChecks((prev) => union(prev, ids));
  }, []);

  const toggleCheck = useCallback((checkId: string) => {
    setSelectedChecks((prev) => {
      const next = new Set(prev);
      if (next.has(checkId)) next.delete(checkId);
      else next.add(checkId);
      return next;
    });
  }, []);

  /* ----------------------------------------------------------- derived */

  const checks = useMemo(
    () =>
      scenarioChecks.map((check) =>
        check.available || unlockedChecks.has(check.id) ? { ...check, available: true } : check,
      ),
    [scenarioChecks, unlockedChecks],
  );
  const savedFiles = saved.files;
  const snapshotId = saved.snapshotId;
  const dirtyFiles = useMemo(
    () => new Set(Object.keys(files).filter((name) => files[name] !== savedFiles[name])),
    [files, savedFiles],
  );
  const dirty = dirtyFiles.size > 0;
  // The starter code has to be saved once before it can run.
  const needsSave = dirty || snapshotId === null;
  const runList = useMemo(
    () => Array.from(runs.values()).sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [runs],
  );
  const runActive = runList.some((run) => run.status === "queued" || run.status === "running");

  /* ----------------------------------------------------------- actions */

  const save = useCallback(async () => {
    if (!needsSave || saving || !active) return;
    const snapshot = { ...files };
    setSaving(true);
    setError(null);
    try {
      const result = await saveFiles(interviewId, snapshot);
      // The files sent, not the editor's current ones: an edit made while the
      // request was in flight stays unsaved.
      setSaved({
        files: snapshot,
        snapshotId: result.snapshot_id,
        contentHash: result.content_hash,
      });
      setStatus(`Saved snapshot ${result.snapshot_id}`);
    } catch (cause) {
      setError(errorMessage(cause, "Could not save. Try again."));
    } finally {
      setSaving(false);
    }
  }, [active, files, interviewId, needsSave, saving]);

  const launchRun = useCallback(
    async (snapshot: string, checkIds: string[], chainRoot: string | null) => {
      setError(null);
      try {
        const run = await startRun(interviewId, snapshot, checkIds, crypto.randomUUID());
        if (chainRoot) setRetryRoots((prev) => new Map(prev).set(run.id, chainRoot));
        upsertRun(run);
        setStatus(`Run ${run.id} queued on snapshot ${snapshot}`);
      } catch (cause) {
        setError(errorMessage(cause, "Could not start the run. Try again."));
      }
    },
    [interviewId, upsertRun],
  );

  const run = useCallback(() => {
    if (!snapshotId) return;
    // Scenario order, so the same selection always produces the same request.
    const ids = checks.filter((check) => selectedChecks.has(check.id)).map((c) => c.id);
    void launchRun(snapshotId, ids, null);
  }, [checks, launchRun, selectedChecks, snapshotId]);

  const rootOf = useCallback((runId: string) => retryRoots.get(runId) ?? runId, [retryRoots]);

  const retriesLeft = useCallback(
    (target: RunView) =>
      Math.max(0, MAX_RETRIES_PER_RUN - (retries.get(rootOf(target.id)) ?? 0)),
    [retries, rootOf],
  );

  const retry = useCallback(
    (failed: RunView) => {
      const root = rootOf(failed.id);
      setRetries((prev) => new Map(prev).set(root, (prev.get(root) ?? 0) + 1));
      void launchRun(failed.snapshot_id, failed.check_ids, root);
    },
    [launchRun, rootOf],
  );

  return {
    files,
    setFile,
    dirtyFiles,
    dirty,
    needsSave,
    snapshotId,
    noteSnapshotSaved,
    saving,
    checks,
    selectedChecks,
    toggleCheck,
    unlockChecks,
    runList,
    runActive,
    runsUsed: runs.size,
    upsertRun,
    seed,
    save,
    run,
    retry,
    retriesLeft,
    status,
    error,
    setError,
  };
}
