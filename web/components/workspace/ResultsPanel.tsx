"use client";

import {
  ArrowsClockwise,
  CheckCircle,
  CircleNotch,
  Question,
  Warning,
  XCircle,
} from "@phosphor-icons/react/ssr";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import type { ChipTone } from "@/components/ui/Chip";
import { Panel } from "@/components/ui/Panel";
import type {
  CheckResultDict,
  CheckStepResult,
  CheckView,
  Executor,
  RunStatus,
  RunView,
} from "@/lib/types";

import { shortSnapshot } from "./RunPanel";

interface ResultsPanelProps {
  /** Newest first. */
  runs: RunView[];
  checks: CheckView[];
  onRetry: (run: RunView) => void;
  retriesLeft: (run: RunView) => number;
  /** Why no new run can start right now, or null. */
  retryBlocked: string | null;
}

const RUN_STATUS: Record<RunStatus, { label: string; tone: ChipTone; icon: ReactNode }> = {
  queued: {
    label: "Queued",
    tone: "neutral",
    icon: <CircleNotch size={14} aria-hidden className="animate-spin" />,
  },
  running: {
    label: "Running",
    tone: "neutral",
    icon: <CircleNotch size={14} aria-hidden className="animate-spin" />,
  },
  completed: { label: "Completed", tone: "neutral", icon: <CheckCircle size={14} aria-hidden /> },
  timeout: { label: "Timed out", tone: "caution", icon: <Warning size={14} aria-hidden /> },
  failed: { label: "Failed to run", tone: "negative", icon: <XCircle size={14} aria-hidden /> },
  unavailable: {
    label: "Unavailable",
    tone: "caution",
    icon: <Warning size={14} aria-hidden />,
  },
};

/** PRD §9: a timeout or an unavailable executor is not a result. */
const RUN_MESSAGES: Partial<Record<RunStatus, string>> = {
  queued: "Waiting for the executor.",
  running: "Running your saved snapshot against the selected checks.",
  timeout:
    "The run exceeded its time limit before the checks finished. A timeout is an execution failure, not a result.",
  failed: "The checks could not be executed. No result was recorded.",
  unavailable: "Execution was unavailable. No result was recorded.",
};

const EXECUTOR_LABELS: Record<Executor, string> = {
  e2b: "Ran in an isolated sandbox",
  local: "Ran locally",
  none: "Did not run",
};

const RETRYABLE: ReadonlySet<RunStatus> = new Set(["timeout", "failed", "unavailable"]);

