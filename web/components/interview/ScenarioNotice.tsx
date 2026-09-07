import { Info, X } from "@phosphor-icons/react/ssr";

import { Button } from "@/components/ui/Button";

interface ScenarioNoticeProps {
  text: string;
  /** Names of the checks this notice made available. */
  unlockedChecks: string[];
  onDismiss: () => void;
}

/**
 * The banner for new scenario information (PRD §5). A status region, so it is
 * announced once when it appears and never interrupts what the panel is saying.
 */
export function ScenarioNotice({ text, unlockedChecks, onDismiss }: ScenarioNoticeProps) {
  return (
    <div
      role="status"
      className="border-accent bg-accent/10 flex flex-wrap items-start gap-3 border-b px-4 py-3"
    >
      <Info size={22} aria-hidden className="text-accent mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1 text-sm">
        <p>
          <span className="font-semibold">New scenario information:</span> {text}
        </p>
        {unlockedChecks.length > 0 ? (
          <p className="text-muted-foreground mt-1">
            {unlockedChecks.length === 1
              ? `The ${unlockedChecks[0]} check is now available.`
              : `New checks are now available: ${unlockedChecks.join(", ")}.`}
          </p>
        ) : null}
      </div>
      <Button variant="ghost" onClick={onDismiss} aria-label="Dismiss scenario notice">
        <X size={18} aria-hidden />
        Dismiss
      </Button>
    </div>
  );
}
