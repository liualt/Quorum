"use client";

import { CheckCircle, Flag } from "@phosphor-icons/react/ssr";
import { useId, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { ErrorText } from "@/components/ui/ErrorText";
import { ApiError } from "@/lib/api";
import type { DisputeView, FindingView, Participant } from "@/lib/types";

import { DIMENSION_TITLES, formatTime } from "./labels";

interface DisputeListProps {
  disputes: DisputeView[];
  /** Every finding of the assessment, to name the affected ones. */
  findings: FindingView[];
  me: Participant;
  onResolve: (disputeId: string, resolution: string) => Promise<void>;
  emptyText: string;
}

/**
 * Corrections as filed: the recorded text and the proposal side by side, the
 * findings under review because of it, and — for a reviewer — the form that
 * resolves it. Nothing here edits the record; a resolution is a note on it.
 */
export function DisputeList({ disputes, findings, me, onResolve, emptyText }: DisputeListProps) {
  if (disputes.length === 0) {
    return <p className="text-muted-foreground text-sm">{emptyText}</p>;
  }
  const titleOf = (id: string) => {
    const finding = findings.find((item) => item.id === id);
    if (!finding) return id;
    return finding.is_dimension ? DIMENSION_TITLES[finding.dimension] : finding.title || id;
  };
  return (
    <ul className="grid gap-3">
      {disputes.map((dispute) => (
        <li key={dispute.id} className="border-border grid gap-3 rounded-lg border p-4">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {dispute.status === "open" ? (
              <Chip tone="caution" icon={<Flag size={14} aria-hidden />}>
                Open
              </Chip>
            ) : (
              <Chip tone="positive" icon={<CheckCircle size={14} aria-hidden />}>
                Resolved
              </Chip>
            )}
            <span className="font-mono">{dispute.id}</span>
            <span className="text-muted-foreground">Filed {formatTime(dispute.created_at)}</span>
          </div>

          <dl className="grid gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
                Recorded text
              </dt>
              <dd className="text-sm whitespace-pre-wrap">{dispute.original_text}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
                Proposed correction
              </dt>
              <dd className="text-sm whitespace-pre-wrap">{dispute.proposed_text}</dd>
            </div>
          </dl>

          <dl className="grid gap-1 text-sm">
            {dispute.reason ? (
              <div className="flex gap-2">
                <dt className="text-muted-foreground shrink-0">Reason:</dt>
                <dd>{dispute.reason}</dd>
              </div>
            ) : null}
            <div className="flex gap-2">
              <dt className="text-muted-foreground shrink-0">Affected findings:</dt>
              <dd>
                {dispute.affected_finding_ids.length === 0
                  ? "none"
                  : dispute.affected_finding_ids.map(titleOf).join("; ")}
              </dd>
            </div>
            {dispute.resolution ? (
              <div className="flex gap-2">
                <dt className="text-muted-foreground shrink-0">Resolution:</dt>
                <dd>
                  {dispute.resolution}
                  <span className="text-muted-foreground"> · {formatTime(dispute.resolved_at)}</span>
                </dd>
              </div>
            ) : null}
          </dl>

          {dispute.status === "open" && me === "reviewer" ? (
            <ResolveForm onResolve={(resolution) => onResolve(dispute.id, resolution)} />
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function ResolveForm({ onResolve }: { onResolve: (resolution: string) => Promise<void> }) {
  const id = useId();
  const [resolution, setResolution] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = resolution.trim();
    if (!text) {
      setError("Write how the correction was resolved.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onResolve(text);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : "Could not resolve the correction.");
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="border-border grid gap-2 border-t pt-3">
      <label htmlFor={id} className="text-sm font-medium">
        Resolution <span className="text-muted-foreground font-normal">(reviewer)</span>
      </label>
      <textarea
        id={id}
        rows={2}
        required
        maxLength={4000}
        value={resolution}
        onChange={(event) => setResolution(event.target.value)}
        className="border-border-strong bg-background text-foreground w-full rounded-lg border
          px-3 py-2 text-sm leading-relaxed"
        placeholder="What was decided, and why"
      />
      <div>
        <Button type="submit" variant="secondary" disabled={busy} aria-busy={busy}>
          {busy ? "Resolving…" : "Resolve correction"}
        </Button>
      </div>
      {error ? <ErrorText>{error}</ErrorText> : null}
    </form>
  );
}