function timeOf(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function ResultsPanel({ runs, checks, onRetry, retriesLeft, retryBlocked }: ResultsPanelProps) {
  const nameOf = (id: string) => checks.find((check) => check.id === id)?.name ?? id;

  return (
    <Panel title="Results" padded={false}>
      {runs.length === 0 ? (
        <p className="text-muted-foreground px-4 py-6 text-sm">
          No runs yet. Save your code, choose the checks, and run them to see real results here.
        </p>
      ) : (
        <ol className="divide-border divide-y">
          {runs.map((run, index) => (
            <li key={run.id} className="px-4 py-4">
              <RunEntry
                run={run}
                nameOf={nameOf}
                open={index === 0}
                onRetry={onRetry}
                retriesLeft={retriesLeft(run)}
                retryBlocked={retryBlocked}
              />
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

interface RunEntryProps {
  run: RunView;
  nameOf: (id: string) => string;
  open: boolean;
  onRetry: (run: RunView) => void;
  retriesLeft: number;
  retryBlocked: string | null;
}

function RunEntry({ run, nameOf, open, onRetry, retriesLeft, retryBlocked }: RunEntryProps) {
  const status = RUN_STATUS[run.status];
  const results = run.results ?? [];
  const passed = results.filter((result) => result.passed).length;
  const retryable = RETRYABLE.has(run.status);
  const retryHint =
    retryBlocked ?? (retriesLeft === 0 ? "No retries left for this run." : null);

  return (
    <details open={open} className="group">
      <summary className="flex min-h-11 cursor-pointer list-none flex-wrap items-center gap-2 text-sm [&::-webkit-details-marker]:hidden">
        <Chip tone={status.tone} icon={status.icon}>
          {status.label}
        </Chip>
        {run.status === "completed" ? (
          <Chip
            tone={passed === results.length ? "positive" : "negative"}
            icon={
              passed === results.length ? (
                <CheckCircle size={14} aria-hidden />
              ) : (
                <XCircle size={14} aria-hidden />
              )
            }
          >
            {passed} of {results.length} checks passed
          </Chip>
        ) : null}
        <span className="text-muted-foreground font-mono text-xs">
          <time dateTime={run.created_at}>{timeOf(run.created_at)}</time> · snapshot{" "}
          {shortSnapshot(run.snapshot_id)}
          {run.replay_of ? " · replay" : ""}
        </span>
        <span className="text-muted-foreground ml-auto text-xs group-open:hidden">
          Show details
        </span>
        <span className="text-muted-foreground ml-auto hidden text-xs group-open:inline">
          Hide details
        </span>
      </summary>

      <div className="mt-3 grid gap-3">
        <p className="text-muted-foreground text-xs">
          {EXECUTOR_LABELS[run.executor]} · fixtures {run.fixture_version} · checks{" "}
          {run.check_version}
        </p>

        {RUN_MESSAGES[run.status] ? (
          <p className="text-sm">{RUN_MESSAGES[run.status]}</p>
        ) : null}

        {run.status === "failed" && run.stderr_excerpt ? (
          <pre className="bg-background border-border max-h-40 overflow-auto rounded-lg border p-3 font-mono text-xs whitespace-pre-wrap">
            {run.stderr_excerpt}
          </pre>
        ) : null}

        {run.status === "completed" ? (
          <ul className="grid gap-3">
            {results.map((result) => (
              <li key={result.check_id}>
                <CheckEntry result={result} name={nameOf(result.check_id)} />
              </li>
            ))}
          </ul>
        ) : null}

        {retryable ? (
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              onClick={() => onRetry(run)}
              disabled={retryHint !== null}
              title={retryHint ?? undefined}
            >
              <ArrowsClockwise size={18} aria-hidden />
              Retry
              {retriesLeft > 0 ? ` (${retriesLeft} left)` : ""}
            </Button>
            <p className="text-muted-foreground text-sm">
              {retryHint ?? "Starts a new run of the same snapshot and checks."}
            </p>
          </div>
        ) : null}
      </div>
    </details>
  );
}

function CheckEntry({ result, name }: { result: CheckResultDict; name: string }) {
  const searchLine =
    result.search_calls === null
      ? null
      : `Search calls: ${result.search_calls}${
          result.max_search_calls === null ? "" : ` of ${result.max_search_calls} allowed`
        }`;
  const efficiency =
    result.efficiency_ok === null ? null : result.efficiency_ok ? "within budget" : "over budget";

  return (
    <div className="border-border rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {result.passed ? (
          <CheckCircle size={20} aria-hidden className="text-accent shrink-0" />
        ) : (
          <XCircle size={20} aria-hidden className="text-destructive shrink-0" />
        )}
        <span className="font-medium">{name}</span>
        <span className={result.passed ? "text-accent" : "text-destructive-text"}>
          {result.passed ? "Passed" : "Failed"}
        </span>
        {searchLine ? (
          <span className="text-muted-foreground ml-auto font-mono text-xs">
            {searchLine}
            {efficiency ? (
              <span className={result.efficiency_ok ? "" : "text-destructive-text"}>
                {" "}
                · {efficiency}
              </span>
            ) : null}
          </span>
        ) : null}
      </div>

      {result.error ? <p className="text-destructive-text mt-2 text-sm">{result.error}</p> : null}

      {result.steps.length > 0 ? (
        <details className="mt-2">
          <summary className="text-muted-foreground min-h-11 cursor-pointer text-sm sm:min-h-0">
            {result.steps.length} step{result.steps.length === 1 ? "" : "s"} — expected vs actual
          </summary>
          <ol className="mt-2 grid gap-2">
            {result.steps.map((step) => (
              <li key={step.index}>
                <StepEntry step={step} />
              </li>
            ))}
          </ol>
        </details>
      ) : null}
    </div>
  );
}

function StepEntry({ step }: { step: CheckStepResult }) {
  const outcome =
    step.ok === null ? (
      <>
        <Question size={16} aria-hidden className="text-muted-foreground" /> Not observed
      </>
    ) : step.ok ? (
      <>
        <CheckCircle size={16} aria-hidden className="text-accent" /> OK
      </>
    ) : (
      <>
        <XCircle size={16} aria-hidden className="text-destructive" /> Mismatch
      </>
    );

  return (
    <div className="bg-background rounded-md p-2 font-mono text-xs">
      <p className="flex items-center gap-1.5">
        Step {step.index + 1} · {step.op}
        <span className="ml-auto flex items-center gap-1">{outcome}</span>
      </p>
      {step.expected !== null ? (
        <dl className="mt-1 grid gap-0.5 sm:grid-cols-[6rem_1fr]">
          <dt className="text-muted-foreground">expected</dt>
          <dd className="break-all">{ids(step.expected)}</dd>
          <dt className="text-muted-foreground">actual</dt>
          <dd className="break-all">{step.actual === null ? "not observed" : ids(step.actual)}</dd>
        </dl>
      ) : null}
      {step.error ? <p className="text-destructive-text mt-1">{step.error}</p> : null}
    </div>
  );
}

function ids(list: string[]): string {
  return list.length === 0 ? "(none)" : list.join(", ");
}
