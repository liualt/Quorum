/**
 * The evidence map as data: which column each of a finding's references sits
 * in, and which recorded links join them.
 *
 * This is a pure function of the `AssessmentView`, kept apart from React Flow
 * so the layout rules can be read (and changed) without the rendering. The
 * columns follow PRD section 5 — Statement → Challenge → Code and result →
 * Revision → Finding — with fixed positions, never a physics layout.
 */

import { MarkerType, type Edge, type Node } from "@xyflow/react";

import type {
  AssessmentEvidence,
  FindingView,
  LinkView,
  ObservationLevel,
  Ref,
  RefType,
  Relation,
} from "@/lib/types";

import {
  CLAIM_TYPE_LABELS,
  KIND_LABELS,
  LEVEL_LABELS,
  RELATION_LABELS,
  formatTime,
  isAISpeaker,
  runOutcome,
  shortHash,
  speakerLabel,
} from "./labels";

export type EvidenceColumn = "statement" | "challenge" | "code" | "revision" | "finding";

/** Which drawer tab a node's button opens. */
export type DrawerTab = "transcript" | "code" | "results";

export const COLUMNS: readonly EvidenceColumn[] = [
  "statement",
  "challenge",
  "code",
  "revision",
  "finding",
];

export const COLUMN_LABELS: Record<EvidenceColumn, string> = {
  statement: "Statement",
  challenge: "Challenge",
  code: "Code and result",
  revision: "Revision",
  finding: "Finding",
};

export const COLUMN_X: Record<EvidenceColumn, number> = {
  statement: 0,
  challenge: 280,
  code: 560,
  revision: 840,
  finding: 1120,
};

export const NODE_WIDTH = 240;
/* A card is a column label, a heading, three lines of text, a meta line and a
   44 px button, with 12 px padding: about 200 px. The row leaves a gap. */
export const ROW_HEIGHT = 230;

export interface EvidenceNodeData extends Record<string, unknown> {
  column: EvidenceColumn;
  /** Null on the finding node, which is the thing being explained. */
  ref: Ref | null;
  heading: string;
  /** The record is an AI utterance; the card shows the disclosure badge. */
  ai: boolean;
  body: string;
  meta: string;
  /** The card's one button. Null on the finding node. */
  action: { label: string; tab: DrawerTab } | null;
  level: ObservationLevel | null;
  needsReview: boolean;
}

export type EvidenceNode = Node<EvidenceNodeData, EvidenceColumn>;

export interface EvidenceEdgeData extends Record<string, unknown> {
  relation: Relation;
}

export type EvidenceEdge = Edge<EvidenceEdgeData>;

export interface EvidenceGraph {
  nodes: EvidenceNode[];
  edges: EvidenceEdge[];
  /** References the evidence bundle did not carry a record for. */
  missing: Ref[];
}

/*
 * Line style is what distinguishes the relations; colour only reinforces it.
 * The label is on every edge as well, so the relation is readable three ways.
 */
const EDGE_COLOR: Record<Relation, string> = {
  supports: "var(--color-accent)",
  challenges: "var(--color-destructive)",
  revises: "var(--color-foreground)",
};

const EDGE_DASH: Record<Relation, string | undefined> = {
  supports: undefined,
  challenges: "6 4",
  revises: "2 4",
};

export const DEFAULT_TAB: Record<RefType, DrawerTab> = {
  segment: "transcript",
  claim: "transcript",
  run: "results",
  snapshot: "code",
};

export function nodeId(ref: Ref): string {
  return `${ref.type}:${ref.id}`;
}

interface Placed {
  data: EvidenceNodeData;
  /** Sort key within the column: when the record was made. */
  order: number;
}

export function buildEvidenceGraph(
  finding: FindingView,
  evidence: AssessmentEvidence,
): EvidenceGraph {
  const placed = new Map<string, Placed>();
  const missing: Ref[] = [];

  for (const ref of [...finding.supporting_refs, ...finding.opposing_refs]) {
    const id = nodeId(ref);
    if (placed.has(id)) continue;
    const entry = placeRef(ref, evidence);
    if (entry) placed.set(id, entry);
    else missing.push(ref);
  }

  const nodes: EvidenceNode[] = [];
  let tallest = 1;
  for (const column of COLUMNS) {
    if (column === "finding") continue;
    const rows = [...placed.entries()]
      .filter(([, entry]) => entry.data.column === column)
      .sort(([, a], [, b]) => a.order - b.order);
    tallest = Math.max(tallest, rows.length);
    rows.forEach(([id, entry], row) => {
      nodes.push(node(id, column, row * ROW_HEIGHT, entry.data));
    });
  }

  const findingNodeId = `finding:${finding.id}`;
  nodes.push(
    node(findingNodeId, "finding", ((tallest - 1) / 2) * ROW_HEIGHT, {
      column: "finding",
      ref: null,
      heading: finding.title || "Finding",
      ai: false,
      body: finding.explanation,
      meta: LEVEL_LABELS[finding.observation_level],
      action: null,
      level: finding.observation_level,
      needsReview: finding.review_status === "needs_review",
    }),
  );

  const columnOf = new Map(nodes.map((item) => [item.id, item.data.column]));
  const headingOf = new Map(nodes.map((item) => [item.id, item.data.heading]));
  const edges: EvidenceEdge[] = [];

  // The recorded links between the records on the map, direction as recorded.
  for (const link of evidence.links) {
    const source = `${link.source_type}:${link.source_id}`;
    const target = `${link.target_type}:${link.target_id}`;
    if (!columnOf.has(source) || !columnOf.has(target)) continue;
    edges.push(edge(link.id, source, target, link.relation, columnOf, headingOf));
  }

  // Each reference into the finding, by the role the assessment gave it.
  const refEdges: Array<[Ref[], Relation]> = [
    [finding.supporting_refs, "supports"],
    [finding.opposing_refs, "challenges"],
  ];
  for (const [refs, relation] of refEdges) {
    for (const ref of refs) {
      const source = nodeId(ref);
      if (!columnOf.has(source)) continue;
      edges.push(
        edge(`ref:${relation}:${source}`, source, findingNodeId, relation, columnOf, headingOf),
      );
    }
  }

  return { nodes, edges, missing };
}

