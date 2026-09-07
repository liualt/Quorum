/**
 * The only place in the web app that talks to the backend.
 *
 * Every function is one route from the "HTTP API" table in
 * `docs/superpowers/plans/2026-09-07-quorum-interfaces.md`. Requests go to
 * same-origin `/api/...` paths, which `next.config.ts` rewrites to the FastAPI
 * server — that keeps the capability cookie first-party and satisfies the
 * backend's Origin check on mutations.
 */

import type {
  AssessmentView,
  CreateInterviewResult,
  DisputeView,
  ExchangeResult,
  FileMap,
  FinishResult,
  InterviewView,
  PausedResult,
  RunView,
  SaveFilesResult,
  SnapshotView,
  StartInterviewResult,
  TranscriptResult,
  TurnResult,
} from "./types";

/** A non-2xx response. `detail` is the backend's `{"detail": ...}` message. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

async function readDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") return detail;
    // FastAPI answers a 422 with a list of validation problems rather than a
    // sentence. Joining the messages beats showing "Unprocessable Entity".
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => (item as { msg?: unknown })?.msg)
        .filter((msg): msg is string => typeof msg === "string");
      if (messages.length > 0) return messages.join("; ");
    }
  } catch {
    // A proxy error or a dropped connection can answer with something that is
    // not JSON; fall through to the status text.
  }
  return response.statusText || `Request failed with status ${response.status}`;
}

/**
 * Issue one API call. Throws `ApiError` on a non-2xx answer; returns `undefined
 * as T` for 204, which only `deleteInterview` produces.
 */
async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal } = options;

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      signal,
      credentials: "same-origin",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, "Could not reach the Quorum server.");
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

const base = (interviewId: string) =>
  `/api/interviews/${encodeURIComponent(interviewId)}`;

/* ------------------------------------------------------------------ lifecycle */

export function createInterview(
  displayName: string,
  signal?: AbortSignal,
): Promise<CreateInterviewResult> {
  return request("/api/interviews", {
    method: "POST",
    body: { display_name: displayName, consent: true },
    signal,
  });
}

export function exchangeToken(
  token: string,
  signal?: AbortSignal,
): Promise<ExchangeResult> {
  return request("/api/auth/exchange", { method: "POST", body: { token }, signal });
}

export function getInterview(
  interviewId: string,
  signal?: AbortSignal,
): Promise<InterviewView> {
  return request(base(interviewId), { signal });
}

/**
 * Go live. `voice: false` is the candidate choosing text, and the server then
 * starts no voice agent however it is configured — a paid session nobody joined
 * is the one thing a public demo must not do.
 */
export function startInterview(
  interviewId: string,
  options: { voice: boolean },
  signal?: AbortSignal,
): Promise<StartInterviewResult> {
  return request(`${base(interviewId)}/start`, {
    method: "POST",
    body: { voice: options.voice },
    signal,
  });
}

export function setPaused(
  interviewId: string,
  paused: boolean,
  signal?: AbortSignal,
): Promise<PausedResult> {
  return request(`${base(interviewId)}/pause`, {
    method: "POST",
    body: { paused },
    signal,
  });
}

export function finishInterview(
  interviewId: string,
  signal?: AbortSignal,
): Promise<FinishResult> {
  return request(`${base(interviewId)}/finish`, { method: "POST", signal });
}

export function deleteInterview(
  interviewId: string,
  signal?: AbortSignal,
): Promise<void> {
  return request(base(interviewId), { method: "DELETE", signal });
}

/* ------------------------------------------------------------ code and running */

export function saveFiles(
  interviewId: string,
  files: FileMap,
  signal?: AbortSignal,
): Promise<SaveFilesResult> {
  return request(`${base(interviewId)}/files`, {
    method: "PUT",
    body: { files },
    signal,
  });
}

export function getSnapshot(
  interviewId: string,
  snapshotId: string,
  signal?: AbortSignal,
): Promise<SnapshotView> {
  return request(
    `${base(interviewId)}/snapshots/${encodeURIComponent(snapshotId)}`,
    { signal },
  );
}

export function startRun(
  interviewId: string,
  snapshotId: string,
  checkIds: string[],
  idempotencyKey?: string,
  signal?: AbortSignal,
): Promise<RunView> {
  return request(`${base(interviewId)}/runs`, {
    method: "POST",
    body: {
      snapshot_id: snapshotId,
      check_ids: checkIds,
      ...(idempotencyKey === undefined ? {} : { idempotency_key: idempotencyKey }),
    },
    signal,
  });
}

export function listRuns(
  interviewId: string,
  signal?: AbortSignal,
): Promise<RunView[]> {
  return request(`${base(interviewId)}/runs`, { signal });
}

export function getRun(
  interviewId: string,
  runId: string,
  signal?: AbortSignal,
): Promise<RunView> {
  return request(`${base(interviewId)}/runs/${encodeURIComponent(runId)}`, {
    signal,
  });
}

export function startReplay(
  interviewId: string,
  runId: string,
  signal?: AbortSignal,
): Promise<RunView> {
  return request(`${base(interviewId)}/replays`, {
    method: "POST",
    body: { run_id: runId },
    signal,
  });
}

/* ------------------------------------------------------------------ conversation */

export function sendTurn(
  interviewId: string,
  text: string,
  signal?: AbortSignal,
): Promise<TurnResult> {
  return request(`${base(interviewId)}/turns`, {
    method: "POST",
    body: { text },
    signal,
  });
}

export function reportTranscript(
  interviewId: string,
  speaker: "agent" | "candidate",
  status: "end" | "interrupted",
  text: string,
  turnId: number,
  signal?: AbortSignal,
): Promise<TranscriptResult> {
  return request(`${base(interviewId)}/transcript`, {
    method: "POST",
    body: { speaker, status, text, turn_id: turnId },
    signal,
  });
}

/* -------------------------------------------------------- assessment and disputes */

export function getAssessment(
  interviewId: string,
  signal?: AbortSignal,
): Promise<AssessmentView> {
  return request(`${base(interviewId)}/assessment`, { signal });
}

export function createDispute(
  interviewId: string,
  segmentId: string,
  proposedText: string,
  reason: string,
  signal?: AbortSignal,
): Promise<DisputeView> {
  return request(`${base(interviewId)}/disputes`, {
    method: "POST",
    body: { segment_id: segmentId, proposed_text: proposedText, reason },
    signal,
  });
}

export function resolveDispute(
  interviewId: string,
  disputeId: string,
  resolution: string,
  signal?: AbortSignal,
): Promise<DisputeView> {
  return request(
    `${base(interviewId)}/disputes/${encodeURIComponent(disputeId)}/resolve`,
    { method: "POST", body: { resolution }, signal },
  );
}
