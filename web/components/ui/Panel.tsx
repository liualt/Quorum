import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

interface PanelProps {
  /** Rendered as the panel's heading. Omit for an untitled surface. */
  title?: ReactNode;
  /** Controls or status shown on the heading row, opposite the title. */
  actions?: ReactNode;
  /** Heading level, so a page's panels nest under its `h1` correctly. */
  headingLevel?: 2 | 3;
  children: ReactNode;
  className?: string;
  /** Padding is on by default; turn it off for edge-to-edge content (Monaco). */
  padded?: boolean;
}

/**
 * The app's card surface: a bordered region on `--color-card`. It is a static
 * container, not a control — the whole card is never clickable, so the buttons
 * inside it stay the only click targets.
 */
export function Panel({
  title,
  actions,
  headingLevel = 2,
  children,
  className,
  padded = true,
}: PanelProps) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <section
      className={cx(
        "border-border bg-card text-card-foreground rounded-xl border shadow-md",
        className,
      )}
    >
      {title !== undefined || actions !== undefined ? (
        <div
          className={cx(
            "border-border flex flex-wrap items-center justify-between gap-2 border-b",
            padded ? "px-6 py-3" : "px-4 py-3",
          )}
        >
          {title !== undefined ? (
            <Heading className="text-sm font-semibold tracking-wide uppercase">
              {title}
            </Heading>
          ) : (
            <span />
          )}
          {actions}
        </div>
      ) : null}
      <div className={padded ? "p-6" : undefined}>{children}</div>
    </section>
  );
}
