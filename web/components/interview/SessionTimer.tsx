"use client";

import { Clock } from "@phosphor-icons/react/ssr";
import { useEffect, useRef, useState } from "react";

import { Chip } from "@/components/ui/Chip";

interface SessionTimerProps {
  /** ISO timestamp the server recorded at the first `/start`. */
  startedAt: string | null;
  paused: boolean;
  capMinutes: number;
}

function pad(n: number): string {
  return n.toString().padStart(2, "0");
}

function clock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  return `${pad(Math.floor(total / 60))}:${pad(total % 60)}`;
}

/**
 * Time on the clock against the session cap.
 *
 * Paused time is taken out, but only the pauses this browser has seen: the
 * view does not carry the server's banked `paused_ms`, so after a reload the
 * timer counts from `started_at` as if the interview had never paused. The
 * server enforces the cap from its own record; this display is a guide.
 *
 * `role="timer"` is deliberately not a live region — a one-second tick must
 * never be announced.
 */
export function SessionTimer({ startedAt, paused, capMinutes }: SessionTimerProps) {
  const [elapsed, setElapsed] = useState(0);
  const pausedMs = useRef(0);
  const pausedSince = useRef<number | null>(null);

  useEffect(() => {
    if (!startedAt) return;
    if (paused) {
      // The last tick stays on screen until the interview resumes.
      pausedSince.current = Date.now();
      return;
    }
    if (pausedSince.current !== null) {
      pausedMs.current += Date.now() - pausedSince.current;
      pausedSince.current = null;
    }
    const started = Date.parse(startedAt);
    const tick = () => setElapsed(Date.now() - started - pausedMs.current);
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [paused, startedAt]);

  if (!startedAt) return null;

  const capMs = capMinutes * 60_000;
  const overCap = elapsed >= capMs;

  return (
    <Chip
      tone={overCap ? "caution" : "neutral"}
      icon={<Clock size={14} aria-hidden />}
      className="tabular-nums"
    >
      <span role="timer" aria-label="Session time">
        {clock(elapsed)} / {clock(capMs)}
      </span>
      {paused ? <span> · Paused</span> : null}
      {overCap && !paused ? <span> · Over the cap</span> : null}
    </Chip>
  );
}
