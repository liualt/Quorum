"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, getInterview, getSnapshot, listRuns } from "@/lib/api";
import { useSessionEvents } from "@/lib/events";
import type {
  InterviewView,
  Role,
  RunView,
  SegmentView,
  SessionEvent,
  Stage,
} from "@/lib/types";

import { errorMessage } from "./errorMessage";
import type { CodeSeed } from "./useCodeAndRuns";

export type Phase = "loading" | "prejoin" | "starting" | "live" | "finishing";

export interface Notice {
  segmentId: string;
  text: string;
  unlocked: string[];
}

/** The parts of `useCodeAndRuns` the session feeds. */
export interface CodeSink {
  seed: (data: CodeSeed) => void;
  upsertRun: (run: RunView) => void;
  unlockChecks: (ids: string[]) => void;
  noteSnapshotSaved: (snapshotId: string, contentHash: string) => void;
}

interface Options {
  id: string;
  code: CodeSink;
  /** The interview is over (or was over when the page loaded): leave for the assessment. */
  onFinished: () => void;
}

/**
 * The session itself: the interview record, stage, role, pause, transcript
 * and scenario notices, loaded once by `GET` and then kept current by the
 * event stream.
 *
 * The stream replays the whole history on every (re)connect, so every
 * collection is keyed by record id and every handler is an upsert: seeing an
 * event twice changes nothing. Code and run events are handed to the code
 * hook through `code`.
 */
export function useInterviewSession({ id, code, onFinished }: Options) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [interview, setInterview] = useState<InterviewView | null>(null);
  const [stage, setStage] = useState<Stage>("briefing");
  const [role, setRole] = useState<Role>("technical");
  const [paused, setPaused] = useState(false);

  const [segments, setSegments] = useState<Map<string, SegmentView>>(() => new Map());
  const [notice, setNotice] = useState<Notice | null>(null);
  const dismissedNotices = useRef(new Set<string>());

  const onFinishedRef = useRef(onFinished);
  useEffect(() => {
    onFinishedRef.current = onFinished;
  }, [onFinished]);

  /* ------------------------------------------------------------- loading */

  const { seed } = code;
  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const view = await getInterview(id, controller.signal);
        if (view.status === "finished" || view.status === "finishing") {
          onFinishedRef.current();
          return;
        }
        // A reload must show the code the candidate last saved, not the
        // scenario's starting point.
        let editable = view.scenario.editable_files;
        let contentHash: string | null = null;
        if (view.latest_snapshot_id) {
          const snapshot = await getSnapshot(id, view.latest_snapshot_id, controller.signal);
          editable = { ...editable, ...snapshot.files };
          contentHash = snapshot.content_hash;
        }
        const existing = view.me === "candidate" ? await listRuns(id, controller.signal) : [];

        setInterview(view);
        setStage(view.stage);
        setRole(view.active_role);
        setPaused(view.paused);
        seed({
          files: editable,
          snapshotId: view.latest_snapshot_id,
          contentHash,
          runs: existing,
          availableCheckIds: view.scenario.checks
            .filter((check) => check.available)
            .map((check) => check.id),
        });
        setPhase("prejoin");
      } catch (cause) {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setLoadError(
          cause instanceof ApiError && (cause.status === 401 || cause.status === 403)
            ? "This interview is not open to this browser. Use the link you were given, in the browser where you created the interview."
            : errorMessage(cause, "Could not load the interview."),
        );
      }
    })();
    return () => controller.abort();
  }, [id, seed]);

  /* --------------------------------------------------------------- events */

  const upsertSegment = useCallback((segment: SegmentView) => {
    setSegments((prev) => new Map(prev).set(segment.id, segment));
  }, []);

  const { upsertRun, unlockChecks, noteSnapshotSaved } = code;
  const onEvent = useCallback(
    (event: SessionEvent) => {
      switch (event.type) {
        case "stage_changed":
          setStage(event.payload.stage);
          break;
        case "role_changed":
          setRole(event.payload.role);
          break;
        case "transcript_segment":
        case "segment_updated":
          upsertSegment(event.payload.segment);
          break;
        case "snapshot_saved":
          noteSnapshotSaved(event.payload.snapshot_id, event.payload.content_hash);
          break;
        case "run_started":
        case "run_completed":
          upsertRun(event.payload.run);
          break;
        case "pause_changed":
          setPaused(event.payload.paused);
          break;
        case "scenario_notice": {
          const { segment_id, text, checks_unlocked } = event.payload;
          unlockChecks(checks_unlocked);
          if (!dismissedNotices.current.has(segment_id)) {
            setNotice({ segmentId: segment_id, text, unlocked: checks_unlocked });
          }
          break;
        }
        case "interview_finished":
          onFinishedRef.current();
          break;
        default:
          // voice_status is the server's view of a connection this browser
          // observes directly; assessment and dispute events belong to the
          // assessment page.
          break;
      }
    },
    [noteSnapshotSaved, unlockChecks, upsertRun, upsertSegment],
  );

  // Only once the GET has succeeded: the stream retries forever on a 401.
  useSessionEvents(interview && interview.me === "candidate" ? id : null, onEvent);

  /* -------------------------------------------------------------- derived */

  // A segment's seq is its place in the conversation. Event order is not:
  // the candidate's line and the panel's reply are emitted as their own
  // records, and an update to an older segment arrives after newer ones.
  const segmentList = useMemo(
    () => Array.from(segments.values()).sort((a, b) => a.seq - b.seq),
    [segments],
  );

  const dismissNotice = useCallback((current: Notice) => {
    dismissedNotices.current.add(current.segmentId);
    setNotice(null);
  }, []);

  return {
    phase,
    setPhase,
    loadError,
    interview,
    setInterview,
    stage,
    setStage,
    role,
    setRole,
    paused,
    setPaused,
    segmentList,
    notice,
    dismissNotice,
  };
}
