"use client";

import { useMemo } from "react";
import type { Discipline, GraphData } from "@/lib/api";
import { DISCIPLINES, RELATIONSHIPS } from "@/lib/labels";

const COLUMN_W = 230, NODE_W = 150, NODE_H = 46, ROW_H = 72, TOP = 44, LEFT = 24;
const ORDER: Discipline[] = ["architecture", "structure", "mep", "equipment", "quantity", "general"];
const STEEL = "#2F5D8A", STALE = "#C2571A", INK = "#1B2430", LINE = "#AEB7C1";

export function GraphView({ graph, selected, impacted, onSelect }: {
  graph: GraphData; selected: string | null; impacted: Set<string>; onSelect: (id: string) => void;
}) {
  const layout = useMemo(() => {
    const columns = ORDER.filter((d) => graph.nodes.some((n) => n.discipline === d));
    const pos = new Map<string, { x: number; y: number; col: number }>();
    let rows = 1;
    columns.forEach((d, col) => {
      const inColumn = graph.nodes.filter((n) => n.discipline === d);
      rows = Math.max(rows, inColumn.length);
      inColumn.forEach((n, row) => pos.set(n.id, { x: LEFT + col * COLUMN_W, y: TOP + row * ROW_H, col }));
    });
    return { columns, pos, width: LEFT * 2 + columns.length * COLUMN_W - (COLUMN_W - NODE_W), height: TOP + rows * ROW_H };
  }, [graph.nodes]);

  const staleConsumers = new Set(graph.edges.filter((e) => e.is_stale).map((e) =>
    e.flow === "target_to_source" ? e.source_document_id : e.target_document_id));

  function edgePath(sourceId: string, targetId: string, providerId: string | null): string | null {
    const a = layout.pos.get(sourceId), b = layout.pos.get(targetId);
    if (!a || !b) return null;
    // draw from provider to consumer so arrows point the way a change travels
    const [from, to] = providerId === targetId ? [b, a] : [a, b];
    if (from.col === to.col) {
      const x = from.x + NODE_W, y1 = from.y + NODE_H / 2, y2 = to.y + NODE_H / 2;
      return `M${x},${y1} C${x + 70},${y1} ${x + 70},${y2} ${x},${y2}`;
    }
    const forward = to.col > from.col;
    const x1 = forward ? from.x + NODE_W : from.x, x2 = forward ? to.x : to.x + NODE_W;
    const y1 = from.y + NODE_H / 2, y2 = to.y + NODE_H / 2, dx = Math.abs(x2 - x1) / 2;
    return `M${x1},${y1} C${x1 + (forward ? dx : -dx)},${y1} ${x2 - (forward ? dx : -dx)},${y2} ${x2},${y2}`;
  }

  if (graph.nodes.length === 0) return null;
  return (
    <div className="overflow-x-auto rounded border border-line bg-white">
      <svg width={layout.width} height={layout.height} role="group" aria-label="Document dependency graph"
           className="min-w-full">
        <defs>
          {[["a", STEEL], ["s", STALE]].map(([id, color]) => (
            <marker key={id} id={`arrow-${id}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0,0 L10,5 L0,10 z" fill={color} />
            </marker>
          ))}
        </defs>
        {layout.columns.map((d, col) => (
          <text key={d} x={LEFT + col * COLUMN_W} y={24} fontSize={12} fill="#5C6773" fontWeight={600}>
            {DISCIPLINES[d].toUpperCase()}</text>
        ))}
        {graph.edges.map((e) => {
          const d = edgePath(e.source_document_id, e.target_document_id, e.provider_document_id);
          if (!d) return null;
          const both = e.flow === "both", color = e.is_stale ? STALE : STEEL;
          const rel = RELATIONSHIPS[e.relationship_type];
          return (
            <path key={e.id} d={d} fill="none" stroke={color} strokeWidth={1 + e.strength * 2} opacity={0.85}
                  strokeDasharray={both ? "5 4" : undefined}
                  markerEnd={both ? undefined : `url(#arrow-${e.is_stale ? "s" : "a"})`}>
              <title>{`${rel.phrase(e.source_number, e.target_number)} (${Math.round(e.confidence * 100)}% confidence)${e.is_stale ? " - STALE" : ""}`}</title>
            </path>
          );
        })}
        {graph.nodes.map((n) => {
          const p = layout.pos.get(n.id)!;
          const isSel = n.id === selected, isImpacted = impacted.has(n.id), isStale = staleConsumers.has(n.id);
          return (
            <g key={n.id} transform={`translate(${p.x},${p.y})`} tabIndex={0} role="button"
               aria-label={`${n.document_number} ${n.name}${isStale ? ", has stale dependencies" : ""}`}
               aria-pressed={isSel} style={{ cursor: "pointer" }} onClick={() => onSelect(n.id)}
               onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(n.id); } }}>
              <rect width={NODE_W} height={NODE_H} rx={4} fill={isImpacted ? "#FBE9DD" : isSel ? "#E6EEF5" : "#fff"}
                    stroke={isStale ? STALE : isSel ? STEEL : LINE} strokeWidth={isSel || isStale ? 2.5 : 1.5} />
              <text x={10} y={20} fontSize={14} fontFamily="var(--font-mono), monospace" fill={INK} fontWeight={500}>
                {n.document_number}</text>
              <text x={10} y={37} fontSize={11} fill="#5C6773">
                {n.current_revision_number ? `v${n.current_revision_number}` : "no revision"}{isStale ? " · stale input" : ""}</text>
              <title>{`${n.document_number} ${n.name}`}</title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
