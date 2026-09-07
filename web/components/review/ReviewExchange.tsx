"use client";

import { Warning } from "@phosphor-icons/react/ssr";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ButtonLink } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { ApiError, exchangeToken } from "@/lib/api";

/**
 * Trades a one-time reviewer token for a session cookie, then sends the
 * reviewer on to the assessment.
 *
 * The token sits in the URL, so this replaces the history entry rather than
 * pushing one: a back navigation must not land on a spent token.
 */
export function ReviewExchange({ token }: { token: string }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    exchangeToken(token, controller.signal)
      .then(({ interview_id }) => {
        router.replace(`/assessment/${interview_id}`);
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setError(
          cause instanceof ApiError && cause.status === 404
            ? "This reviewer link is not valid. It may have already been used, or the interview may have been deleted."
            : cause instanceof ApiError
              ? cause.detail
              : "Could not open the interview. Please try again.",
        );
      });

    return () => controller.abort();
  }, [token, router]);

  return (
    <main className="mx-auto w-full max-w-xl px-4 py-12 sm:px-6">
      {/* The panels below are h2s; the page still needs a top-level heading. */}
      <h1 className="sr-only">Reviewer link</h1>
      {error ? (
        <Panel title="Reviewer link not accepted">
          <div className="grid gap-4">
            <p
              role="alert"
              className="text-destructive flex items-start gap-2 text-sm"
            >
              <Warning size={18} aria-hidden className="mt-0.5 shrink-0" />
              {error}
            </p>
            <p className="text-muted-foreground text-sm">
              Reviewer links are shown once, when the interview is created. Ask
              the candidate for a new one.
            </p>
            <div>
              <ButtonLink href="/" variant="secondary">
                Back to the start
              </ButtonLink>
            </div>
          </div>
        </Panel>
      ) : (
        <Panel title="Opening the interview">
          <p role="status" className="text-muted-foreground text-sm">
            Checking your reviewer link…
          </p>
        </Panel>
      )}
    </main>
  );
}
