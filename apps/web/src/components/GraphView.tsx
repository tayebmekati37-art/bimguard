"use client";

import { useMemo } from "react";
import { useT } from "@/lib/i18n";
import type { Discipline, GraphData } from "@/lib/api";
import { HEALTH, HEALTH_ORDER, RELATIONSHIPS } from "@/lib/labels";

const COLUMN_W = 230, NODE_W = 150, NODE_H = 46, ROW_H = 72, TOP = 44, LEFT = 24;
const ORDER: Discipline[] = ["architecture", "structure", "mep", "equipment", "quantity", "general"];
const STEEL = "#2F5D8A", STALE = "#C2571A", INK = "#1B2430";

export function GraphLegend() {
  const { t } = useT();
  return (
    <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted" aria-label={t("graph.legendAria")}>
      {HEALTH_ORDER.slice().reverse().map((s) => (
        <li key={s} className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-3 w-3 rounded-sm border-2 bg-white" style={{ borderColor: HEALTH[s].hex }} />
          <span>
            <strong className="font-medium text-ink">{t(`health.${s}`)}</strong>: {t(`health.${s}.text`)}
          </span>
        </li>
      ))}
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="inline-block h-3 w-3 rounded-sm" style={{ background: "#FBE9DD" }} />
        {" "}{t("graph.legendReached")}
      </li>
    </ul>
  );
}

export function GraphView({ graph, selected, reached, onSelect }: {
  graph: GraphData; selected: string | null; reached: Set<string>; onSelect: (id: string) => void;
}) {
  const { t } = useT();
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

  function edgePath(sourceId: string, targetId: string, providerId: string | null): string | null {
    const a = layout.pos.get(sourceId), b = layout.pos.get(targetId);
    if (!a || !b) return null;
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
      <svg width={layout.width} height={layout.height} role="group" aria-label={t("graph.diagramAria")} className="min-w-full">
        <defs>
          {[["a", STEEL], ["s", STALE]].map(([id, color]) => (
            <marker key={id} id={`arrow-${id}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0,0 L10,5 L0,10 z" fill={color} />
            </marker>
          ))}
        </defs>
        {layout.columns.map((d, col) => (
          <text key={d} x={LEFT + col * COLUMN_W} y={24} fontSize={12} fill="#5C6773" fontWeight={600}>
            {t(`discipline.${d}`).toUpperCase()}
          </text>
        ))}
        {graph.edges.map((e) => {
          const d = edgePath(e.source_document_id, e.target_document_id, e.provider_document_id);
          if (!d) return null;
          const both = e.flow === "both", color = e.is_stale ? STALE : STEEL;
          const rel = RELATIONSHIPS[e.relationship_type];
          return (
            <path key={e.id} d={d} fill="none" stroke={color} strokeWidth={1 + e.strength * 2} opacity={0.85}
                  strokeDasharray={both ? "5 4" : undefined} markerEnd={both ? undefined : `url(#arrow-${e.is_stale ? "s" : "a"})`}>
              <title>{`${rel.phrase(e.source_number, e.target_number)} (${Math.round(e.confidence * 100)}% confidence)${e.is_stale ? " - STALE" : ""}`}</title>
            </path>
          );
        })}
        {graph.nodes.map((n) => {
          const p = layout.pos.get(n.id)!;
          const isSel = n.id === selected, isReached = reached.has(n.id), health = HEALTH[n.health];
          const healthLabel = t(`health.${n.health}`);
          return (
            <g key={n.id} transform={`translate(${p.x},${p.y})`} tabIndex={0} role="button"
               aria-label={`${n.document_number} ${n.name}: ${healthLabel}${n.health_reasons.length ? `. ${n.health_reasons.join(". ")}` : ""}`}
               aria-pressed={isSel} style={{ cursor: "pointer" }} onClick={() => onSelect(n.id)}
               onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(n.id); } }}>
              <rect width={NODE_W} height={NODE_H} rx={4} fill={isReached ? "#FBE9DD" : isSel ? "#E6EEF5" : "#fff"}
                    stroke={health.hex} strokeWidth={isSel ? 3.5 : n.health === "healthy" ? 1.5 : 2.5}
                    style={{ transition: "fill 0.4s ease" }} />
              <text x={10} y={20} fontSize={14} fontFamily="var(--font-mono), monospace" fill={INK} fontWeight={500}>
                {n.document_number}
              </text>
              <text x={10} y={37} fontSize={11} fill="#5C6773">
                {n.current_revision_number ? `v${n.current_revision_number}` : t("graph.noRevision")}
                {n.health !== "healthy" ? ` · ${healthLabel}` : ""}
              </text>
              <title>{`${n.document_number} ${n.name}`}</title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}