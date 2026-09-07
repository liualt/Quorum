import {
  ChatText,
  CheckCircle,
  Circle,
  CircleHalf,
  Code,
  Play,
  Quotes,
  Warning,
} from "@phosphor-icons/react/ssr";
import type { ComponentType } from "react";

import { AIBadge } from "@/components/ui/AIBadge";
import { Chip, type ChipTone } from "@/components/ui/Chip";
import type { AssessmentEvidence, ObservationLevel, Ref, RefType } from "@/lib/types";

import { DEFAULT_TAB, type DrawerTab } from "./evidenceGraph";
import { LEVEL_LABELS, describeRef } from "./labels";

/*
 * Observation levels are not grades: only "demonstrated" gets the positive
 * tone, and the other two stay neutral rather than reading as failures.
 */
const LEVELS: Record<
  ObservationLevel,
  { tone: ChipTone; Icon: ComponentType<{ size?: number; "aria-hidden"?: boolean }> }
> = {
  demonstrated: { tone: "positive", Icon: CheckCircle },
  partly_demonstrated: { tone: "neutral", Icon: CircleHalf },
  not_observed: { tone: "neutral", Icon: Circle },
};

export function LevelChip({ level }: { level: ObservationLevel }) {
  const { tone, Icon } = LEVELS[level];
  return (
    <Chip tone={tone} icon={<Icon size={14} aria-hidden />}>
      {LEVEL_LABELS[level]}
    </Chip>
  );
}

/** Shown only while a finding is under review; "ok" has nothing to announce. */
export function ReviewChip() {
  return (
    <Chip tone="caution" icon={<Warning size={14} aria-hidden />}>
      Needs review
    </Chip>
  );
}

const REF_ICONS: Record<
  RefType,
  ComponentType<{ size?: number; "aria-hidden"?: boolean; className?: string }>
> = {
  segment: ChatText,
  claim: Quotes,
  run: Play,
  snapshot: Code,
};

interface RefButtonsProps {
  supporting: Ref[];
  opposing: Ref[];
  evidence: AssessmentEvidence;
  onOpen: (ref: Ref, tab: DrawerTab) => void;
}

/**
 * A finding's references as buttons that open the drawer.
 *
 * Support and opposition are told apart by the group headings, not by colour:
 * the buttons themselves look the same in both groups.
 */
export function RefButtons({ supporting, opposing, evidence, onOpen }: RefButtonsProps) {
  return (
    <div className="grid grid-cols-1 gap-3">
      <RefGroup label="Supporting evidence" refs={supporting} evidence={evidence} onOpen={onOpen} />
      <RefGroup label="Opposing evidence" refs={opposing} evidence={evidence} onOpen={onOpen} />
    </div>
  );
}

interface RefGroupProps {
  label: string;
  refs: Ref[];
  evidence: AssessmentEvidence;
  onOpen: (ref: Ref, tab: DrawerTab) => void;
}

function RefGroup({ label, refs, evidence, onOpen }: RefGroupProps) {
  if (refs.length === 0) {
    return (
      <p className="text-muted-foreground text-xs">
        <span className="font-semibold tracking-wide uppercase">{label}:</span> none recorded
      </p>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-1.5">
      <p className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">{label}</p>
      <ul className="flex flex-wrap gap-2">
        {refs.map((ref) => {
          const { label: text, ai } = describeRef(ref, evidence);
          const Icon = REF_ICONS[ref.type];
          return (
            // min-w-0: a flex item's minimum is its content, which would keep
            // the chip from shrinking and the label from truncating.
            <li key={`${ref.type}:${ref.id}`} className="min-w-0">
              <button
                type="button"
                onClick={() => onOpen(ref, DEFAULT_TAB[ref.type])}
                className="border-border-strong hover:bg-muted inline-flex max-w-full min-h-11
                  cursor-pointer items-center gap-1.5 rounded-full border px-3 font-mono text-xs
                  transition-colors duration-200"
              >
                <Icon size={14} aria-hidden className="shrink-0" />
                {ai ? <AIBadge className="shrink-0" /> : null}
                {/* One line, shortened if it must be; the accessible name stays whole. */}
                <span className="min-w-0 truncate">{text}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
