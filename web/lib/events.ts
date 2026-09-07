"use client";

import { useEffect, useRef } from "react";

import { SESSION_EVENT_TYPES } from "./types";
import type { SessionEvent } from "./types";

const INITIAL_RETRY_MS = 1_000;
const MAX_RETRY_MS = 10_000;

/**
 * Subscribe to one interview's server-sent event stream.
 *
 * The browser's own `EventSource` reconnect is not usable here: it replays the
 * original URL, and the backend needs the `after` cursor of the last event we
 * actually saw so it can replay the gap from the database. So the stream is
 * closed on error and reopened with a fresh cursor, backing off 1s → 10s.
 *
 * `onEvent` is read through a ref, so passing an inline callback does not tear
 * the connection down and lose the cursor on every render.
 *
 * **Consumers must handle events idempotently.** The cursor lives in the effect,
 * so it restarts at 0 on every mount and the backend replays the interview's
 * whole history — a remount, a route change back into the workspace, or React's
 * StrictMode double-mount in development all redeliver events already seen.
 * Key state by `seq` or by the record id inside the payload (`segment.id`,
 * `run.id`); never append to a list or increment a counter on arrival.
 */
export function useSessionEvents(
  interviewId: string | null,
  onEvent: (event: SessionEvent) => void,
): void {
  const onEventRef = useRef(onEvent);
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!interviewId) return;

    let source: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let retryMs = INITIAL_RETRY_MS;
    let lastSeq = 0;
    let closed = false;

    const handle = (message: MessageEvent<string>) => {
      let event: SessionEvent;
      try {
        event = JSON.parse(message.data) as SessionEvent;
      } catch {
        // A truncated frame is not worth tearing the stream down for; the next
        // reconnect replays from `lastSeq` anyway.
        return;
      }
      if (typeof event.seq === "number" && event.seq > lastSeq) {
        lastSeq = event.seq;
      }
      onEventRef.current(event);
    };

    const connect = () => {
      if (closed) return;

      source = new EventSource(
        `/api/interviews/${encodeURIComponent(interviewId)}/events?after=${lastSeq}`,
        { withCredentials: true },
      );

      for (const type of SESSION_EVENT_TYPES) {
        source.addEventListener(type, handle as EventListener);
      }

      source.onopen = () => {
        retryMs = INITIAL_RETRY_MS;
      };

      source.onerror = () => {
        source?.close();
        source = null;
        if (closed) return;
        retryTimer = setTimeout(connect, retryMs);
        retryMs = Math.min(retryMs * 2, MAX_RETRY_MS);
      };
    };

    connect();

    return () => {
      closed = true;
      if (retryTimer !== null) clearTimeout(retryTimer);
      source?.close();
      source = null;
    };
  }, [interviewId]);
}
