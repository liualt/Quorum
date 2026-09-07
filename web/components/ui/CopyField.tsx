"use client";

import { Check, Copy } from "@phosphor-icons/react/ssr";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";

interface CopyFieldProps {
  label: string;
  /** Explains what the value is for. Wired to the input with aria-describedby. */
  hint?: string;
  value: string;
  id: string;
}

/**
 * A read-only value with a copy button.
 *
 * The value stays selectable in a real input so a viewer without clipboard
 * permission — or without JavaScript's clipboard API — can still select and
 * copy it by hand.
 */
export function CopyField({ label, hint, value, id }: CopyFieldProps) {
  const [copied, setCopied] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current);
    },
    [],
  );

  const copy = async () => {
    inputRef.current?.select();
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      if (timer.current !== null) clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 3000);
    } catch {
      // No clipboard permission: the value is selected above, so Ctrl+C works.
      setCopied(false);
    }
  };

  const hintId = hint ? `${id}-hint` : undefined;

  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">
        {label}
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={inputRef}
          id={id}
          type="text"
          readOnly
          value={value}
          aria-describedby={hintId}
          onFocus={(event) => event.currentTarget.select()}
          className="border-border-strong bg-background text-foreground min-h-11 min-w-0 flex-1
            rounded-lg border px-3 font-mono text-sm"
        />
        <Button variant="secondary" onClick={copy}>
          {copied ? (
            <Check size={18} aria-hidden weight="bold" />
          ) : (
            <Copy size={18} aria-hidden />
          )}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      {hint ? (
        <p id={hintId} className="text-muted-foreground mt-1 text-sm">
          {hint}
        </p>
      ) : null}
      <span role="status" className="sr-only">
        {copied ? `${label} copied to the clipboard` : ""}
      </span>
    </div>
  );
}
