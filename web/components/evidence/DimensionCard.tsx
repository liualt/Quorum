import type { AssessmentEvidence, FindingView, Ref } from "@/lib/types";

import type { DrawerTab } from "./evidenceGraph";
import { FindingCard } from "./FindingCard";
import { DIMENSION_TITLES } from "./labels";

interface DimensionCardProps {
  finding: FindingView;
  evidence: AssessmentEvidence;
  onOpen: (ref: Ref, tab: DrawerTab) => void;
}

/**
 * One of the four assessment dimensions. The card is a `FindingCard` under the
 * rubric's title for the dimension rather than the model's own title, so the
 * four always read in the same words whatever the model called them.
 */
export function DimensionCard({ finding, evidence, onOpen }: DimensionCardProps) {
  return (
    <FindingCard
      finding={finding}
      title={DIMENSION_TITLES[finding.dimension]}
      evidence={evidence}
      onOpen={onOpen}
      headingLevel={3}
    />
  );
}
