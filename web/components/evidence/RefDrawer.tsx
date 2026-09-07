"use client";

import { useState } from "react";

import { ErrorText } from "@/components/ui/ErrorText";
import type {
  AssessmentView,
  ClaimView,
  DisputeView,
  FileMap,
  FindingView,
  Participant,
  Ref,
  RunView,
  SegmentView,
  SnapshotView,
} from "@/lib/types";

import { DiffView, type DiffSide } from "./DiffView";
import { DisputeForm } from "./DisputeForm";
import { DisputeList } from "./DisputeList";
import { EvidenceDrawer, type DrawerTabSpec } from "./EvidenceDrawer";
import type { DrawerTab } from "./evidenceGraph";
import { CLAIM_TYPE_LABELS, STAGE_LABELS, formatTime, shortHash } from "./labels";
import { ReplayButton } from "./ReplayButton";
import { RunCompare } from "./RunCompare";
import { isRunActive, replaysOf, runBefore, type DiffTarget } from "./runDiff";
import { TranscriptSegment } from "./TranscriptSegment";
import type { SnapshotsState } from "./useSnapshots";

export interface DrawerTarget {
  ref: Ref;
  tab: DrawerTab;
}

interface RefDrawerProps {
  target: DrawerTarget;
  assessment: AssessmentView;
  runs: RunView[];
  checkNames: Record<string, string>;
  snapshots: SnapshotsState;
  diff: DiffTarget | null;
  /** The scenario's editable files, for a diff with no earlier snapshot. */
  fallbackFiles: FileMap | null;
  onClose: () => void;
  onRerun: (runId: string) => Promise<void>;
  onCreateDispute: (segmentId: string, proposedText: string, reason: string) => Promise<void>;
  onResolveDispute: (disputeId: string, resolution: string) => Promise<void>;
}

const RUN_TABS: DrawerTabSpec[] = [
  { id: "results", label: "Results" },
  { id: "code", label: "Code" },
];

/**
 * What the drawer shows for each kind of reference.
 *
 * Keyed by the reference so that moving to another one resets the tab and the
 * correction form instead of carrying them across.
 */
export function RefDrawer(props: RefDrawerProps) {
  return <RefDrawerBody key={`${props.target.ref.type}:${props.target.ref.id}`} {...props} />;
}

function RefDrawerBody({
  target,
  assessment,
  runs,
  checkNames,
  snapshots,
  diff,
  fallbackFiles,
  onClose,
  onRerun,
  onCreateDispute,
  onResolveDispute,
}: RefDrawerProps) {
  const [tab, setTab] = useState<DrawerTab>(target.tab);
  const { ref } = target;
  const { evidence } = assessment;
  const findings = [...assessment.dimensions, ...assessment.findings];
  const segmentPanel = (segment: SegmentView) => (
    <SegmentPanel
      segment={segment}
      disputes={assessment.disputes}
      findings={findings}
      me={assessment.me}
      onCreateDispute={onCreateDispute}
      onResolveDispute={onResolveDispute}
    />
  );

  switch (ref.type) {
    case "segment": {
      const segment = evidence.segments[ref.id];
      return (
        <EvidenceDrawer title="Transcript segment" subtitle={ref.id} onClose={onClose}>
          {segment ? segmentPanel(segment) : <Missing what="segment" />}
        </EvidenceDrawer>
      );
    }
    case "claim": {
      const claim = evidence.claims[ref.id];
      const segment = claim ? evidence.segments[claim.segment_id] : undefined;
      return (
        <EvidenceDrawer
          title={claim ? CLAIM_TYPE_LABELS[claim.claim_type] : "Statement"}
          subtitle={ref.id}
          onClose={onClose}
        >
          {claim ? (
            <div className="grid gap-4">
              <ClaimPanel claim={claim} />
              {segment ? (
                segmentPanel(segment)
              ) : (
                <p className="text-muted-foreground text-sm">
                  The segment this was read from ({claim.segment_id}) is not part of this
                  report&rsquo;s evidence.
                </p>
              )}
            </div>
          ) : (
            <Missing what="statement" />
          )}
        </EvidenceDrawer>
      );
    }
    case "run": {
      const run = runs.find((item) => item.id === ref.id) ?? evidence.runs[ref.id];
      return (
        <EvidenceDrawer
          title="Run"
          subtitle={ref.id}
          tabs={RUN_TABS}
          activeTab={tab}
          onTabChange={(id) => setTab(id as DrawerTab)}
          onClose={onClose}
        >
          {!run ? (
            <Missing what="run" />
          ) : tab === "code" ? (
            <CodePanel diff={diff} snapshots={snapshots} fallbackFiles={fallbackFiles} />
          ) : (
            <div className="grid gap-5">
              <ReplayButton
                onRerun={() => onRerun(run.id)}
                rerunning={replaysOf(run, runs).some(isRunActive)}
              />
              <RunCompare
                run={run}
                before={runBefore(run, runs)}
                replays={replaysOf(run, runs)}
                checkNames={checkNames}
              />
            </div>
          )}
        </EvidenceDrawer>
      );
    }
    case "snapshot":
      return (
        <EvidenceDrawer title="Snapshot" subtitle={ref.id} onClose={onClose}>
          <CodePanel diff={diff} snapshots={snapshots} fallbackFiles={fallbackFiles} />
        </EvidenceDrawer>
      );
  }
}

