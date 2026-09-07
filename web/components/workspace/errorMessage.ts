import { ApiError } from "@/lib/api";

/** The backend's own sentence when it sent one; the caller's wording otherwise. */
export function errorMessage(cause: unknown, fallback: string): string {
  return cause instanceof ApiError ? cause.detail : fallback;
}
