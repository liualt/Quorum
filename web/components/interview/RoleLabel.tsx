import { AIBadge } from "@/components/ui/AIBadge";
import { cx } from "@/lib/cx";
import type { Role } from "@/lib/types";

import { ROLE_LABELS } from "./labels";

interface RoleLabelProps {
  role: Role;
  className?: string;
}

/**
 * "AI · Technical interviewer" — the disclosure the design system requires on
 * every role name. The badge carries the "AI" text; the dot is decoration.
 */
export function RoleLabel({ role, className }: RoleLabelProps) {
  return (
    <span
      className={cx("inline-flex items-center gap-2 font-mono text-sm", className)}
    >
      <AIBadge />
      <span aria-hidden className="text-muted-foreground">
        ·
      </span>
      <span>{ROLE_LABELS[role]}</span>
    </span>
  );
}
