"use client";

import { useEffect, useRef } from "react";

import { Chip } from "@/components/ui/Chip";
import { Panel } from "@/components/ui/Panel";
import type { LiveCaption } from "@/lib/voice";
import type { SegmentKind, SegmentView } from "@/lib/types";

import { isRole } from "./labels";
import { RoleLabel } from "./RoleLabel";

interface CaptionsProps {
  /** The record, in the order the server produced it. */
  segments: SegmentView[];
  /** Captions still being spoken. Visual only; the record follows. */
  live: LiveCaption[];
  candidateName: string;
}

const KIND_LABELS: Partial<Record<SegmentKind, string>> = {
  hint: "Hint",
  scenario_notice: "Scenario notice",
};

const NEAR_BOTTOM_PX = 48;

function timeOf(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * The transcript as the candidate sees it during the interview.
 *
 * One `role="log"` region holds the record; each stored segment is announced
 * once when it lands. In-progress captions sit below it, outside the live
 * region and hidden from assistive technology: they change several times a
 * second, and the same words are announced once as a segment when the turn
 * ends.
 */
export function Captions({ segments, live, candidateName }: CaptionsProps) {
  const scroller = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);

  useEffect(() => {
    const el = scroller.current;
    if (el && nearBottom.current) el.scrollTop = el.scrollHeight;
  }, [segments, live]);

  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    nearBottom.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
  };

  return (
    <Panel title="Captions" padded={false}>
      <div
        ref={scroller}
        onScroll={onScroll}
        className="h-72 overflow-y-auto lg:h-[26rem]"
      >
        {/* The live region wraps the list rather than being it, so the list
            keeps its list semantics. */}
        <div role="log" aria-live="polite" aria-relevant="additions text">
          <ol className="divide-border divide-y">
            {segments.length === 0 ? (
              <li className="text-muted-foreground px-4 py-6 text-sm">
                The panel&apos;s greeting will appear here once you join.
              </li>
            ) : null}
            {segments.map((segment) => (
              <li key={segment.id} className="grid gap-1 px-4 py-3">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <Speaker segment={segment} candidateName={candidateName} />
                  {KIND_LABELS[segment.kind] ? (
                    <Chip>{KIND_LABELS[segment.kind]}</Chip>
                  ) : null}
                  {segment.status === "interrupted" ? (
                    <Chip tone="caution">Interrupted</Chip>
                  ) : null}
                  <time
                    dateTime={segment.created_at}
                    className="text-muted-foreground ml-auto font-mono"
                  >
                    {timeOf(segment.created_at)}
                  </time>
                </div>
                <p className="text-sm whitespace-pre-wrap">
                  {segment.spoken_text ?? segment.text}
                </p>
              </li>
            ))}
          </ol>
        </div>
        {live.length > 0 ? (
          <div aria-hidden className="border-border border-t px-4 py-3">
            {live.map((caption) => (
              <p
                key={`${caption.speaker}-${caption.turnId}`}
                className="text-muted-foreground text-sm italic"
              >
                <span className="font-mono not-italic">
                  {caption.speaker === "agent" ? "AI" : candidateName} ·{" "}
                </span>
                {caption.text}
              </p>
            ))}
          </div>
        ) : null}
      </div>
    </Panel>
  );
}

function Speaker({
  segment,
  candidateName,
}: {
  segment: SegmentView;
  candidateName: string;
}) {
  if (isRole(segment.speaker)) return <RoleLabel role={segment.speaker} />;
  return (
    <span className="font-mono text-sm font-semibold">
      {segment.speaker === "candidate" ? candidateName : "System"}
    </span>
  );
}
