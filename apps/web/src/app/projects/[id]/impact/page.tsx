"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Fragment, useCallback, useEffect, useState } from "react";
import { AppShell, useUser } from "@/components/AppShell";
import { ErrorNote, Pager, SeverityBadge, btnPrimary, btnSecondary } from "@/components/ui";
import {
  getProject, getProjectImpact, runImpactAnalysis, validateDependency, type ImpactEvent, type Project, type ProjectImpact,
} from "@/lib/api";
import { DISCIPLINES, RELATIONSHIPS, SEVERITIES, can, formatDate } from "@/lib/labels";

const PAGE_SIZE = 25;
const BAR: Record<string, string> = { CRITICAL: "bg-status-critical", HIGH: "bg-status-stale", MEDIUM: "bg-status-warn", LOW: "bg-muted" };
const KIND: Record<string, string> = {
  counterpart: "Same element", references: "Based on changed element", proximity: "Near changed element", same_room: "Same room",
};

function StateBadge({ state }: { state: ImpactEvent["state"] }) {
  const tone = state === "open" ? "border-status-stale text-status-stale" : state === "reviewed" ? "border-status-ok text-status-ok" : "border-line text-muted";
  const label = state === "open" ? "Open" : state === "reviewed" ? "Reviewed" : "Advisory";
  return <span className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${tone}`}>{label}</span>;
}

function ScoreBar({ score, severity }: { score: number; severity: string }) {
  return (
    <div className="flex items-center gap-2" title={`Impact score ${score} of 100`}>
      <div className="h-2 w-20 rounded bg-line" aria-hidden><div className={`h-2 rounded ${BAR[severity] ?? "bg-muted"}`} style={{ width: `${Math.min(100, score)}%` }} /></div>
      <span className="w-10 font-mono text-sm">{score.toFixed(1)}</span>
    </div>
  );
}

function Detail({ e, canReview, busy, onReview }: { e: ImpactEvent; canReview: boolean; busy: boolean; onReview: () => void }) {
  return (
    <div className="grid gap-6 bg-paper px-4 py-4 text-sm lg:grid-cols-2">
      <div>
        <p className="font-medium">Why this document is affected</p>
        <p className="mt-1">{e.reason}</p>
        <p className="mt-4 font-medium">Path</p>
        <ol className="mt-1 space-y-1 text-xs">
          {e.path.map((s) => (
            <li key={s.edge_id}><span className="font-mono">{s.from_number}</span> to <span className="font-mono">{s.to_number}</span>{" "}
              <span className="text-muted">({RELATIONSHIPS[s.relationship_type].label.toLowerCase()}, {Math.round(s.strength * 100)}% strength{s.reason ? `: ${s.reason}` : ""})</span></li>
          ))}
        </ol>
        {e.state === "open" && e.direct && canReview && (
          <button className={`${btnPrimary} mt-4`} disabled={busy} onClick={onReview}>
            Mark reviewed against {e.changed_document_number} v{e.changed_revision_number}</button>
        )}
        {e.state === "open" && !e.direct && <p className="mt-4 text-xs text-muted">Reached through {e.path[0].to_number}. It is resolved once {e.path[0].to_number} has been reviewed against {e.changed_document_number} v{e.changed_revision_number}.</p>}
        {e.state === "reviewed" && <p className="mt-4 text-xs text-status-ok">Reviewed against v{e.dependency_validated_against}{e.validated_by_name ? ` by ${e.validated_by_name}` : ""}{e.validated_at ? `, ${formatDate(e.validated_at)}` : ""}.</p>}
        {e.state === "advisory" && <p className="mt-4 text-xs text-muted">This path starts with a two-way relationship, which cannot be reviewed. It is shown for information.</p>}
      </div>

      <div>
        <p className="font-medium">Why this score</p>
        <p className="mt-1 font-mono text-xs">{e.formula}</p>
        <table className="mt-2 w-full text-xs">
          <tbody>
            {e.factors.map((f) => (
              <tr key={f.key} className="border-b border-line align-top last:border-0">
                <td className="w-28 py-1.5 pr-2 font-medium">{f.label}</td>
                <td className="w-14 py-1.5 font-mono">{f.value.toFixed(2)}</td>
                <td className="py-1.5 text-muted">{f.explanation}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-muted">Confidence {Math.round(e.confidence * 100)}%: the weakest relationship, the strength of the change evidence, and one step of doubt per extra hop.</p>
      </div>

      <div className="lg:col-span-2">
        <p className="font-medium">Elements in {e.impacted_document_number} that may be affected {e.affected_element_count > 0 && <span className="font-normal text-muted">({e.affected_element_count})</span>}</p>
        {e.note && <p className="mt-1 text-xs text-muted">{e.note}</p>}
        {!e.note && e.affected_elements.length === 0 && <p className="mt-1 text-xs text-muted">No element in this document is linked to a changed element by reference, proximity, shared room or identity.</p>}
        {e.affected_elements.length > 0 && (
          <table className="mt-2 w-full text-xs">
            <thead className="border-b border-line text-left text-muted"><tr><th className="py-1 font-medium">Element</th><th className="font-medium">Link</th><th className="font-medium">Why</th></tr></thead>
            <tbody>
              {e.affected_elements.map((a) => (
                <tr key={a.guid} className="border-b border-line align-top last:border-0">
                  <td className="py-1.5"><span className="font-mono">{a.tag}</span><div className="text-muted">{a.ifc_class.replace(/^Ifc/, "")}{a.room ? `, room ${a.room}` : ""}</div></td>
                  <td className="py-1.5">{a.kinds.map((k) => KIND[k] ?? k).join(", ")}</td>
                  <td className="py-1.5">{a.reasons.map((r) => <div key={r}>{r}</div>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function ImpactView() {
  const { id } = useParams<{ id: string }>();
  const user = useUser();
  const [project, setProject] = useState<Project | null>(null);
  const [data, setData] = useState<ProjectImpact | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [severity, setSeverity] = useState("");
  const [state, setState] = useState("");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    Promise.all([getProject(id), getProjectImpact(id, { severity, state, limit: PAGE_SIZE, offset })])
      .then(([p, d]) => { setProject(p); setData(d); setError(null); }).catch((e) => setError(e.message));
  }, [id, severity, state, offset]);
  useEffect(load, [load]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await fn(); load(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  if (error && !data) return <><Link href={`/projects/${id}`} className="text-sm text-steel hover:underline">Back to project</Link><ErrorNote message={error} /></>;
  if (!data || !project) return <p className="text-muted">Loading</p>;

  const { counts } = data;
  const canRun = can.compare(user.role) && project.status === "active";
  return (
    <>
      <Link href={`/projects/${id}`} className="text-sm text-steel hover:underline">Back to {project.name}</Link>
      <div className="mt-3 flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-semibold">Impact analysis</h1>
          <p className="mt-1 text-sm text-muted">What the latest revisions could affect in other documents, scored from the detected changes and the dependency graph.</p>
        </div>
        {canRun && <button className={btnSecondary} disabled={busy} onClick={() => act(() => runImpactAnalysis(id))}>{busy ? "Analysing" : "Re-run analysis"}</button>}
      </div>
      <ErrorNote message={error} />

      {data.analyses.length === 0 ? (
        <div className="mt-6 rounded border border-dashed border-line bg-white p-8">
          <p className="font-medium">No impact to report yet.</p>
          <p className="mt-1 text-sm text-muted">Impact is calculated when a new revision is compared with the previous one and the document has dependents. Register dependencies, then upload a new revision.</p>
        </div>
      ) : (
        <>
          <section className="mt-6 rounded border border-line bg-white p-4" aria-label="Summary">
            <div className="flex flex-wrap items-center gap-x-8 gap-y-2">
              <div><span className="text-2xl font-semibold">{counts.open}</span> <span className="text-sm text-muted">open</span></div>
              <div><span className="text-2xl font-semibold text-status-ok">{counts.reviewed}</span> <span className="text-sm text-muted">reviewed</span></div>
              {counts.advisory > 0 && <div><span className="text-2xl font-semibold text-muted">{counts.advisory}</span> <span className="text-sm text-muted">advisory</span></div>}
              <div className="flex items-center gap-2">
                {SEVERITIES.filter((s) => counts.open_by_severity[s]).map((s) => (
                  <span key={s} className="flex items-center gap-1"><SeverityBadge severity={s} /><span className="text-sm">{counts.open_by_severity[s]}</span></span>))}
              </div>
            </div>
            <ul className="mt-3 space-y-0.5 text-sm text-muted">
              {data.analyses.map((a) => (
                <li key={a.id}><span className="font-mono text-ink">{a.changed_document_number}</span> v{a.changed_revision_number}: {a.summary.changes} changes reach {a.summary.total} {a.summary.total === 1 ? "document" : "documents"}
                  {a.summary.radius ? `, up to ${a.summary.radius} ${a.summary.radius === 1 ? "step" : "steps"} away` : ""} · analysed {formatDate(a.created_at)}</li>))}
            </ul>
          </section>

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted">Severity</span>
            <button className={`${btnSecondary} ${severity === "" ? "border-steel bg-steel-light" : ""}`} onClick={() => { setSeverity(""); setOffset(0); }}>All</button>
            {SEVERITIES.map((s) => <button key={s} aria-pressed={severity === s} className={`${btnSecondary} ${severity === s ? "border-steel bg-steel-light" : ""}`}
              onClick={() => { setSeverity(severity === s ? "" : s); setOffset(0); }}>{s.charAt(0) + s.slice(1).toLowerCase()}</button>)}
            <select aria-label="State filter" className="ml-3 rounded border border-line bg-white px-3 py-1.5 text-sm" value={state} onChange={(e) => { setState(e.target.value); setOffset(0); }}>
              <option value="">Any state</option><option value="open">Open</option><option value="reviewed">Reviewed</option><option value="advisory">Advisory</option>
            </select>
          </div>

          {data.events.items.length === 0 ? <p className="mt-4 text-sm">No impacts match these filters.</p> : (
            <>
              <table className="mt-3 w-full border border-line bg-white text-sm">
                <thead className="border-b border-line bg-paper text-left text-muted">
                  <tr><th className="px-3 py-2 font-medium">Score</th><th className="px-3 font-medium">Severity</th><th className="px-3 font-medium">Document</th>
                      <th className="px-3 font-medium">Distance</th><th className="px-3 font-medium">Confidence</th><th className="px-3 font-medium">State</th></tr>
                </thead>
                <tbody>
                  {data.events.items.map((e) => (
                    <Fragment key={e.id}>
                      <tr className="cursor-pointer border-b border-line align-top hover:bg-steel-light/40" tabIndex={0} aria-expanded={open === e.id}
                          onClick={() => setOpen(open === e.id ? null : e.id)}
                          onKeyDown={(k) => { if (k.key === "Enter" || k.key === " ") { k.preventDefault(); setOpen(open === e.id ? null : e.id); } }}>
                        <td className="px-3 py-2"><ScoreBar score={e.score} severity={e.severity} /></td>
                        <td className="px-3 py-2"><SeverityBadge severity={e.severity} /></td>
                        <td className="px-3 py-2"><span className="font-mono">{e.impacted_document_number}</span>
                          <div className="text-xs text-muted">{e.impacted_name} · {DISCIPLINES[e.impacted_discipline]} · affected by {e.changed_document_number} v{e.changed_revision_number}</div></td>
                        <td className="px-3 py-2">{e.direct ? "Direct" : `${e.distance} steps`}</td>
                        <td className="px-3 py-2">{Math.round(e.confidence * 100)}%</td>
                        <td className="px-3 py-2"><StateBadge state={e.state} /></td>
                      </tr>
                      {open === e.id && <tr className="border-b border-line"><td colSpan={6}>
                        <Detail e={e} canReview={can.changeStatus(user.role) && project.status === "active"} busy={busy}
                                onReview={() => act(() => validateDependency(e.first_edge_id!))} />
                      </td></tr>}
                    </Fragment>
                  ))}
                </tbody>
              </table>
              <Pager total={data.events.total} limit={data.events.limit} offset={data.events.offset} onChange={setOffset} />
            </>
          )}
        </>
      )}
    </>
  );
}

export default function ImpactPage() {
  return <AppShell><ImpactView /></AppShell>;
}
