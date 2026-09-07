"use client";

import { useEffect, useState } from "react";

import { ApiError, getSnapshot } from "@/lib/api";
import type { SnapshotView } from "@/lib/types";

export interface SnapshotsState {
  byId: Record<string, SnapshotView>;
  loading: boolean;
  error: string | null;
}

/**
 * Load the snapshots the drawer needs, once each.
 *
 * Snapshots are immutable, so anything fetched stays cached for the life of
 * the report; opening the same run twice costs nothing the second time. An
 * error is remembered against the set of ids that produced it, so moving to a
 * different reference clears it and a failed set is not retried in a loop.
 */
export function useSnapshots(interviewId: string, ids: readonly string[]): SnapshotsState {
  const [cache, setCache] = useState<Record<string, SnapshotView>>({});
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null);
  const key = ids.join(",");

  useEffect(() => {
    const missing = (key ? key.split(",") : []).filter((id) => !(id in cache));
    if (missing.length === 0) return;

    const controller = new AbortController();
    Promise.all(missing.map((id) => getSnapshot(interviewId, id, controller.signal)))
      .then((views) => {
        setCache((previous) => {
          const next = { ...previous };
          for (const view of views) next[view.id] = view;
          return next;
        });
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setFailure({
          key,
          message: cause instanceof ApiError ? cause.detail : "Could not load the saved code.",
        });
      });
    return () => controller.abort();
  }, [interviewId, key, cache]);

  const wanted = key ? key.split(",") : [];
  const error = failure?.key === key ? failure.message : null;
  const loading = error === null && wanted.some((id) => !(id in cache));
  return { byId: cache, loading, error };
}
