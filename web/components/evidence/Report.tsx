"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button, ButtonLink } from "@/components/ui/Button";
import { ErrorText } from "@/components/ui/ErrorText";
import { Panel } from "@/components/ui/Panel";
import {
  ApiError,
  createDispute,
  getAssessment,
  getInterview,
  listRuns,
  resolveDispute,
  startReplay,
} from "@/lib/api";
import { useSessionEvents } from "@/lib/events";
import type {
  AssessmentView,
  InterviewView,
  Ref,
  RunView,
  SessionEvent,
} from "@/lib/types";

import { DimensionCard } from "./DimensionCard";
import { DisputeList } from "./DisputeList";
import { EvidenceMap } from "./EvidenceMap";
import type { DrawerTab } from "./evidenceGraph";
import { FindingCard } from "./FindingCard";
import { FindingList } from "./FindingList";
import { RefDrawer, type DrawerTarget } from "./RefDrawer";
import { ReportHeader } from "./ReportHeader";
import { diffTargetFor } from "./runDiff";
import { useSnapshots } from "./useSnapshots";

interface LoadFailure {
  status: number;
  message: string;
}

const isAbort = (cause: unknown) =>
  cause instanceof DOMException && cause.name === "AbortError";

function describeFailure(cause: unknown): LoadFailure {
  if (cause instanceof ApiError) return { status: cause.status, message: cause.detail };
  return { status: 0, message: "Could not reach the Quorum server." };
}

/*
 * How long to wait before re-reading the report after an event. The stream
 * replays the interview's whole history on connect, and a rerun produces a
 * `run_started` and a `run_completed` in quick succession; one read covers
 * whatever arrived in the window.
 */
const REFRESH_DELAY_MS = 150;

/*
 * How often to look again for a report that does not exist yet while the
 * interview is still finishing — a page reloaded during "ending the
 * interview" lands here before the assessment is stored.
 */
const FINISHING_POLL_MS = 1_500;

/**
 * The assessment report: loads the view, keeps it current from the event
 * stream, and owns what is selected and what the drawer shows. Everything
 * below it is presentational and gets the data it needs as props.
 */
