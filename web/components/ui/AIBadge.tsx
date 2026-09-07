import { cx } from "@/lib/cx";

interface AIBadgeProps {
  className?: string;
}

/**
 * The one component that renders the "AI" label.
 *
 * Disclosure is a product requirement, not decoration: it sits next to every
 * interviewer role name and every interviewer utterance, so it must look and
 * read identically everywhere. Changing how AI content is marked in this app
 * means changing this file and nothing else.
 *
 * The visible text is "AI"; the appended screen-reader word makes it announce
 * as "AI generated" without repeating anything a sighted reader sees.
 */
export function AIBadge({ className }: AIBadgeProps) {
  return (
    <span
      className={cx(
        "border-accent text-accent inline-flex items-center rounded border",
        "px-1.5 py-0.5 font-mono text-xs leading-none font-bold tracking-wider",
        className,
      )}
    >
      AI
      <span className="sr-only"> generated</span>
    </span>
  );
}
