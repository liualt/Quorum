"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorText } from "@/components/ui/ErrorText";
import { ApiError } from "@/lib/api";
import type { SegmentView } from "@/lib/types";

/** Mirrors the server's `TURN_TEXT_LIMIT`; the server still enforces its own. */
const TEXT_LIMIT = 4000;

const FIELD =
  "border-border-strong bg-background text-foreground w-full rounded-lg border px-3 py-2 " +
  "text-sm leading-relaxed";

interface DisputeFormProps {
  segment: SegmentView;
  onSubmit: (proposedText: string, reason: string) => Promise<void>;
  onCancel: () => void;
}

/**
 * The candidate's (or reviewer's) proposed correction to one segment.
 *
 * The field starts out holding the recorded text, so a correction is an edit
 * of what was heard rather than a retelling; the original is kept beside it
 * whatever is submitted.
 */
export function DisputeForm({ segment, onSubmit, onCancel }: DisputeFormProps) {
  const ids = useId();
  const textRef = useRef<HTMLTextAreaElement>(null);
  const [proposed, setProposed] = useState(segment.text);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    textRef.current?.focus();
  }, []);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = proposed.trim();
    if (!text) {
      setError("Enter the corrected text.");
      return;
    }
    if (text === segment.text.trim()) {
      setError("The corrected text is the same as the recorded text.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit(text, reason.trim());
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : "Could not file the correction.");
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      aria-labelledby={`${ids}-heading`}
      className="border-border-strong grid gap-3 rounded-lg border p-4"
    >
      <h3 id={`${ids}-heading`} className="text-sm font-semibold">
        Propose a correction
      </h3>
      <p className="text-muted-foreground text-xs">
        The recorded text stays on the record beside your correction. Findings that depend on
        this segment are marked for review until a reviewer resolves it.
      </p>

      <div className="grid gap-1">
        <label htmlFor={`${ids}-text`} className="text-sm font-medium">
          Corrected text
        </label>
        <textarea
          ref={textRef}
          id={`${ids}-text`}
          className={FIELD}
          rows={4}
          maxLength={TEXT_LIMIT}
          required
          value={proposed}
          onChange={(event) => setProposed(event.target.value)}
        />
      </div>

      <div className="grid gap-1">
        <label htmlFor={`${ids}-reason`} className="text-sm font-medium">
          Reason <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <textarea
          id={`${ids}-reason`}
          className={FIELD}
          rows={2}
          maxLength={TEXT_LIMIT}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="What was misheard or misunderstood"
        />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy} aria-busy={busy}>
          {busy ? "Filing…" : "File correction"}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
      {error ? <ErrorText>{error}</ErrorText> : null}
    </form>
  );
}
