import { CheckCircle, Hourglass } from "@phosphor-icons/react/ssr";

import { AIBadge } from "@/components/ui/AIBadge";
import { Chip } from "@/components/ui/Chip";
import type { AssessmentView } from "@/lib/types";

import { formatTime } from "./labels";

/** The one sentence every report carries, word for word from the brief. */
const NOTE =
  "Findings are interpretations linked to recorded evidence. A passing check supports a " +
  "behavior under the recorded conditions only. Quorum does not make the hiring decision.";

export function ReportHeader({ assessment }: { assessment: AssessmentView }) {
  const { interview, status } = assessment;
  return (
    <header className="grid grid-cols-1 gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-muted-foreground mb-1 flex items-center gap-2 font-mono text-xs tracking-widest uppercase">
            Quorum
            <AIBadge />
            Assessment
          </p>
          <h1 className="text-2xl font-bold sm:text-3xl">{interview.display_name}</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Viewing as {assessment.me === "reviewer" ? "the reviewer" : "the candidate"}
          </p>
        </div>
        {status === "complete" ? (
          <Chip tone="positive" icon={<CheckCircle size={14} aria-hidden />}>
            Complete
          </Chip>
        ) : (
          <Chip tone="caution" icon={<Hourglass size={14} aria-hidden />}>
            Pending
          </Chip>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
        <Meta label="Finished" value={formatTime(interview.finished_at)} />
        <Meta label="Model" value={assessment.model_id} mono />
        <Meta label="Rubric" value={assessment.rubric_version} mono />
        <Meta label="Prompt" value={assessment.prompt_version} mono />
      </dl>

      <p className="border-accent border-l-4 pl-3 text-sm">{NOTE}</p>

      {status === "pending" ? (
        <div role="status" className="border-border-strong grid gap-1 rounded-lg border p-3 text-sm">
          <p>{assessment.summary}</p>
          <p className="text-muted-foreground">
            The findings below are what the recorded checks observed, not interpretations. A
            reviewer should read the transcript and the runs directly.
          </p>
        </div>
      ) : (
        <p className="text-sm">{assessment.summary}</p>
      )}
    </header>
  );
}

function Meta({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">{label}</dt>
      <dd className={mono ? "font-mono break-all" : undefined}>{value}</dd>
    </div>
  );
}
