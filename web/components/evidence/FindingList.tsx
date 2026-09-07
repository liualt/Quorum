import { CaretRight } from "@phosphor-icons/react/ssr";

import { cx } from "@/lib/cx";
import type { FindingView } from "@/lib/types";

import { LevelChip, ReviewChip } from "./FindingParts";
import { DIMENSION_TITLES } from "./labels";

interface FindingListProps {
  findings: FindingView[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/** The expanded findings as a selectable list; the chosen one drives the map. */
export function FindingList({ findings, selectedId, onSelect }: FindingListProps) {
  if (findings.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">No expanded findings were recorded.</p>
    );
  }
  return (
    <ul className="grid grid-cols-1 gap-2" aria-label="Findings">
      {findings.map((finding) => {
        const selected = finding.id === selectedId;
        return (
          <li key={finding.id}>
            <button
              type="button"
              aria-current={selected ? "true" : undefined}
              onClick={() => onSelect(finding.id)}
              className={cx(
                "flex w-full min-h-11 cursor-pointer items-start gap-2 rounded-lg border p-3",
                "text-left transition-colors duration-200",
                selected
                  ? "border-ring bg-muted"
                  : "border-border-strong hover:bg-muted",
              )}
            >
              <CaretRight
                size={16}
                aria-hidden
                weight={selected ? "bold" : "regular"}
                className={cx("mt-0.5 shrink-0", !selected && "text-muted-foreground")}
              />
              <span className="grid min-w-0 flex-1 gap-1.5">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold">
                    {finding.title || "Untitled finding"}
                  </span>
                  {finding.review_status === "needs_review" ? <ReviewChip /> : null}
                </span>
                <span className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
                  <span>{DIMENSION_TITLES[finding.dimension]}</span>
                  <LevelChip level={finding.observation_level} />
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
