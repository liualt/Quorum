import type { Role, Speaker, Stage } from "@/lib/types";

/**
 * Human labels for the wire vocabularies the workspace shows.
 *
 * Kept in one file so the header chip, the role label and every caption agree
 * on what a stage or a role is called.
 */

export const STAGE_LABELS: Record<Stage, string> = {
  briefing: "Briefing",
  initial_review: "Initial review",
  investigation: "Investigation",
  changed_condition: "Changed condition",
  release_discussion: "Release discussion",
  assessment: "Assessment",
};

/** Matches `prompts.ROLE_LABELS` on the server, which is what the panel calls itself. */
export const ROLE_LABELS: Record<Role, string> = {
  technical: "Technical interviewer",
  product: "Product manager",
  customer: "Customer administrator",
};

export function isRole(speaker: Speaker): speaker is Role {
  return speaker in ROLE_LABELS;
}
