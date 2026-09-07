import { Flag, Warning } from "@phosphor-icons/react/ssr";

import { AIBadge } from "@/components/ui/AIBadge";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import type { SegmentView } from "@/lib/types";

import {
  KIND_LABELS,
  STAGE_LABELS,
  formatOffset,
  formatTime,
  isAISpeaker,
  speakerLabel,
} from "./labels";

interface TranscriptSegmentProps {
  segment: SegmentView;
  /** Omit to render the segment without the correction control. */
  onFlag?: () => void;
  /** Whether the correction form this button reveals is open. */
  flagOpen?: boolean;
}

/** One transcript segment exactly as recorded, with the control to dispute it. */
export function TranscriptSegment({ segment, onFlag, flagOpen = false }: TranscriptSegmentProps) {
  return (
    <article className="border-border grid gap-3 rounded-lg border p-4">
      <header className="flex flex-wrap items-center gap-2">
        {isAISpeaker(segment.speaker) ? <AIBadge /> : null}
        <span className="text-sm font-semibold">{speakerLabel(segment.speaker)}</span>
        <Chip>{KIND_LABELS[segment.kind]}</Chip>
        <Chip>{STAGE_LABELS[segment.stage]}</Chip>
        {segment.status === "interrupted" ? (
          <Chip tone="caution" icon={<Warning size={14} aria-hidden />}>
            Interrupted
          </Chip>
        ) : null}
      </header>

      <p className="text-sm leading-relaxed whitespace-pre-wrap">{segment.text}</p>

      <dl className="text-muted-foreground grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono text-xs">
        <dt>Recorded</dt>
        <dd>{formatTime(segment.created_at)}</dd>
        {segment.start_ms !== null ? (
          <>
            <dt>Timing</dt>
            <dd>
              {formatOffset(segment.start_ms)}
              {segment.end_ms !== null ? ` – ${formatOffset(segment.end_ms)}` : ""} into the
              session
            </dd>
          </>
        ) : null}
        <dt>Segment</dt>
        <dd className="break-all">{segment.id}</dd>
      </dl>

      {onFlag ? (
        <div>
          <Button variant="secondary" onClick={onFlag} aria-expanded={flagOpen}>
            <Flag size={18} aria-hidden />
            Flag this segment
          </Button>
        </div>
      ) : null}
    </article>
  );
}
