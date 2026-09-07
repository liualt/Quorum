"use client";

import { Pause, Play, SignOut } from "@phosphor-icons/react/ssr";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { Captions } from "@/components/interview/Captions";
import { STAGE_LABELS } from "@/components/interview/labels";
import { MicControls } from "@/components/interview/MicControls";
import type { VoiceUiStatus } from "@/components/interview/MicControls";
import { PreJoin } from "@/components/interview/PreJoin";
import { RoleLabel } from "@/components/interview/RoleLabel";
import { ScenarioNotice } from "@/components/interview/ScenarioNotice";
import { SessionTimer } from "@/components/interview/SessionTimer";
import { TextInput } from "@/components/interview/TextInput";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { ErrorText } from "@/components/ui/ErrorText";
import { Panel } from "@/components/ui/Panel";
import {
  ApiError,
  finishInterview,
  getInterview,
  getSnapshot,
  listRuns,
  reportTranscript,
  saveFiles,
  sendTurn,
  setPaused as requestPaused,
  startInterview,
  startRun,
} from "@/lib/api";
import { useSessionEvents } from "@/lib/events";
import type {
  FileMap,
  InterviewView,
  Role,
  RunView,
  SegmentView,
  SessionEvent,
  Stage,
} from "@/lib/types";
import type {
  AgentActivity,
  LiveCaption,
  VoiceControls,
  VoiceHandlers,
  VoiceJoin,
} from "@/lib/voice";

import { BriefPanel } from "./BriefPanel";
import { BRIEF_TAB, EDITOR_PANEL_ID, FileList, tabId } from "./FileList";
import { ResultsPanel } from "./ResultsPanel";
import { RunPanel } from "./RunPanel";

function EditorLoading() {
  return (
    <p role="status" className="text-muted-foreground p-4 text-sm">
      Loading the editor…
    </p>
  );
}

// Both need `window` at import time, so neither is rendered on the server.
const CodeEditor = dynamic(() => import("./CodeEditor"), {
  ssr: false,
  loading: () => <EditorLoading />,
});
const VoicePanel = dynamic(() => import("@/components/interview/VoicePanel"), {
  ssr: false,
});

type Phase = "loading" | "prejoin" | "starting" | "live" | "finishing";

interface Notice {
  segmentId: string;
  text: string;
  unlocked: string[];
}

/** PRD §9: a bounded retry after an execution failure. */
const MAX_RETRIES_PER_RUN = 2;

function errorMessage(cause: unknown, fallback: string): string {
  return cause instanceof ApiError ? cause.detail : fallback;
}

function union(set: Set<string>, ids: string[]): Set<string> {
  const next = new Set(set);
  for (const id of ids) next.add(id);
  return next;
}

/**
 * The candidate's screen, and the owner of everything on it.
 *
 * State arrives from three places — the initial `GET`, the responses to the
 * candidate's own actions, and the event stream — and the stream replays the
 * whole history on every (re)connect. So every collection is keyed by record
 * id and every handler is an upsert: seeing an event twice changes nothing.
 */
