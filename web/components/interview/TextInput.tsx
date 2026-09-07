"use client";

import { PaperPlaneRight } from "@phosphor-icons/react/ssr";
import { useId, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorText } from "@/components/ui/ErrorText";

interface TextInputProps {
  /** Whether typed text goes to the voice agent or straight to the backend. */
  mode: "voice" | "text";
  /** Why the input is closed, or null when it is open. */
  blocked: string | null;
  onSend: (text: string) => Promise<void>;
}

const MAX_LENGTH = 4000;

/**
 * Typing to the panel. Enter sends, Shift+Enter breaks a line. Errors sit
 * under the field; the text is kept so the candidate can send it again.
 */
export function TextInput({ mode, blocked, onSend }: TextInputProps) {
  const inputId = useId();
  const hintId = useId();
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmed = text.trim();
  const canSend = blocked === null && !sending && trimmed.length > 0;

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!canSend) return;
    setSending(true);
    setError(null);
    try {
      await onSend(trimmed);
      setText("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not send that. Try again.");
    } finally {
      setSending(false);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };

  return (
    <form onSubmit={submit} className="grid gap-2">
      <label htmlFor={inputId} className="text-sm font-medium">
        Message the panel
      </label>
      <div className="flex items-end gap-2">
        <textarea
          id={inputId}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          maxLength={MAX_LENGTH}
          disabled={blocked !== null || sending}
          aria-describedby={hintId}
          placeholder={mode === "voice" ? "Type instead of speaking…" : "Type your reply…"}
          className="border-border-strong bg-background text-foreground placeholder:text-muted-foreground
            focus:border-accent min-h-11 min-w-0 flex-1 resize-y rounded-lg border px-3 py-2
            text-base transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-50"
        />
        <Button type="submit" disabled={!canSend} aria-label="Send message">
          <PaperPlaneRight size={18} aria-hidden />
          {sending ? "Sending…" : "Send"}
        </Button>
      </div>
      <p id={hintId} className="text-muted-foreground text-sm">
        {blocked ??
          (mode === "voice"
            ? "Enter sends. Typed messages reach the interviewer as text and are part of the record."
            : "Enter sends. The panel replies here in text.")}
      </p>
      {error ? <ErrorText>{error}</ErrorText> : null}
    </form>
  );
}
