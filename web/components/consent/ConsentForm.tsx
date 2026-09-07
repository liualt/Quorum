"use client";

import { ArrowRight, Warning } from "@phosphor-icons/react/ssr";
import { useId, useState } from "react";

import { Button, ButtonLink } from "@/components/ui/Button";
import { CopyField } from "@/components/ui/CopyField";
import { Panel } from "@/components/ui/Panel";
import { ApiError, createInterview } from "@/lib/api";
import type { CreateInterviewResult } from "@/lib/types";

/** The wording the candidate agrees to. Do not paraphrase it. */
const CONSENT_TEXT =
  "I understand that AI interviewers will question me and that my speech and code will be processed to produce an assessment";

export function ConsentForm() {
  const nameId = useId();
  const nameHintId = useId();
  const consentId = useId();
  const submitHintId = useId();

  const [displayName, setDisplayName] = useState("");
  const [consented, setConsented] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<CreateInterviewResult | null>(null);

  if (created) {
    return <InterviewCreated result={created} />;
  }

  const trimmedName = displayName.trim();
  const canSubmit = consented && trimmedName.length > 0 && !submitting;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setError(null);
    try {
      setCreated(await createInterview(trimmedName));
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.detail
          : "Something went wrong. Please try again.",
      );
      setSubmitting(false);
    }
  };

  return (
    <Panel title="Start an interview">
      <form onSubmit={submit} noValidate className="grid gap-6">
        <div>
          <label htmlFor={nameId} className="mb-1 block text-sm font-medium">
            Display name or pseudonym
          </label>
          <input
            id={nameId}
            name="display_name"
            type="text"
            required
            maxLength={80}
            autoComplete="off"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            aria-describedby={nameHintId}
            className="border-border bg-background text-foreground min-h-11 w-full
              rounded-lg border px-3 text-base transition-colors duration-200
              placeholder:text-muted-foreground focus:border-accent"
            placeholder="e.g. Ada, or Candidate 7"
          />
          <p id={nameHintId} className="text-muted-foreground mt-1 text-sm">
            The panel and the report use this name. A pseudonym is fine — Quorum
            does not ask for your real name.
          </p>
        </div>

        {/* The whole bordered row is the label, so the touch target is the box
            rather than the 24px box-glyph inside it. */}
        <label
          htmlFor={consentId}
          className="border-border bg-background hover:border-accent flex cursor-pointer
            items-start gap-3 rounded-lg border p-4 text-sm transition-colors duration-200"
        >
          <input
            id={consentId}
            name="consent"
            type="checkbox"
            checked={consented}
            onChange={(event) => setConsented(event.target.checked)}
            className="accent-accent size-6 shrink-0 cursor-pointer"
          />
          <span>{CONSENT_TEXT}</span>
        </label>

        {error ? (
          <p
            role="alert"
            className="text-destructive flex items-start gap-2 text-sm"
          >
            <Warning size={18} aria-hidden className="mt-0.5 shrink-0" />
            {error}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="submit"
            size="lg"
            disabled={!canSubmit}
            aria-describedby={submitHintId}
          >
            {submitting ? "Creating interview…" : "Create interview"}
          </Button>
          <p id={submitHintId} className="text-muted-foreground text-sm">
            {consented
              ? "Creates a session and takes you to the workspace."
              : "Tick the box above to enable this button."}
          </p>
        </div>
      </form>
    </Panel>
  );
}

function InterviewCreated({ result }: { result: CreateInterviewResult }) {
  // The token only reaches the browser once, so the shareable link is built
  // here rather than fetched again later.
  const reviewerUrl =
    typeof window === "undefined"
      ? result.reviewer_path
      : new URL(result.reviewer_path, window.location.origin).toString();

  return (
    <Panel title="Interview created">
      <div className="grid gap-6">
        <p className="text-muted-foreground text-sm">
          Session{" "}
          <span className="text-foreground font-mono">{result.id}</span> is
          ready. Open the workspace when you are ready to begin — the panel waits
          for you.
        </p>

        <div>
          <ButtonLink href={result.candidate_path} size="lg">
            Enter workspace
            <ArrowRight size={18} aria-hidden weight="bold" />
          </ButtonLink>
        </div>

        <CopyField
          id="reviewer-link"
          label="Reviewer link"
          value={reviewerUrl}
          hint="Give this link to the hiring manager. It is shown once."
        />
      </div>
    </Panel>
  );
}
