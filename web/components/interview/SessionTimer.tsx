"use client";

import { Clock } from "@phosphor-icons/react/ssr";
import { useEffect, useRef, useState } from "react";

import { Chip } from "@/components/ui/Chip";

interface SessionTimerProps {
  /** ISO timestamp the server recorded at the first `/start`. */
  startedAt: string | null;
  paused: boolean;
  /** Paused time the server has banked, from the interview record. */
  pausedMs: number;
  /** When the server's record says the current pause began, if it is paused. */
  pausedAt: string | null;
  capMinutes: number;
}

/**
 * What the clock is counted from: the server's banked pauses plus the one
 * pause, if any, that is still open.
 */
export interface PauseLedger {
  startedAt: number;
  bankedMs: number;
  pausedSince: number | null;
}

/** Elapsed session time at `now`, with every pause taken out. */
export function elapsedMs(ledger: PauseLedger, now: number): number {
  const open = ledger.pausedSince === null ? 0 : Math.max(0, now - ledger.pausedSince);
  return now - ledger.startedAt - ledger.bankedMs - open;
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
 * The ledger starts from the server's record — `paused_ms` banked so far and
 * `paused_at` for a pause still open — so a reloaded page shows the same clock
 * the server keeps. Pause and resume seen after that (the `paused` prop, fed by
 * the candidate's own action or the `pause_changed` event) extend the ledger
 * locally; a fresh record from the server replaces it. The server enforces the
 * cap from its own record; this display is a guide.
 *
 * `role="timer"` is deliberately not a live region — a one-second tick must
 * never be announced.
 */
export function SessionTimer({
  startedAt,
  paused,
  pausedMs,
  pausedAt,
  capMinutes,
}: SessionTimerProps) {
  const [elapsed, setElapsed] = useState(0);
  const ledger = useRef<PauseLedger | null>(null);
  // Declared first so the record effect below reads this render's `paused`
  // without depending on it (effects run in declaration order).
  const pausedRef = useRef(paused);
  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  // The server's record is authoritative whenever it changes.
  useEffect(() => {
    if (!startedAt) {
      ledger.current = null;
      return;
    }
    const openedAt = pausedAt ? Date.parse(pausedAt) : null;
    ledger.current = {
      startedAt: Date.parse(startedAt),
      bankedMs: pausedMs,
      // A record that says paused without a timestamp still stops the clock.
      pausedSince: openedAt ?? (pausedRef.current ? Date.now() : null),
    };
    setElapsed(elapsedMs(ledger.current, Date.now()));
  }, [pausedAt, pausedMs, startedAt]);

  // Pauses observed since that record, closed or opened at the moment seen.
  useEffect(() => {
    const current = ledger.current;
    if (!current) return;
    const now = Date.now();
    if (paused && current.pausedSince === null) {
      current.pausedSince = now;
    } else if (!paused && current.pausedSince !== null) {
      current.bankedMs += Math.max(0, now - current.pausedSince);
      current.pausedSince = null;
    }
    setElapsed(elapsedMs(current, now));
  }, [paused]);

  useEffect(() => {
    if (!startedAt) return;
    const tick = () => {
      if (ledger.current) setElapsed(elapsedMs(ledger.current, Date.now()));
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [startedAt]);

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