function Missing({ what }: { what: string }) {
  return (
    <p className="text-muted-foreground text-sm">
      This {what} is cited by the assessment but is not part of its evidence bundle.
    </p>
  );
}

interface SegmentPanelProps {
  segment: SegmentView;
  disputes: DisputeView[];
  findings: FindingView[];
  me: Participant;
  onCreateDispute: RefDrawerProps["onCreateDispute"];
  onResolveDispute: RefDrawerProps["onResolveDispute"];
}

function SegmentPanel({
  segment,
  disputes,
  findings,
  me,
  onCreateDispute,
  onResolveDispute,
}: SegmentPanelProps) {
  const [flagging, setFlagging] = useState(false);
  const own = disputes.filter((dispute) => dispute.segment_id === segment.id);
  return (
    <div className="grid gap-4">
      <TranscriptSegment
        segment={segment}
        onFlag={() => setFlagging((open) => !open)}
        flagOpen={flagging}
      />
      {flagging ? (
        <DisputeForm
          segment={segment}
          onSubmit={async (text, reason) => {
            await onCreateDispute(segment.id, text, reason);
            setFlagging(false);
          }}
          onCancel={() => setFlagging(false)}
        />
      ) : null}
      <section className="grid gap-2">
        <h3 className="text-sm font-semibold tracking-wide uppercase">
          Corrections on this segment
        </h3>
        <DisputeList
          disputes={own}
          findings={findings}
          me={me}
          onResolve={onResolveDispute}
          emptyText="No corrections have been filed for this segment."
        />
      </section>
    </div>
  );
}

function ClaimPanel({ claim }: { claim: ClaimView }) {
  return (
    <section className="border-border grid gap-3 rounded-lg border p-4">
      <p className="text-base">{claim.statement}</p>
      <p className="text-muted-foreground text-xs">
        A statement is the model&rsquo;s reading of the segment below, not a quotation from it.
      </p>
      <dl className="text-muted-foreground grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono text-xs">
        <dt>Type</dt>
        <dd>{CLAIM_TYPE_LABELS[claim.claim_type]}</dd>
        <dt>Scope</dt>
        <dd>{claim.scope.replace(/_/g, " ")}</dd>
        <dt>Stage</dt>
        <dd>{STAGE_LABELS[claim.stage]}</dd>
        <dt>Clarity</dt>
        <dd>{claim.clarity}</dd>
        <dt>Status</dt>
        <dd>{claim.interpretation_status.replace(/_/g, " ")}</dd>
        <dt>Recorded</dt>
        <dd>{formatTime(claim.created_at)}</dd>
      </dl>
    </section>
  );
}

interface CodePanelProps {
  diff: DiffTarget | null;
  snapshots: SnapshotsState;
  fallbackFiles: FileMap | null;
}

function CodePanel({ diff, snapshots, fallbackFiles }: CodePanelProps) {
  if (!diff) {
    return (
      <p className="text-muted-foreground text-sm">No saved code is attached to this reference.</p>
    );
  }
  if (snapshots.error) return <ErrorText>{snapshots.error}</ErrorText>;

  const modified = snapshots.byId[diff.modifiedId];
  const original = diff.originalId ? snapshots.byId[diff.originalId] : null;
  if (!modified || (diff.originalId && !original)) {
    return (
      <p role="status" className="text-muted-foreground text-sm">
        Loading the saved code…
      </p>
    );
  }

  const originalSide: DiffSide | null = original
    ? side(original)
    : fallbackFiles
      ? {
          key: "scenario",
          label: "Scenario files as given (no earlier snapshot)",
          files: fallbackFiles,
        }
      : null;
  if (!originalSide) {
    return (
      <ErrorText>
        The scenario&rsquo;s original files could not be loaded, so there is nothing to compare
        this snapshot with.
      </ErrorText>
    );
  }
  return (
    <DiffView
      key={`${diff.originalId ?? "scenario"}:${diff.modifiedId}`}
      original={originalSide}
      modified={side(modified)}
    />
  );
}

function side(snapshot: SnapshotView): DiffSide {
  return {
    key: snapshot.id,
    label: `${snapshot.id} · ${shortHash(snapshot.content_hash)} · ${formatTime(snapshot.created_at)}`,
    files: snapshot.files,
  };
}
