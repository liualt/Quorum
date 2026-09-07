"use client";

import { Check, Circle, FloppyDisk, Play } from "@phosphor-icons/react/ssr";
import { useId } from "react";

import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { ErrorText } from "@/components/ui/ErrorText";
import { Panel } from "@/components/ui/Panel";
import type { CheckView } from "@/lib/types";

interface RunPanelProps {
  checks: CheckView[];
  selected: ReadonlySet<string>;
  onToggleCheck: (id: string) => void;
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  snapshotId: string | null;
  /** A run is queued or running. */
  runActive: boolean;
  runsUsed: number;
  runLimit: number;
  onRun: () => void;
  /** The last thing that happened ("Saved snapshot …"), announced politely. */
  status: string | null;
  error: string | null;
  /** The interview is ending; nothing here may start. */
  disabled: boolean;
}

/** The first thing stopping a run, phrased for the candidate. */
function runBlockedBy(props: RunPanelProps): string | null {
  if (props.disabled) return "The interview is ending.";
  if (props.dirty) return "Save first; a run always uses a saved snapshot.";
  if (!props.snapshotId) return "Save the starter code to run it.";
  if (props.runActive) return "A run is in progress.";
  if (props.runsUsed >= props.runLimit)
    return `All ${props.runLimit} runs have been used.`;
  if (props.selected.size === 0) return "Select at least one check.";
  return null;
}

export function shortSnapshot(id: string): string {
  return id.length > 12 ? `${id.slice(0, 12)}…` : id;
}

export function RunPanel(props: RunPanelProps) {
  const {
    checks,
    selected,
    onToggleCheck,
    dirty,
    saving,
    onSave,
    snapshotId,
    runsUsed,
    runLimit,
    onRun,
    status,
    error,
    disabled,
  } = props;
  const runHintId = useId();
  const blocked = runBlockedBy(props);
  // The starter code counts as unsaved: a run needs a snapshot, and there is none yet.
  const needsSave = dirty || snapshotId === null;

  return (
    <Panel
      title="Save and run"
      actions={
        dirty ? (
          <Chip
            tone="caution"
            icon={<Circle size={10} weight="fill" aria-hidden />}
          >
            Unsaved changes
          </Chip>
        ) : snapshotId ? (
          <Chip tone="neutral" icon={<Check size={12} aria-hidden />}>
            All changes saved
          </Chip>
        ) : (
          <Chip
            tone="caution"
            icon={<Circle size={10} weight="fill" aria-hidden />}
          >
            Nothing saved yet
          </Chip>
        )
      }
    >
      <div className="grid gap-4">
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-sm font-medium">Checks to run</legend>
          {checks.map((check) => {
            const available = check.available;
            return (
              <label
                key={check.id}
                className={
                  available
                    ? "flex cursor-pointer items-start gap-3 text-sm"
                    : "flex cursor-not-allowed items-start gap-3 text-sm opacity-60"
                }
              >
                <input
                  type="checkbox"
                  checked={available && selected.has(check.id)}
                  disabled={!available || disabled}
                  onChange={() => onToggleCheck(check.id)}
                  className="accent-accent mt-0.5 size-5 shrink-0 cursor-pointer disabled:cursor-not-allowed"
                />
                <span className="min-w-0">
                  <span className="font-medium">{check.name}</span>
                  {!available ? (
                    <Chip className="ml-2 align-middle">
                      not yet introduced
                    </Chip>
                  ) : null}
                  <span className="text-muted-foreground block">
                    {check.description}
                  </span>
                </span>
              </label>
            );
          })}
        </fieldset>

        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="secondary"
            onClick={onSave}
            disabled={!needsSave || saving || disabled}
          >
            <FloppyDisk size={18} aria-hidden />
            {saving ? "Saving…" : "Save"}
          </Button>
          <Button
            onClick={onRun}
            disabled={blocked !== null}
            title={blocked ?? undefined}
            aria-describedby={runHintId}
          >
            <Play size={18} aria-hidden />
            {snapshotId ? (
              <>
                Run saved snapshot{" "}
                <code className="font-mono font-normal">
                  {shortSnapshot(snapshotId)}
                </code>
              </>
            ) : (
              "Run checks"
            )}
          </Button>
          <p id={runHintId} className="text-muted-foreground text-sm">
            {blocked ?? `${runsUsed} of ${runLimit} runs used.`}
          </p>
        </div>

        <p
          role="status"
          className="text-muted-foreground min-h-5 font-mono text-xs"
        >
          {status ?? (snapshotId ? `Latest snapshot ${snapshotId}` : "")}
        </p>
        {error ? <ErrorText>{error}</ErrorText> : null}
      </div>
    </Panel>
  );
}