export function Report({ interviewId }: { interviewId: string }) {
  const [assessment, setAssessment] = useState<AssessmentView | null>(null);
  const [runs, setRuns] = useState<RunView[]>([]);
  const [interview, setInterview] = useState<InterviewView | null>(null);
  const [failure, setFailure] = useState<LoadFailure | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [chosenFindingId, setChosenFindingId] = useState<string | null>(null);
  const [target, setTarget] = useState<DrawerTarget | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const [view, runList] = await Promise.all([
          getAssessment(interviewId, controller.signal),
          listRuns(interviewId, controller.signal),
        ]);
        setAssessment(view);
        setRuns(runList);
        setFailure(null);
      } catch (cause) {
        if (!isAbort(cause)) setFailure(describeFailure(cause));
        return;
      }
      try {
        setInterview(await getInterview(interviewId, controller.signal));
      } catch {
        // Without it, check names fall back to their ids and a diff with no
        // earlier snapshot says so; the report itself is unaffected.
      }
    };
    void load();
    return () => controller.abort();
  }, [interviewId, attempt]);

  // No report yet, but the interview is finishing: it is on its way, so keep
  // looking rather than leave the candidate on "No report yet" after a reload.
  // An interview that is still live is not polled; its report is not coming.
  useEffect(() => {
    if (failure?.status !== 404) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | null = null;
    (async () => {
      try {
        const view = await getInterview(interviewId, controller.signal);
        if (view.status !== "finishing" && view.status !== "finished") return;
      } catch (cause) {
        if (isAbort(cause)) return;
        // Unreachable for the moment; try the report again anyway.
      }
      timer = setTimeout(() => setAttempt((count) => count + 1), FINISHING_POLL_MS);
    })();
    return () => {
      controller.abort();
      if (timer !== null) clearTimeout(timer);
    };
  }, [failure, interviewId]);

  /** Re-read the report and the runs; the server's state replaces ours. */
  const refresh = useCallback(async () => {
    try {
      const [view, runList] = await Promise.all([
        getAssessment(interviewId),
        listRuns(interviewId),
      ]);
      setAssessment(view);
      setRuns(runList);
      setRefreshError(null);
    } catch (cause) {
      setRefreshError(
        cause instanceof ApiError ? cause.detail : "Could not refresh the report.",
      );
    }
  }, [interviewId]);

  // The event handler reads the latest state through a ref, so the stream is
  // not torn down and replayed on every render.
  const latest = useRef({ assessment, runs });
  useEffect(() => {
    latest.current = { assessment, runs };
  }, [assessment, runs]);

  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleRefresh = useCallback(() => {
    if (refreshTimer.current !== null) return;
    refreshTimer.current = setTimeout(() => {
      refreshTimer.current = null;
      void refresh();
    }, REFRESH_DELAY_MS);
  }, [refresh]);
  useEffect(
    () => () => {
      if (refreshTimer.current !== null) clearTimeout(refreshTimer.current);
    },
    [],
  );

  // Idempotent by construction: an event only triggers a read when it says
  // something the current state does not, so the history replay on connect
  // costs nothing once the report is loaded.
  const onEvent = useCallback(
    (event: SessionEvent) => {
      const { assessment: current, runs: knownRuns } = latest.current;
      if (!current) return;
      switch (event.type) {
        case "run_started":
        case "run_completed": {
          const run = event.payload.run;
          const known = knownRuns.find((item) => item.id === run.id);
          if (!known || known.status !== run.status) scheduleRefresh();
          return;
        }
        case "dispute_updated": {
          const dispute = event.payload.dispute;
          const known = current.disputes.find((item) => item.id === dispute.id);
          if (
            !known ||
            known.status !== dispute.status ||
            known.affected_finding_ids.join() !== dispute.affected_finding_ids.join()
          ) {
            scheduleRefresh();
          }
          return;
        }
        case "assessment_completed":
          if (current.id !== event.payload.assessment_id) scheduleRefresh();
          return;
        default:
          return;
      }
    },
    [scheduleRefresh],
  );
  useSessionEvents(assessment ? interviewId : null, onEvent);

  const selectedFinding = useMemo(() => {
    if (!assessment) return null;
    return (
      assessment.findings.find((finding) => finding.id === chosenFindingId) ??
      assessment.findings[0] ??
      null
    );
  }, [assessment, chosenFindingId]);

  const checkNames = useMemo(
    () =>
      Object.fromEntries(
        (interview?.scenario.checks ?? []).map((check) => [check.id, check.name]),
      ),
    [interview],
  );

  const diff = useMemo(
    () => (target && assessment ? diffTargetFor(target.ref, assessment.evidence, runs) : null),
    [target, assessment, runs],
  );
  const snapshotIds = useMemo(
    () => (diff ? [diff.modifiedId, ...(diff.originalId ? [diff.originalId] : [])] : []),
    [diff],
  );
  const snapshots = useSnapshots(interviewId, snapshotIds);

  const openRef = useCallback((ref: Ref, tab: DrawerTab) => setTarget({ ref, tab }), []);
  const closeDrawer = useCallback(() => setTarget(null), []);

  const rerun = useCallback(
    async (runId: string) => {
      await startReplay(interviewId, runId);
      await refresh();
    },
    [interviewId, refresh],
  );
  const fileDispute = useCallback(
    async (segmentId: string, proposedText: string, reason: string) => {
      await createDispute(interviewId, segmentId, proposedText, reason);
      await refresh();
    },
    [interviewId, refresh],
  );
  const resolve = useCallback(
    async (disputeId: string, resolution: string) => {
      await resolveDispute(interviewId, disputeId, resolution);
      await refresh();
    },
    [interviewId, refresh],
  );

  if (failure) {
    return (
      <LoadFailureView
        failure={failure}
        interviewId={interviewId}
        onRetry={() => setAttempt((count) => count + 1)}
      />
    );
  }
  if (!assessment) {
    return (
      <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6">
        <h1 className="sr-only">Assessment</h1>
        <p role="status" className="text-muted-foreground text-sm">
          Loading the report…
        </p>
      </main>
    );
  }

  const { evidence } = assessment;
  const allFindings = [...assessment.dimensions, ...assessment.findings];

  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6">
      <ReportHeader assessment={assessment} />
      {refreshError ? <ErrorText className="mt-4">{refreshError}</ErrorText> : null}

      <section aria-labelledby="dimensions-heading" className="mt-8">
        <h2 id="dimensions-heading" className="mb-3 text-lg font-semibold">
          Dimensions
        </h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {assessment.dimensions.map((finding) => (
            <DimensionCard
              key={finding.id}
              finding={finding}
              evidence={evidence}
              onOpen={openRef}
            />
          ))}
        </div>
      </section>

      <section aria-labelledby="findings-heading" className="mt-8 grid grid-cols-1 gap-4">
        <h2 id="findings-heading" className="text-lg font-semibold">
          Findings
        </h2>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <FindingList
            findings={assessment.findings}
            selectedId={selectedFinding?.id ?? null}
            onSelect={setChosenFindingId}
          />
          {selectedFinding ? (
            <FindingCard
              finding={selectedFinding}
              title={selectedFinding.title || "Finding"}
              evidence={evidence}
              onOpen={openRef}
              headingLevel={3}
            />
          ) : null}
        </div>
        <div className="grid grid-cols-1 gap-2">
          <h3 className="text-sm font-semibold tracking-wide uppercase">Evidence path</h3>
          {selectedFinding ? (
            <EvidenceMap finding={selectedFinding} evidence={evidence} onOpen={openRef} />
          ) : (
            <p className="text-muted-foreground text-sm">
              Select a finding to see its evidence path.
            </p>
          )}
        </div>
      </section>

      <section aria-labelledby="corrections-heading" className="mt-8 grid grid-cols-1 gap-3">
        <h2 id="corrections-heading" className="text-lg font-semibold">
          Corrections
        </h2>
        <DisputeList
          disputes={assessment.disputes}
          findings={allFindings}
          me={assessment.me}
          onResolve={resolve}
          emptyText="No corrections have been filed. Open a transcript segment to flag one."
        />
      </section>

      {target ? (
        <RefDrawer
          target={target}
          assessment={assessment}
          runs={runs}
          checkNames={checkNames}
          snapshots={snapshots}
          diff={diff}
          fallbackFiles={interview?.scenario.editable_files ?? null}
          onClose={closeDrawer}
          onRerun={rerun}
          onCreateDispute={fileDispute}
          onResolveDispute={resolve}
        />
      ) : null}
    </main>
  );
}

