import Link from "next/link";
import type { ButtonHTMLAttributes, ComponentProps, ReactNode } from "react";

import { cx } from "@/lib/cx";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";
export type ButtonSize = "md" | "lg";

/*
 * Focus is not styled here: `app/globals.css` puts one `:focus-visible` outline
 * on every control in the app, so third-party controls get the same ring.
 */
const BASE =
  "inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg border " +
  "font-sans font-semibold whitespace-nowrap transition-colors duration-200 " +
  "disabled:cursor-not-allowed disabled:opacity-50";

const VARIANTS: Record<ButtonVariant, string> = {
  // The palette's CTA colour. Text is `on-accent` (near-black), not white:
  // white on #22C55E is 2.2:1 and would fail AA.
  primary:
    "border-transparent bg-accent text-on-accent hover:not-disabled:bg-accent/90",
  secondary:
    "border-border bg-transparent text-foreground hover:not-disabled:bg-muted",
  ghost:
    "border-transparent bg-transparent text-muted-foreground " +
    "hover:not-disabled:bg-muted hover:not-disabled:text-foreground",
  destructive:
    "border-transparent bg-destructive text-on-destructive " +
    "hover:not-disabled:bg-destructive/90",
};

// 44px and 48px: the minimum comfortable touch target and one step above it.
const SIZES: Record<ButtonSize, string> = {
  md: "min-h-11 px-4 text-sm",
  lg: "min-h-12 px-6 text-base",
};

export function buttonClasses(
  variant: ButtonVariant = "primary",
  size: ButtonSize = "md",
  className?: string,
): string {
  return cx(BASE, VARIANTS[variant], SIZES[size], className);
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  type = "button",
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={buttonClasses(variant, size, className)}
      {...props}
    >
      {children}
    </button>
  );
}

interface ButtonLinkProps extends ComponentProps<typeof Link> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
}

/** A navigation that looks like a button. Still an anchor, so it opens in a new
 *  tab, copies its href, and is announced as a link. */
export function ButtonLink({
  variant = "primary",
  size = "md",
  className,
  children,
  ...props
}: ButtonLinkProps) {
  return (
    <Link className={buttonClasses(variant, size, className)} {...props}>
      {children}
    </Link>
  );
}
