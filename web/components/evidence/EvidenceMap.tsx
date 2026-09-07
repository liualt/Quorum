"use client";

import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ChatText, Code, GitDiff, Lightbulb, Target } from "@phosphor-icons/react/ssr";
import { createContext, useContext, useMemo, type ComponentType } from "react";

import { AIBadge } from "@/components/ui/AIBadge";
import { Button } from "@/components/ui/Button";
import type { AssessmentEvidence, FindingView, Ref, Relation } from "@/lib/types";

import {
  COLUMN_LABELS,
  buildEvidenceGraph,
  type DrawerTab,
  type EvidenceColumn,
  type EvidenceNode,
} from "./evidenceGraph";
import { LevelChip, ReviewChip } from "./FindingParts";
import { RELATION_LABELS } from "./labels";

type OpenRef = (ref: Ref, tab: DrawerTab) => void;

/*
 * The node cards get their click handler from context rather than from node
 * data, so the graph builder stays a pure function of the assessment.
 */
const OpenRefContext = createContext<OpenRef>(() => {});

const COLUMN_ICONS: Record<
  EvidenceColumn,
  ComponentType<{ size?: number; "aria-hidden"?: boolean }>
> = {
  statement: ChatText,
  challenge: Lightbulb,
  code: Code,
  revision: GitDiff,
  finding: Target,
};

/* Both ends carry a handle on each side, so an edge that runs right-to-left
   can leave from the left and land on the right (see `evidenceGraph.edge`). */
const HANDLE_STYLE = {
  width: 8,
  height: 8,
  background: "var(--color-border-strong)",
  border: "none",
};

function EvidenceNodeCard({ data }: NodeProps<EvidenceNode>) {
  const open = useContext(OpenRefContext);
  const Icon = COLUMN_ICONS[data.column];
  const { ref, action } = data;
  return (
    /*
     * React Flow gives a node that is neither selectable nor draggable
     * `pointer-events: none`; the card turns them back on so its button is
     * clickable.
     */
    <div
      className="border-border-strong bg-card text-card-foreground pointer-events-auto grid w-60
        gap-2 rounded-lg border p-3 shadow-md"
    >
      <Handle type="target" position={Position.Left} id="tgt-l" style={HANDLE_STYLE} />
      <Handle type="target" position={Position.Right} id="tgt-r" style={HANDLE_STYLE} />
      <Handle type="source" position={Position.Left} id="src-l" style={HANDLE_STYLE} />
      <Handle type="source" position={Position.Right} id="src-r" style={HANDLE_STYLE} />

      <p className="text-muted-foreground flex items-center gap-1.5 font-mono text-xs tracking-wide uppercase">
        <Icon size={14} aria-hidden />
        {COLUMN_LABELS[data.column]}
      </p>
      <p className="flex min-w-0 items-center gap-1.5 text-sm font-semibold">
        {data.ai ? <AIBadge /> : null}
        <span className="truncate">{data.heading}</span>
      </p>
      <p className="line-clamp-3 text-xs">{data.body}</p>
      {data.level ? (
        <div className="flex flex-wrap gap-1.5">
          <LevelChip level={data.level} />
          {data.needsReview ? <ReviewChip /> : null}
        </div>
      ) : (
        <p className="text-muted-foreground font-mono text-xs">{data.meta}</p>
      )}
      {action && ref ? (
        <Button
          variant="secondary"
          className="nodrag w-full"
          onClick={() => open(ref, action.tab)}
        >
          {action.label}
        </Button>
      ) : null}
    </div>
  );
}

const nodeTypes: NodeTypes = {
  statement: EvidenceNodeCard,
  challenge: EvidenceNodeCard,
  code: EvidenceNodeCard,
  revision: EvidenceNodeCard,
  finding: EvidenceNodeCard,
};

interface EvidenceMapProps {
  finding: FindingView;
  evidence: AssessmentEvidence;
  onOpen: OpenRef;
}

/**
 * The selected finding's evidence path in fixed columns.
 *
 * Nothing here is draggable, connectable or selectable: the map is a reading
 * surface whose only controls are the real buttons on the cards and the zoom
 * controls. Wheel events scroll the page, not the canvas.
 */
export function EvidenceMap({ finding, evidence, onOpen }: EvidenceMapProps) {
  const { nodes, edges, missing } = useMemo(
    () => buildEvidenceGraph(finding, evidence),
    [finding, evidence],
  );

  return (
    <div className="grid gap-3">
      <div className="border-border bg-background h-[420px] overflow-hidden rounded-lg border">
        <OpenRefContext.Provider value={onOpen}>
          <ReactFlow
            key={finding.id}
            aria-label={`Evidence map for ${finding.title || "the selected finding"}`}
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            colorMode="dark"
            fitView
            fitViewOptions={{ padding: 0.15, maxZoom: 1 }}
            minZoom={0.2}
            maxZoom={1.5}
            nodesDraggable={false}
            nodesConnectable={false}
            nodesFocusable={false}
            edgesFocusable={false}
            elementsSelectable={false}
            zoomOnScroll={false}
            panOnScroll={false}
            zoomOnDoubleClick={false}
            preventScrolling={false}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={24} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </OpenRefContext.Provider>
      </div>

      <Legend />

      {missing.length > 0 ? (
        <p className="text-muted-foreground text-xs" role="status">
          {missing.length === 1
            ? "One reference could not be loaded and is not on the map."
            : `${missing.length} references could not be loaded and are not on the map.`}
        </p>
      ) : null}
    </div>
  );
}

const LEGEND: Array<{ relation: Relation; dash?: string; color: string }> = [
  { relation: "supports", color: "var(--color-accent)" },
  { relation: "challenges", dash: "6 4", color: "var(--color-destructive)" },
  { relation: "revises", dash: "2 4", color: "var(--color-foreground)" },
];

function Legend() {
  return (
    <div className="text-muted-foreground flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
      <ul className="flex flex-wrap gap-x-5 gap-y-2" aria-label="Edge styles">
        {LEGEND.map(({ relation, dash, color }) => (
          <li key={relation} className="flex items-center gap-2">
            <svg width="40" height="8" aria-hidden className="shrink-0">
              <line
                x1="0"
                y1="4"
                x2="40"
                y2="4"
                stroke={color}
                strokeWidth="2"
                strokeDasharray={dash}
              />
            </svg>
            <span className="font-mono">{RELATION_LABELS[relation]}</span>
          </li>
        ))}
      </ul>
      <p>
        Links are recorded relationships between records. They do not show causation or
        the candidate&rsquo;s reasoning.
      </p>
    </div>
  );
}
