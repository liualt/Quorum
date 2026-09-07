import { Panel } from "@/components/ui/Panel";
import type { AssessmentEvidence, FindingView, Ref } from "@/lib/types";

import type { DrawerTab } from "./evidenceGraph";
import { LevelChip, RefButtons, ReviewChip } from "./FindingParts";
import { reviewReasonLabel } from "./labels";

interface FindingCardProps {
  finding: FindingView;
  title: string;
  evidence: AssessmentEvidence;
  onOpen: (ref: Ref, tab: DrawerTab) => void;
  headingLevel?: 2 | 3;
  className?: string;
}

/**
 * One finding in full: level, explanation, the three qualifying notes, review
 * state and the references behind it. The four dimensions and the selected
 * expanded finding are the same shape, so they share this card.
 */
export function FindingCard({
  finding,
  title,
  evidence,
  onOpen,
  headingLevel = 3,
  className,
}: FindingCardProps) {
  const notes: Array<[string, string]> = [
    ["Assistance", finding.assistance],
    ["Uncertainty", finding.uncertainty],
    ["Follow-up", finding.follow_up],
  ];
  return (
    <Panel
      title={title}
      headingLevel={headingLevel}
      actions={<LevelChip level={finding.observation_level} />}
      className={className}
    >
      <div className="grid grid-cols-1 gap-4">
        <p className="text-sm">{finding.explanation}</p>

        {finding.review_status === "needs_review" ? (
          <div className="grid gap-1.5">
            <div>
              <ReviewChip />
            </div>
            <ul className="text-muted-foreground list-disc pl-5 text-xs">
              {finding.review_reasons.map((reason) => (
                <li key={reason}>{reviewReasonLabel(reason)}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <dl className="grid gap-2 text-sm">
          {notes
            .filter(([, value]) => value)
            .map(([label, value]) => (
              <div key={label}>
                <dt className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
                  {label}
                </dt>
                <dd>{value}</dd>
              </div>
            ))}
        </dl>

        <RefButtons
          supporting={finding.supporting_refs}
          opposing={finding.opposing_refs}
          evidence={evidence}
          onOpen={onOpen}
        />
      </div>
    </Panel>
  );
}
