import { Warning } from "@phosphor-icons/react/ssr";
import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

interface ErrorTextProps {
  children: ReactNode;
  className?: string;
}

/**
 * An inline failure message, announced when it appears.
 *
 * The prose uses `--color-destructive-text` (6.45:1 on the background, 5.66:1
 * on a card) rather than `--color-destructive`, which only reaches 4.16:1 on a
 * card and would fail AA for body text. The base destructive stays on the icon,
 * a non-text graphic where 3:1 is the bar.
 */
export function ErrorText({ children, className }: ErrorTextProps) {
  return (
    <p
      role="alert"
      className={cx(
        "text-destructive-text flex items-start gap-2 text-sm",
        className,
      )}
    >
      <Warning size={18} aria-hidden className="mt-0.5 shrink-0" />
      {children}
    </p>
  );
}
