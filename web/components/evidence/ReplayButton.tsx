"use client";

import { ArrowsClockwise } from "@phosphor-icons/react/ssr";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorText } from "@/components/ui/ErrorText";
import { ApiError } from "@/lib/api";
import { cx } from "@/lib/cx";

interface ReplayButtonProps {
  /** Starts the rerun; rejects with the API's reason when it cannot start. */
  onRerun: () => Promise<void>;
  /** A rerun of this run is already queued or running. */
  rerunning: boolean;
}

/**
 * The control that replays a recorded run.
 *
 * Only rendered beside a run reference — a finding without a runnable check
 * never shows it (PRD section 5). The button reports the in-flight state in
 * words as well as by being disabled, and the server's refusals (a run already
 * in progress, the replay cap) are shown as they come.
 */
export function ReplayButton({ onRerun, rerunning }: ReplayButtonProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = busy || rerunning;

  // Disabling the focused button drops keyboard focus to the body; when the
  // rerun is over, put it back where the reader left it.
  const holder = useRef<HTMLDivElement>(null);
  const wasActive = useRef(false);
  useEffect(() => {
    if (wasActive.current && !active && document.activeElement === document.body) {
      holder.current?.querySelector("button")?.focus();
    }
    wasActive.current = active;
  }, [active]);

  const click = async () => {
    setBusy(true);
    setError(null);
    try {
      await onRerun();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : "Could not start the rerun.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-2" ref={holder}>
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={click} disabled={active} aria-busy={active}>
          <ArrowsClockwise
            size={18}
            aria-hidden
            className={cx(active && "animate-spin")}
          />
          {active ? "Rerunning…" : "Rerun check"}
        </Button>
        <p className="text-muted-foreground max-w-prose text-xs">
          Reruns the saved snapshot with the recorded fixture and check version. The original
          result is kept; a rerun that differs marks the findings that cite it for review.
        </p>
      </div>
      <p role="status" className="sr-only">
        {active ? "A rerun is in progress." : ""}
      </p>
      {error ? <ErrorText>{error}</ErrorText> : null}
    </div>
  );
}
