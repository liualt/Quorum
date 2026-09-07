import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

/**
 * Tones for the states the product actually reports: a check that passed, one
 * that failed, an execution that was unavailable or a finding that needs
 * review, and plain informational state (stage, role, timer).
 */
export type ChipTone = "neutral" | "positive" | "negative" | "caution";

/*
 * The label always uses `--color-foreground` — 21:1 on the background and
 * 15.8:1 on a card, so a chip stays legible wherever it is dropped. Tinted
 * label colours were tried first and `--color-destructive` on a tinted surface
 * lands at 4.4:1, under AA for 12px text.
 *
 * Tone therefore lives in the border and the icon, which are non-text graphics
 * needing 3:1: on a card, accent is 6.9:1 and destructive 4.2:1. Colour only
 * ever reinforces a word that already names the state.
 */
const TONES: Record<ChipTone, { chip: string; icon: string }> = {
  neutral: { chip: "border-border bg-muted", icon: "text-muted-foreground" },
  positive: { chip: "border-accent bg-accent/10", icon: "text-accent" },
  negative: {
    chip: "border-destructive bg-destructive/10",
    icon: "text-destructive",
  },
  caution: { chip: "border-muted-foreground bg-muted", icon: "text-foreground" },
};

interface ChipProps {
  /**
   * A Phosphor icon, already sized. It is decorative — the chip's text carries
   * the meaning — so pass `aria-hidden` on the icon itself.
   */
  icon?: ReactNode;
  tone?: ChipTone;
  children: ReactNode;
  className?: string;
}

/**
 * A small status label. The text is always the status, never a colour gloss on
 * one, so the chip reads the same without colour perception.
 */
export function Chip({ icon, tone = "neutral", children, className }: ChipProps) {
  const { chip, icon: iconTone } = TONES[tone];
  return (
    <span
      className={cx(
        "text-foreground inline-flex min-w-0 items-center gap-1.5 rounded-full",
        "border px-2.5 py-1 font-mono text-xs font-medium whitespace-nowrap",
        chip,
        className,
      )}
    >
      {icon ? (
        <span className={cx("flex shrink-0 items-center", iconTone)}>{icon}</span>
      ) : null}
      <span className="min-w-0 truncate">{children}</span>
    </span>
  );
}