interface LoadFailureViewProps {
  failure: LoadFailure;
  interviewId: string;
  onRetry: () => void;
}

function LoadFailureView({ failure, interviewId, onRetry }: LoadFailureViewProps) {
  const notReady = failure.status === 404;
  const noAccess = failure.status === 401 || failure.status === 403;
  return (
    <main className="mx-auto w-full max-w-xl px-4 py-12 sm:px-6">
      <h1 className="sr-only">Assessment</h1>
      <Panel
        title={
          notReady ? "No report yet" : noAccess ? "No access" : "Could not load the report"
        }
      >
        <div className="grid gap-4">
          {notReady ? (
            <p className="text-sm">
              This interview has not finished, so there is no assessment to show yet. The
              report appears once the session has ended.
            </p>
          ) : noAccess ? (
            <p className="text-sm">
              This browser does not hold a key for this interview. Open the report from your
              candidate link, or from the reviewer link you were given.
            </p>
          ) : (
            <ErrorText>{failure.message}</ErrorText>
          )}
          <div className="flex flex-wrap gap-2">
            {notReady ? (
              <ButtonLink href={`/interview/${interviewId}`} variant="secondary">
                Back to the interview
              </ButtonLink>
            ) : null}
            {!noAccess ? (
              <Button variant={notReady ? "ghost" : "secondary"} onClick={onRetry}>
                Try again
              </Button>
            ) : null}
            <ButtonLink href="/" variant="ghost">
              Start page
            </ButtonLink>
          </div>
        </div>
      </Panel>
    </main>
  );
}