export function Workspace({ id }: { id: string }) {
  const router = useRouter();

  const [phase, setPhase] = useState<Phase>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [interview, setInterview] = useState<InterviewView | null>(null);
  const [stage, setStage] = useState<Stage>("briefing");
  const [role, setRole] = useState<Role>("technical");
  const [paused, setPaused] = useState(false);

  /* ----------------------------------------------------------------- code */
  const [files, setFiles] = useState<FileMap>({});
  const [savedFiles, setSavedFiles] = useState<FileMap>({});
  const [snapshotId, setSnapshotId] = useState<string | null>(null);
  const [selectedTab, setSelectedTab] = useState<string>(BRIEF_TAB);
  const [saving, setSaving] = useState(false);
  const [runs, setRuns] = useState<Map<string, RunView>>(() => new Map());
  const [selectedChecks, setSelectedChecks] = useState<Set<string>>(() => new Set());
  const [unlockedChecks, setUnlockedChecks] = useState<Set<string>>(() => new Set());
  const [retries, setRetries] = useState<Map<string, number>>(() => new Map());
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  /* --------------------------------------------------------- conversation */
  const [segments, setSegments] = useState<Map<string, SegmentView>>(() => new Map());
  const [notice, setNotice] = useState<Notice | null>(null);
  const dismissedNotices = useRef(new Set<string>());

  /* ---------------------------------------------------------------- voice */
  const [join, setJoin] = useState<VoiceJoin | null>(null);
  const [voiceUi, setVoiceUi] = useState<VoiceUiStatus>("text");
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);
  const [agentActivity, setAgentActivity] = useState<AgentActivity | null>(null);
  const [liveCaptions, setLiveCaptions] = useState<LiveCaption[]>([]);
  const [reconnecting, setReconnecting] = useState(false);
  const voiceRef = useRef<VoiceControls | null>(null);

  /* ------------------------------------------------------------ lifecycle */
  const [startError, setStartError] = useState<string | null>(null);
  const [finishError, setFinishError] = useState<string | null>(null);
  const endDialog = useRef<HTMLDialogElement>(null);

  /* ------------------------------------------------------------- loading */

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const view = await getInterview(id, controller.signal);
        if (view.status === "finished" || view.status === "finishing") {
          router.replace(`/assessment/${id}`);
          return;
        }
        // A reload must show the code the candidate last saved, not the
        // scenario's starting point.
        let editable = view.scenario.editable_files;
        if (view.latest_snapshot_id) {
          const snapshot = await getSnapshot(id, view.latest_snapshot_id, controller.signal);
          editable = { ...editable, ...snapshot.files };
        }
        const existing = view.me === "candidate" ? await listRuns(id, controller.signal) : [];

        setInterview(view);
        setStage(view.stage);
        setRole(view.active_role);
        setPaused(view.paused);
        setFiles(editable);
        setSavedFiles(editable);
        setSnapshotId(view.latest_snapshot_id);
        setSelectedChecks(
          new Set(view.scenario.checks.filter((check) => check.available).map((c) => c.id)),
        );
        setRuns(new Map(existing.map((run) => [run.id, run])));
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
  }, [id, router]);

  /* --------------------------------------------------------------- events */

  const upsertSegment = useCallback((segment: SegmentView) => {
    setSegments((prev) => new Map(prev).set(segment.id, segment));
  }, []);

  const upsertRun = useCallback((run: RunView) => {
    setRuns((prev) => new Map(prev).set(run.id, run));
  }, []);

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
          setSnapshotId(event.payload.snapshot_id);
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
          setUnlockedChecks((prev) => union(prev, checks_unlocked));
          setSelectedChecks((prev) => union(prev, checks_unlocked));
          if (!dismissedNotices.current.has(segment_id)) {
            setNotice({ segmentId: segment_id, text, unlocked: checks_unlocked });
          }
          break;
        }
        case "interview_finished":
          router.replace(`/assessment/${id}`);
          break;
        default:
          // voice_status is the server's view of a connection this browser
          // observes directly; assessment and dispute events belong to the
          // assessment page.
          break;
      }
    },
    [id, router, upsertRun, upsertSegment],
  );

  // Only once the GET has succeeded: the stream retries forever on a 401.
  useSessionEvents(interview && interview.me === "candidate" ? id : null, onEvent);

  /* -------------------------------------------------------------- derived */

  const editableNames = useMemo(
    () => (interview ? Object.keys(interview.scenario.editable_files) : []),
    [interview],
  );
  const readonlyNames = useMemo(
    () => (interview ? Object.keys(interview.scenario.readonly_files) : []),
    [interview],
  );
  const checks = useMemo(
    () =>
      interview
        ? interview.scenario.checks.map((check) =>
            check.available || unlockedChecks.has(check.id)
              ? { ...check, available: true }
              : check,
          )
        : [],
    [interview, unlockedChecks],
  );
  const dirtyFiles = useMemo(
    () => new Set(editableNames.filter((name) => files[name] !== savedFiles[name])),
    [editableNames, files, savedFiles],
  );
  const dirty = dirtyFiles.size > 0;
  const runList = useMemo(
    () =>
      Array.from(runs.values()).sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [runs],
  );
  const runActive = runList.some((run) => run.status === "queued" || run.status === "running");
  // A segment's seq is its place in the conversation. Event order is not:
  // the candidate's line and the panel's reply are emitted as their own
  // records, and an update to an older segment arrives after newer ones.
  const segmentList = useMemo(
    () => Array.from(segments.values()).sort((a, b) => a.seq - b.seq),
    [segments],
  );
  const runLimit = interview?.run_limit ?? 0;

  /* -------------------------------------------------------------- actions */

  const start = useCallback(
    async (withVoice: boolean) => {
      setPhase("starting");
      setStartError(null);
      try {
        const { voice } = await startInterview(id);
        if (withVoice && voice.enabled) {
          setJoin(voice);
          setVoiceUi("connecting");
          setVoiceNote(null);
        } else {
          setJoin(null);
          setVoiceUi("text");
          setVoiceNote(
            !withVoice || voice.enabled
              ? null
              : voice.reason
                ? `Voice could not start: ${voice.reason}. Continuing in text.`
                : "Voice is not available on this server. Continuing in text.",
          );
        }
        // The server set `started_at`; the timer needs it.
        setInterview(await getInterview(id));
        setPhase("live");
      } catch (cause) {
        setStartError(errorMessage(cause, "Could not start the interview. Try again."));
        setPhase("prejoin");
      }
    },
    [id],
  );

  const updatePaused = useCallback(
    async (next: boolean) => {
      setPaused(next);
      try {
        await requestPaused(id, next);
      } catch (cause) {
        setPaused(!next);
        setActionError(errorMessage(cause, "Could not change the pause state."));
      }
    },
    [id],
  );

  const voiceHandlers = useMemo<VoiceHandlers>(
    () => ({
      onConnection: (status) => {
        setVoiceUi(status);
        if (status === "disconnected") {
          setLiveCaptions([]);
          setAgentActivity(null);
          // PRD §9: a lost voice connection pauses the interview.
          void updatePaused(true);
        }
      },
      onCaptions: setLiveCaptions,
      onAgentTurn: ({ turnId, text, status }) => {
        reportTranscript(id, "agent", status, text, turnId).catch(() => {
          // The segment already exists from the model endpoint; a missed
          // spoken-text update leaves the written text, which is still true.
        });
      },
      onAgentActivity: setAgentActivity,
      onError: setVoiceNote,
    }),
    [id, updatePaused],
  );

  const onVoiceControls = useCallback((controls: VoiceControls | null) => {
    voiceRef.current = controls;
  }, []);

  const dropVoice = useCallback(() => {
    setJoin(null);
    setVoiceUi("text");
    setLiveCaptions([]);
    setAgentActivity(null);
  }, []);

  const reconnect = useCallback(async () => {
    setReconnecting(true);
    setJoin(null);
    setVoiceNote(null);
    try {
      const { voice } = await startInterview(id);
      if (voice.enabled) {
        setJoin(voice);
        setVoiceUi("connecting");
      } else {
        dropVoice();
        setVoiceNote(
          voice.reason
            ? `Voice could not reconnect: ${voice.reason}. Continuing in text.`
            : "Voice could not reconnect. Continuing in text.",
        );
      }
      await updatePaused(false);
    } catch (cause) {
      setVoiceNote(errorMessage(cause, "Could not reconnect. Try again, or continue with text."));
    } finally {
      setReconnecting(false);
    }
  }, [dropVoice, id, updatePaused]);

  const continueWithText = useCallback(async () => {
    dropVoice();
    await updatePaused(false);
  }, [dropVoice, updatePaused]);

  const send = useCallback(
    async (text: string) => {
      if (voiceUi === "connected" && voiceRef.current) {
        await voiceRef.current.sendText(text);
        return;
      }
      let reply;
      try {
        reply = await sendTurn(id, text);
      } catch (cause) {
        throw new Error(errorMessage(cause, "Could not reach the panel. Try again."));
      }
      // The reply segment itself arrives on the stream — the server emits it
      // before this response returns — so only the stage and role are taken
      // from the response, in case their events are still in flight.
      setStage(reply.stage);
      setRole(reply.role);
    },
    [id, voiceUi],
  );

  const save = useCallback(async () => {
    if (!dirty || saving || phase !== "live") return;
    const snapshot = { ...files };
    setSaving(true);
    setActionError(null);
    try {
      const saved = await saveFiles(id, snapshot);
      setSavedFiles(snapshot);
      setSnapshotId(saved.snapshot_id);
      setActionStatus(`Saved snapshot ${saved.snapshot_id}`);
    } catch (cause) {
      setActionError(errorMessage(cause, "Could not save. Try again."));
    } finally {
      setSaving(false);
    }
  }, [dirty, files, id, phase, saving]);

  const launchRun = useCallback(
    async (snapshot: string, checkIds: string[]) => {
      setActionError(null);
      try {
        const run = await startRun(id, snapshot, checkIds, crypto.randomUUID());
        upsertRun(run);
        setActionStatus(`Run ${run.id} queued on snapshot ${snapshot}`);
      } catch (cause) {
        setActionError(errorMessage(cause, "Could not start the run. Try again."));
      }
    },
    [id, upsertRun],
  );

  const run = useCallback(() => {
    if (!snapshotId) return;
    // Scenario order, so the same selection always produces the same request.
    const ids = checks.filter((check) => selectedChecks.has(check.id)).map((c) => c.id);
    void launchRun(snapshotId, ids);
  }, [checks, launchRun, selectedChecks, snapshotId]);

  const retry = useCallback(
    (failed: RunView) => {
      setRetries((prev) => new Map(prev).set(failed.id, (prev.get(failed.id) ?? 0) + 1));
      void launchRun(failed.snapshot_id, failed.check_ids);
    },
    [launchRun],
  );

  const retriesLeft = useCallback(
    (target: RunView) => Math.max(0, MAX_RETRIES_PER_RUN - (retries.get(target.id) ?? 0)),
    [retries],
  );

  const toggleCheck = useCallback((checkId: string) => {
    setSelectedChecks((prev) => {
      const next = new Set(prev);
      if (next.has(checkId)) next.delete(checkId);
      else next.add(checkId);
      return next;
    });
  }, []);

  const finish = useCallback(async () => {
    endDialog.current?.close();
    setPhase("finishing");
    setFinishError(null);
    // Leave the channel first so the microphone is released while the
    // assessment builds; the server stops the agent on its side.
    dropVoice();
    try {
      await finishInterview(id);
      router.replace(`/assessment/${id}`);
    } catch (cause) {
      setFinishError(errorMessage(cause, "Could not end the interview. Try again."));
      setPhase("live");
    }
  }, [dropVoice, id, router]);

  /* ------------------------------------------------------------- effects */

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void save();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [save]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  /* -------------------------------------------------------------- render */

  if (loadError) {
    return (
      <Blocked title="Interview unavailable">
        <ErrorText>{loadError}</ErrorText>
      </Blocked>
    );
  }

  if (!interview || phase === "loading") {
    return (
      <main className="mx-auto w-full max-w-xl px-4 py-12">
        <h1 className="sr-only">Interview workspace</h1>
        <p role="status" className="text-muted-foreground text-sm">
          Loading the interview…
        </p>
      </main>
    );
  }

  if (interview.me !== "candidate") {
    return (
      <Blocked
        title="This is the candidate's workspace"
        href={`/assessment/${id}`}
        linkText="Open the assessment"
      >
        <p className="text-muted-foreground text-sm">
          Reviewers see the interview through its assessment, once the candidate has ended it.
        </p>
      </Blocked>
    );
  }

  if (phase === "prejoin" || phase === "starting") {
    return (
      <PreJoin
        interview={interview}
        busy={phase === "starting"}
        error={startError}
        onJoin={(withVoice) => void start(withVoice)}
      />
    );
  }

  const finishing = phase === "finishing";
  const editableSelected = editableNames.includes(selectedTab);
  const selectedContent = editableSelected
    ? (files[selectedTab] ?? "")
    : (interview.scenario.readonly_files[selectedTab] ?? "");
  const inputBlocked = finishing
    ? "The interview is ending."
    : paused
      ? "Resume the interview to continue."
      : null;
  const retryBlocked = finishing
    ? "The interview is ending."
    : runActive
      ? "A run is in progress."
      : runs.size >= runLimit
        ? `All ${runLimit} runs have been used.`
        : null;

  return (
    <div className="flex min-h-dvh flex-col">
      <h1 className="sr-only">Interview workspace</h1>

      <header className="border-border bg-card sticky top-0 z-10 flex flex-wrap items-center gap-x-4 gap-y-2 border-b px-4 py-2">
        <p className="text-muted-foreground font-mono text-xs tracking-widest uppercase">
          Quorum
        </p>
        <Chip>{STAGE_LABELS[stage]}</Chip>
        <span role="status">
          <RoleLabel role={role} />
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <SessionTimer
            startedAt={interview.started_at}
            paused={paused}
            capMinutes={interview.session_cap_minutes}
          />
          <Button
            variant="secondary"
            aria-pressed={paused}
            disabled={finishing}
            onClick={() => void updatePaused(!paused)}
          >
            {paused ? <Play size={18} aria-hidden /> : <Pause size={18} aria-hidden />}
            {paused ? "Resume" : "Pause"}
          </Button>
          <Button
            variant="destructive"
            disabled={finishing}
            onClick={() => endDialog.current?.showModal()}
          >
            <SignOut size={18} aria-hidden />
            End interview
          </Button>
        </div>
      </header>

      {notice ? (
        <ScenarioNotice
          text={notice.text}
          unlockedChecks={notice.unlocked.map(
            (checkId) => checks.find((check) => check.id === checkId)?.name ?? checkId,
          )}
          onDismiss={() => {
            dismissedNotices.current.add(notice.segmentId);
            setNotice(null);
          }}
        />
      ) : null}

      {paused ? (
        <p role="status" className="bg-muted border-border border-b px-4 py-2 text-sm">
          Paused. The panel is waiting, your microphone is muted and the clock is stopped.
        </p>
      ) : null}

      {finishing ? (
        <p role="status" className="bg-muted border-border border-b px-4 py-2 text-sm">
          Ending the interview and building your assessment. This can take up to half a
          minute…
        </p>
      ) : null}
      {finishError ? <ErrorText className="px-4 py-2">{finishError}</ErrorText> : null}

      <main className="grid flex-1 gap-3 p-3 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        {/* Flex columns, not grids: an implicit grid track grows to its
            children's min-content and would push the panels past a narrow
            viewport. */}
        <div className="flex min-w-0 flex-col gap-3">
          <Panel padded={false} className="min-w-0 overflow-hidden">
            <div className="flex flex-col sm:flex-row">
              <FileList
                editable={editableNames}
                readonly={readonlyNames}
                selected={selectedTab}
                dirty={dirtyFiles}
                onSelect={setSelectedTab}
              />
              <div
                id={EDITOR_PANEL_ID}
                role="tabpanel"
                aria-labelledby={tabId(selectedTab)}
                className="h-[28rem] min-w-0 flex-1 lg:h-[32rem]"
              >
                {selectedTab === BRIEF_TAB ? (
                  <BriefPanel markdown={interview.scenario.brief} />
                ) : (
                  <CodeEditor
                    path={selectedTab}
                    value={selectedContent}
                    language={selectedTab.endsWith(".json") ? "json" : "python"}
                    readOnly={!editableSelected || finishing}
                    ariaLabel={editableSelected ? selectedTab : `${selectedTab} (read only)`}
                    onChange={(value) => {
                      if (!editableSelected) return;
                      setFiles((prev) => ({ ...prev, [selectedTab]: value }));
                    }}
                  />
                )}
              </div>
            </div>
          </Panel>

          <RunPanel
            checks={checks}
            selected={selectedChecks}
            onToggleCheck={toggleCheck}
            dirty={dirty}
            saving={saving}
            onSave={() => void save()}
            snapshotId={snapshotId}
            runActive={runActive}
            runsUsed={runs.size}
            runLimit={runLimit}
            onRun={run}
            status={actionStatus}
            error={actionError}
            disabled={finishing}
          />
        </div>

        <div className="flex min-w-0 flex-col gap-3">
          <Captions
            segments={segmentList}
            live={liveCaptions}
            candidateName={interview.display_name}
          />
          <Panel>
            <div className="grid gap-4">
              <MicControls
                voice={voiceUi}
                note={voiceNote}
                agentActivity={agentActivity}
                muted={muted}
                paused={paused}
                onToggleMute={() => setMuted((value) => !value)}
                onReconnect={() => void reconnect()}
                onContinueWithText={() => void continueWithText()}
                busy={reconnecting}
              />
              <TextInput
                mode={voiceUi === "connected" ? "voice" : "text"}
                blocked={inputBlocked}
                onSend={send}
              />
            </div>
          </Panel>
        </div>

        <div className="min-w-0 lg:col-span-2">
          <ResultsPanel
            runs={runList}
            checks={checks}
            onRetry={retry}
            retriesLeft={retriesLeft}
            retryBlocked={retryBlocked}
          />
        </div>
      </main>

      {join ? (
        <VoicePanel
          key={join.token}
          join={join}
          muted={muted || paused}
          handlers={voiceHandlers}
          onControls={onVoiceControls}
        />
      ) : null}

      <dialog
        ref={endDialog}
        aria-labelledby="end-interview-title"
        className="bg-card text-foreground border-border m-auto w-[min(90vw,28rem)] rounded-xl border p-6 shadow-xl backdrop:bg-black/60"
      >
        <h2 id="end-interview-title" className="text-lg font-semibold">
          End the interview?
        </h2>
        <p className="text-muted-foreground mt-2 text-sm">
          The panel stops, your saved code and the transcript become the record, and your
          assessment is built. This cannot be undone.
        </p>
        {dirty ? (
          <p className="mt-2 text-sm">
            You have unsaved changes. They will not be part of the record unless you save
            first.
          </p>
        ) : null}
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <Button variant="secondary" onClick={() => endDialog.current?.close()}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={() => void finish()}>
            End interview
          </Button>
        </div>
      </dialog>
    </div>
  );
}

interface BlockedProps {
  title: string;
  href?: string;
  linkText?: string;
  children: ReactNode;
}

function Blocked({ title, href = "/", linkText = "Back to the start", children }: BlockedProps) {
  return (
    <main className="mx-auto w-full max-w-xl px-4 py-12">
      <h1 className="sr-only">{title}</h1>
      <Panel title={title}>
        <div className="grid gap-4">
          {children}
          <div>
            <ButtonLink href={href} variant="secondary">
              {linkText}
            </ButtonLink>
          </div>
        </div>
      </Panel>
    </main>
  );
}