function node(
  id: string,
  column: EvidenceColumn,
  y: number,
  data: EvidenceNodeData,
): EvidenceNode {
  return {
    id,
    type: column,
    position: { x: COLUMN_X[column], y },
    data,
    draggable: false,
    selectable: false,
    connectable: false,
    ariaLabel: `${COLUMN_LABELS[column]}: ${data.heading}`,
    style: { width: NODE_WIDTH },
  };
}

function edge(
  id: string,
  source: string,
  target: string,
  relation: Relation,
  columnOf: Map<string, EvidenceColumn>,
  headingOf: Map<string, string>,
): EvidenceEdge {
  // A link recorded from a right-hand column back to a left-hand one leaves
  // from the node's left edge, so it does not loop around the card.
  const forward =
    COLUMNS.indexOf(columnOf.get(source)!) <= COLUMNS.indexOf(columnOf.get(target)!);
  return {
    id,
    source,
    target,
    sourceHandle: forward ? "src-r" : "src-l",
    targetHandle: forward ? "tgt-l" : "tgt-r",
    data: { relation },
    label: RELATION_LABELS[relation],
    ariaLabel: `${headingOf.get(source)} ${RELATION_LABELS[relation]} ${headingOf.get(target)}`,
    markerEnd: { type: MarkerType.ArrowClosed, color: EDGE_COLOR[relation], width: 16, height: 16 },
    style: { stroke: EDGE_COLOR[relation], strokeWidth: 1.5, strokeDasharray: EDGE_DASH[relation] },
    labelStyle: { fill: "var(--color-foreground)", fontFamily: "var(--font-mono)", fontSize: 11 },
    labelBgStyle: { fill: "var(--color-card)" },
    labelBgPadding: [6, 3],
    labelBgBorderRadius: 4,
  };
}

function placeRef(ref: Ref, evidence: AssessmentEvidence): Placed | null {
  switch (ref.type) {
    case "segment": {
      const segment = evidence.segments[ref.id];
      if (!segment) return null;
      const challenge = segment.kind === "hint" || segment.kind === "scenario_notice";
      return {
        order: Date.parse(segment.created_at),
        data: {
          column: challenge ? "challenge" : "statement",
          ref,
          heading: `${speakerLabel(segment.speaker)} · ${KIND_LABELS[segment.kind]}`,
          ai: isAISpeaker(segment.speaker),
          body: segment.text,
          meta: formatTime(segment.created_at),
          action: { label: "Open transcript", tab: "transcript" },
          level: null,
          needsReview: false,
        },
      };
    }
    case "claim": {
      const claim = evidence.claims[ref.id];
      if (!claim) return null;
      return {
        order: Date.parse(claim.created_at),
        data: {
          column: isSourceOf(evidence.links, "claim", claim.id, "revises") ? "revision" : "statement",
          ref,
          heading: CLAIM_TYPE_LABELS[claim.claim_type],
          ai: false,
          body: claim.statement,
          meta: `${claim.scope.replace(/_/g, " ")} · ${claim.clarity}`,
          action: { label: "Open statement", tab: "transcript" },
          level: null,
          needsReview: false,
        },
      };
    }
    case "run": {
      const run = evidence.runs[ref.id];
      if (!run) return null;
      return {
        order: Date.parse(run.created_at),
        data: {
          column: isSourceOf(evidence.links, "run", run.id, "challenges") ? "challenge" : "code",
          ref,
          heading: "Run",
          ai: false,
          body: `${runOutcome(run)} · ${run.check_ids.length} checks on snapshot ${run.snapshot_id}`,
          meta: formatTime(run.finished_at ?? run.created_at),
          action: { label: "Open results", tab: "results" },
          level: null,
          needsReview: false,
        },
      };
    }
    case "snapshot": {
      const snapshot = evidence.snapshots[ref.id];
      if (!snapshot) return null;
      return {
        order: Date.parse(snapshot.created_at),
        data: {
          column: "code",
          ref,
          heading: "Snapshot",
          ai: false,
          body: `Saved code ${shortHash(snapshot.content_hash)}`,
          meta: formatTime(snapshot.created_at),
          action: { label: "Open code", tab: "code" },
          level: null,
          needsReview: false,
        },
      };
    }
  }
}

function isSourceOf(
  links: LinkView[],
  type: RefType,
  id: string,
  relation: Relation,
): boolean {
  return links.some(
    (link) =>
      link.relation === relation && link.source_type === type && link.source_id === id,
  );
}
