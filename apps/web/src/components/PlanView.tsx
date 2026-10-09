"use client";

import { useMemo } from "react";
import type { PlanData, PlanElement, PlanGeometry } from "@/lib/api";

type Pt = [number, number];

function corners(g: PlanGeometry | null): Pt[] | null {
  const fp = g?.footprint, loc = g?.location;
  if (!g || !fp || !loc) return null;
  const r = ((g.rotation_deg ?? 0) * Math.PI) / 180, cos = Math.cos(r), sin = Math.sin(r);
  const local: Pt[] = [[fp.x0, fp.y0], [fp.x1, fp.y0], [fp.x1, fp.y1], [fp.x0, fp.y1]];
  return local.map(([x, y]) => [loc[0] + x * cos - y * sin, loc[1] + x * sin + y * cos]);
}

const point = (g: PlanGeometry | null): Pt | null => (g?.location ? [g.location[0], g.location[1]] : null);

export function PlanView({ plan, selected, onSelect }: { plan: PlanData; selected: string; onSelect: (tag: string) => void }) {
  const view = useMemo(() => {
    const all: PlanElement[] = [...plan.context, ...plan.changed];
    const pts: Pt[] = [];
    for (const e of all) for (const g of [e.old, e.new]) {
      const c = corners(g);
      if (c) pts.push(...c); else { const p = point(g); if (p) pts.push(p); }
    }
    if (pts.length === 0) return null;
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const span = Math.max(maxX - minX, maxY - minY, 1), pad = span * 0.04;
    return { minX: minX - pad, maxY: maxY + pad, w: maxX - minX + 2 * pad, h: maxY - minY + 2 * pad, span };
  }, [plan]);

  if (!view) {
    return <p className="rounded border border-dashed border-line bg-white p-6 text-sm text-muted">
      No plan geometry is available for this comparison. The model elements have no location data.</p>;
  }

  const X = (x: number) => (x - view.minX).toFixed(1), Y = (y: number) => (view.maxY - y).toFixed(1);
  const path = (c: Pt[]) => "M" + c.map(([x, y]) => `${X(x)},${Y(y)}`).join(" L") + " Z";
  const fontSize = view.span / 55;

  function shape(e: PlanElement, g: PlanGeometry | null, kind: "context" | "old" | "new", key: string) {
    const c = corners(g), p = point(g);
    const isSel = selected !== "" && e.tag === selected;
    const style =
      kind === "context" ? { fill: "#E9EDF1", stroke: "#AEB7C1", dash: undefined }
      : kind === "old" ? { fill: "none", stroke: e.status === "removed" ? "#B3372F" : "#7A8591", dash: "6 4" }
      : e.status === "added" ? { fill: "#2E7D4F55", stroke: "#2E7D4F", dash: undefined }
      : { fill: "#C2571A55", stroke: "#C2571A", dash: undefined };
    const common = { fill: style.fill, stroke: style.stroke, strokeWidth: isSel ? 3 : 1.5, strokeDasharray: style.dash,
                     vectorEffect: "non-scaling-stroke" as const, style: { cursor: "pointer" }, onClick: () => onSelect(e.tag) };
    if (c) return <path key={key} d={path(c)} {...common}><title>{`${e.tag} ${e.name}`}</title></path>;
    if (p) {
      const isRoom = e.ifc_class === "IfcSpace";
      return (
        <g key={key} onClick={() => onSelect(e.tag)} style={{ cursor: "pointer" }}>
          {isRoom && kind === "context" ? null : <circle cx={X(p[0])} cy={Y(p[1])} r={fontSize * 0.45} {...common} />}
          {isRoom && kind !== "old" && <text x={X(p[0]) } y={Y(p[1])} dx={fontSize * 0.7} dy={-fontSize * 0.5}
                 fontSize={fontSize} fill={e.status === "unchanged" ? "#7A8591" : "#1B2430"}>{e.tag}</text>}
          <title>{`${e.tag} ${e.name}`}</title>
        </g>
      );
    }
    return null;
  }

  return (
    <figure>
      <svg viewBox={`0 0 ${view.w.toFixed(0)} ${view.h.toFixed(0)}`} className="max-h-[28rem] w-full rounded border border-line bg-white"
           role="img" aria-label="Plan view of changed elements, old position dashed and new position solid">
        {plan.context.map((e) => shape(e, e.new, "context", `c-${e.guid}`))}
        {plan.changed.filter((e) => e.old).map((e) => shape(e, e.old, "old", `o-${e.guid}`))}
        {plan.changed.filter((e) => e.new).map((e) => shape(e, e.new, "new", `n-${e.guid}`))}
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-4 text-xs text-muted">
        <span><i className="mr-1 inline-block h-2.5 w-4 border border-[#AEB7C1] bg-[#E9EDF1] align-middle" />Unchanged</span>
        <span><i className="mr-1 inline-block h-2.5 w-4 border border-dashed border-[#7A8591] align-middle" />Old position</span>
        <span><i className="mr-1 inline-block h-2.5 w-4 border border-status-stale bg-status-stale/30 align-middle" />Modified (new)</span>
        <span><i className="mr-1 inline-block h-2.5 w-4 border border-status-ok bg-status-ok/30 align-middle" />Added</span>
        <span><i className="mr-1 inline-block h-2.5 w-4 border border-dashed border-status-critical align-middle" />Removed</span>
        <span>Simplified plan from model location and body extent. Click an element to filter the table.</span>
      </figcaption>
    </figure>
  );
}
