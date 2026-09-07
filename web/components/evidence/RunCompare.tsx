import { CheckCircle, Minus, Question, Warning, XCircle } from "@phosphor-icons/react/ssr";
import { useId } from "react";

import { Chip } from "@/components/ui/Chip";
import type { CheckResultDict, RunView } from "@/lib/types";

import { RUN_STATUS_LABELS, formatTime, humanizeId, runOutcome } from "./labels";

interface RunCompareProps {
  /** The run the finding cites. */
  run: RunView;
  /** The candidate's most recent completed run before it, if there was one. */
  before: RunView | null;
  /** Reruns of `run`, oldest first. */
  replays: RunView[];
  /** Check id → display name, from the scenario. */
  checkNames: Record<string, string>;
}

/**
 * A run's results next to the run before it, its steps in full, and its reruns.
 *
 * Every status is an icon and a word; a null step result is "not observed",
 * which is a different thing from a failure and is shown as one.
 */
export function RunCompare({ run, before, replays, checkNames }: RunCompareProps) {
  const ids = useId();
  const name = (checkId: string) => checkNames[checkId] ?? humanizeId(checkId);
  const checkIds = Array.from(new Set([...run.check_ids, ...(before?.check_ids ?? [])]));

  return (
    <div className="grid gap-6">
      <section className="grid gap-2" aria-labelledby={`${ids}-compare`}>
        <h3 id={`${ids}-compare`} className="text-sm font-semibold tracking-wide uppercase">
          Before and after
        </h3>
        <p className="text-muted-foreground text-xs">
          {before ? (
            <>
              Before: run <span className="font-mono">{before.id}</span>,{" "}
              {formatTime(before.finished_at)}. After: run{" "}
              <span className="font-mono">{run.id}</span>, {formatTime(run.finished_at)}.
            </>
          ) : (
            <>
              No earlier completed run to compare with. This run:{" "}
              <span className="font-mono">{run.id}</span>, {formatTime(run.finished_at)}.
            </>
          )}
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted-foreground text-left text-xs uppercase">
                <th scope="col" className="py-1 pr-3 font-semibold">
                  Check
                </th>
                <th scope="col" className="py-1 pr-3 font-semibold">
                  Before
                </th>
                <th scope="col" className="py-1 font-semibold">
                  After
                </th>
              </tr>
            </thead>
            <tbody>
              {checkIds.map((checkId) => (
                <tr key={checkId} className="border-border border-t">
                  <td className="py-2 pr-3">{name(checkId)}</td>
                  <td className="py-2 pr-3">
                    <Outcome run={before} checkId={checkId} />
                  </td>
                  <td className="py-2">
                    <Outcome run={run} checkId={checkId} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid gap-3" aria-labelledby={`${ids}-steps`}>
        <h3 id={`${ids}-steps`} className="text-sm font-semibold tracking-wide uppercase">
          Steps in this run
        </h3>
        <p className="text-muted-foreground text-xs">
          {RUN_STATUS_LABELS[run.status]} · {runOutcome(run)}
        </p>
        {run.results === null ? (
          <p className="text-muted-foreground text-sm">No results were recorded for this run.</p>
        ) : (
          run.results.map((result) => (
            <CheckSteps key={result.check_id} result={result} name={name(result.check_id)} run={run} />
          ))
        )}
        {run.stdout_excerpt || run.stderr_excerpt ? (
          <details className="text-xs">
            <summary className="flex min-h-11 cursor-pointer items-center font-semibold">
              Output excerpt
            </summary>
            {run.stdout_excerpt ? <Excerpt label="stdout" text={run.stdout_excerpt} /> : null}
            {run.stderr_excerpt ? <Excerpt label="stderr" text={run.stderr_excerpt} /> : null}
          </details>
        ) : null}
        <dl className="text-muted-foreground grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono text-xs">
          <dt>Snapshot</dt>
          <dd className="break-all">{run.snapshot_id}</dd>
          <dt>Fixture</dt>
          <dd>{run.fixture_version}</dd>
          <dt>Checks</dt>
          <dd>{run.check_version}</dd>
          <dt>Executor</dt>
          <dd>{run.executor}</dd>
          <dt>Input hash</dt>
          <dd className="break-all">{run.input_hash}</dd>
        </dl>
      </section>

      <section className="grid gap-2" aria-labelledby={`${ids}-reruns`}>
        <h3 id={`${ids}-reruns`} className="text-sm font-semibold tracking-wide uppercase">
          Reruns
        </h3>
        {replays.length === 0 ? (
          <p className="text-muted-foreground text-sm">No reruns yet.</p>
        ) : (
          <ul className="grid gap-2">
            {replays.map((replay) => (
              <li
                key={replay.id}
                className="border-border flex flex-wrap items-center gap-2 rounded-lg border p-3 text-xs"
              >
                <span className="font-mono">{replay.id}</span>
                <Chip>{RUN_STATUS_LABELS[replay.status]}</Chip>
                <Differs replay={replay} />
                <span className="text-muted-foreground">
                  {runOutcome(replay)} · {formatTime(replay.finished_at ?? replay.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Outcome({ run, checkId }: { run: RunView | null; checkId: string }) {
  if (!run) {
    return <Chip icon={<Minus size={14} aria-hidden />}>No earlier run</Chip>;
  }
  if (run.status !== "completed") {
    return (
      <Chip tone="caution" icon={<Warning size={14} aria-hidden />}>
        {RUN_STATUS_LABELS[run.status]}
      </Chip>
    );
  }
  const result = run.results?.find((item) => item.check_id === checkId);
  if (!result) {
    return <Chip icon={<Minus size={14} aria-hidden />}>Not in this run</Chip>;
  }
  return result.passed ? (
    <Chip tone="positive" icon={<CheckCircle size={14} aria-hidden />}>
      Passed
    </Chip>
  ) : (
    <Chip tone="negative" icon={<XCircle size={14} aria-hidden />}>
      Failed
    </Chip>
  );
}

function CheckSteps({
  result,
  name,
  run,
}: {
  result: CheckResultDict;
  name: string;
  run: RunView;
}) {
  return (
    <div className="border-border grid gap-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold">{name}</span>
        <Outcome run={run} checkId={result.check_id} />
      </div>
      <ol className="grid gap-1.5 text-xs">
        {result.steps.map((step) => (
          <li key={step.index} className="grid gap-0.5">
            <span className="flex items-center gap-1.5 font-mono">
              <StepStatus ok={step.ok} />
              <span>
                #{step.index} {step.op}
              </span>
            </span>
            {step.expected !== null || step.actual !== null ? (
              <span className="text-muted-foreground pl-5">
                expected {idList(step.expected)} · actual {idList(step.actual)}
              </span>
            ) : null}
            {step.error ? <span className="text-destructive-text pl-5">{step.error}</span> : null}
          </li>
        ))}
      </ol>
      <Budget result={result} />
      {result.error ? <p className="text-destructive-text text-xs">{result.error}</p> : null}
    </div>
  );
}

function StepStatus({ ok }: { ok: boolean | null }) {
  if (ok === null) {
    return (
      <span className="text-muted-foreground inline-flex items-center gap-1">
        <Question size={14} aria-hidden />
        not observed
      </span>
    );
  }
  return ok ? (
    <span className="text-accent inline-flex items-center gap-1">
      <CheckCircle size={14} aria-hidden />
      ok
    </span>
  ) : (
    <span className="text-destructive-text inline-flex items-center gap-1">
      <XCircle size={14} aria-hidden />
      failed
    </span>
  );
}

function idList(ids: string[] | null): string {
  if (ids === null) return "—";
  return ids.length === 0 ? "none" : ids.join(", ");
}

function Budget({ result }: { result: CheckResultDict }) {
  if (result.search_calls === null && result.max_search_calls === null) return null;
  const calls = result.search_calls === null ? "not measured" : String(result.search_calls);
  const cap = result.max_search_calls === null ? "" : ` of at most ${result.max_search_calls}`;
  const verdict =
    result.efficiency_ok === null ? "" : result.efficiency_ok ? " · within budget" : " · over budget";
  return (
    <p className="text-muted-foreground text-xs">
      Search calls: {calls}
      {cap}
      {verdict}
    </p>
  );
}

function Differs({ replay }: { replay: RunView }) {
  if (replay.differs_from_original === true) {
    return (
      <Chip tone="caution" icon={<Warning size={14} aria-hidden />}>
        Differs from original
      </Chip>
    );
  }
  if (replay.differs_from_original === false) {
    return (
      <Chip tone="positive" icon={<CheckCircle size={14} aria-hidden />}>
        Matches original
      </Chip>
    );
  }
  return <Chip icon={<Question size={14} aria-hidden />}>Not compared</Chip>;
}

function Excerpt({ label, text }: { label: string; text: string }) {
  return (
    <div className="mt-2 grid gap-1">
      <span className="text-muted-foreground font-mono">{label}</span>
      <pre className="bg-background overflow-x-auto rounded-md p-2 font-mono whitespace-pre-wrap">
        {text}
      </pre>
    </div>
  );
}
