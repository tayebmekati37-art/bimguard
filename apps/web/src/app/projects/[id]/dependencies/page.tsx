"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell, useUser } from "@/components/AppShell";
import { GraphLegend, GraphView } from "@/components/GraphView";
import { ErrorNote, Field, Modal, SeverityBadge, btnDanger, btnPrimary, btnSecondary, inputCls } from "@/components/ui";
import {
  createDependency, deleteDependency, getDocumentOverview, getGraph, getImpact, getProject, validateDependency,
  type DependencyRecord, type DocumentOverview, type GraphData, type ImpactData, type Project, type RelationshipType,
} from "@/lib/api";
import { CHANGE_TYPES, FLOW, HEALTH, RELATIONSHIPS, SEVERITIES, can, flowSentence, formatDate } from "@/lib/labels";

function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(fn: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return { busy, error, run };
}

function AddDialog({ graph, onClose, onCreated }: { graph: GraphData; onClose: () => void; onCreated: () => void }) {
  const [source, setSource] = useState(graph.nodes[0]?.id ?? "");
  const [target, setTarget] = useState(graph.nodes[1]?.id ?? "");
  const [kind, setKind] = useState<RelationshipType>("depends_on");
  const [confidence, setConfidence] = useState(100);
  const [reason, setReason] = useState("");
  const { busy, error, run } = useAction();
  const number = (id: string) => graph.nodes.find((n) => n.id === id)?.document_number ?? "?";
  const valid = source && target && source !== target && reason.trim().length >= 3;
  const docOptions = graph.nodes.map((n) => <option key={n.id} value={n.id}>{n.document_number} {n.name}</option>);
  return (
    <Modal title="Add dependency" onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); run(async () => {
        await createDependency({ source_document_id: source, target_document_id: target, relationship_type: kind,
                                 confidence: confidence / 100, reason: reason.trim() });
        onCreated(); }); }}>
        <Field label="Document"><select className={inputCls} value={source} onChange={(e) => setSource(e.target.value)}>{docOptions}</select></Field>
        <Field label="Relationship" hint={RELATIONSHIPS[kind].hint}>
          <select className={inputCls} value={kind} onChange={(e) => setKind(e.target.value as RelationshipType)}>
            {(Object.keys(RELATIONSHIPS) as RelationshipType[]).map((k) => <option key={k} value={k}>{RELATIONSHIPS[k].label}</option>)}
          </select>
        </Field>
        <Field label="Other document"><select className={inputCls} value={target} onChange={(e) => setTarget(e.target.value)}>{docOptions}</select></Field>
        {source && target && source !== target && (
          <p className="mt-3 rounded bg-steel-light px-3 py-2 text-sm">
            <strong>{RELATIONSHIPS[kind].phrase(number(source), number(target))}.</strong>{" "}
            {flowSentence(FLOW[kind], number(source), number(target))}
          </p>
        )}
        <Field label={`Confidence: ${confidence}%`} hint="How sure you are that this relationship exists. It scales the strength of the impact.">
          <input type="range" min={10} max={100} step={5} className="mt-2 w-full" value={confidence} onChange={(e) => setConfidence(Number(e.target.value))} />
        </Field>
        <Field label="Reason" hint="Why this relationship exists. It is shown wherever the impact is explained.">
          <textarea className={inputCls} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Wall positions and openings come from the architectural model" />
        </Field>
        <ErrorNote message={source === target ? "Choose two different documents." : error} />
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className={btnSecondary} onClick={onClose}>Cancel</button>
          <button type="submit" className={btnPrimary} disabled={busy || !valid}>Add dependency</button>
        </div>
      </form>
    </Modal>
  );
}

function NodePanel({ o, projectId, direction }: { o: DocumentOverview; projectId: string; direction: "downstream" | "upstream" }) {
  const d = o.document, h = HEALTH[o.health_state];
  const c = o.latest_comparison;
  return (
    <section className="rounded border border-line bg-white p-4" aria-label={`Details of ${d.document_number}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-mono text-lg font-semibold">{d.document_number}</h2>
        <span className={`rounded border px-2 py-0.5 text-xs font-medium ${h.cls}`}>{h.label}</span>
      </div>
      <p className="text-sm text-muted">{d.name}</p>
      {o.health_reasons.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm">{o.health_reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
      <dl className="mt-3 grid grid-cols-[7rem_1fr] gap-y-1 text-sm">
        <dt className="text-muted">Discipline</dt><dd>{d.discipline}</dd>
        <dt className="text-muted">Revision</dt><dd>{d.current_revision_number ? `v${d.current_revision_number}` : "None"}</dd>
        <dt className="text-muted">Status</dt><dd>{d.status.replace("_", " ")}</dd>
        <dt className="text-muted">Author</dt><dd>{d.author || "Not set"}</dd>
        <dt className="text-muted">Modified</dt><dd>{formatDate(d.modified_at)}</dd>
      </dl>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <p className="text-sm font-medium">Relies on</p>
          {o.providers.length === 0 ? <p className="text-xs text-muted">Nothing</p> : (
            <ul className="mt-1 space-y-1 text-xs">{o.providers.map((p) => (
              <li key={p.document_id + p.relationship_type}><span className="font-mono">{p.document_number}</span>{" "}
                <span className="text-muted">{RELATIONSHIPS[p.relationship_type].label.toLowerCase()}</span>
                {p.stale && <span className="ml-1 text-status-stale">stale (reviewed against v{p.validated_against_revision ?? "none"}, now v{p.current_revision})</span>}</li>))}</ul>)}
        </div>
        <div>
          <p className="text-sm font-medium">Relied on by</p>
          {o.dependents.length === 0 ? <p className="text-xs text-muted">Nothing</p> : (
            <ul className="mt-1 space-y-1 text-xs">{o.dependents.map((p) => (
              <li key={p.document_id + p.relationship_type}><span className="font-mono">{p.document_number}</span>{" "}
                <span className="text-muted">{RELATIONSHIPS[p.relationship_type].label.toLowerCase()}</span></li>))}</ul>)}
        </div>
      </div>
      <p className="mt-3 text-sm">{o.downstream_count === 0 ? "A change to this document reaches no other document."
        : `A change to this document can reach ${o.downstream_count} ${o.downstream_count === 1 ? "document" : "documents"}, up to ${o.radius} ${o.radius === 1 ? "step" : "steps"} away.`}</p>
      {c && (
        <div className="mt-3 rounded bg-paper p-3 text-sm">
          <p className="font-medium">Latest changes: v{c.from_revision_number} to v{c.to_revision_number}</p>
          <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs">
            {c.total_changes} {c.total_changes === 1 ? "change" : "changes"}
            {SEVERITIES.filter((s) => c.by_severity[s]).map((s) => <span key={s} className="flex items-center gap-1"><SeverityBadge severity={s} />{c.by_severity[s]}</span>)}
            <span className="text-muted">{Object.entries(c.by_type).map(([t, n]) => `${n} ${(CHANGE_TYPES[t] ?? t).toLowerCase()}`).join(", ")}</span>
          </p>
          <Link href={`/revisions/${c.revision_id}/compare`} className="mt-1 inline-block text-xs text-steel hover:underline">View the comparison</Link>
        </div>
      )}
      {o.open_impacts.length > 0 && (
        <div className="mt-3">
          <p className="text-sm font-medium">Open impacts on this document</p>
          <ul className="mt-1 space-y-1 text-xs">{o.open_impacts.map((i) => (
            <li key={i.changed_document_number + i.changed_revision_number} className="flex items-center gap-2"><SeverityBadge severity={i.severity} />
              <span>{i.changed_document_number} v{i.changed_revision_number}, score {i.score.toFixed(1)}, {i.direct ? "direct" : "indirect"}</span></li>))}</ul>
          <Link href={`/projects/${projectId}/impact`} className="mt-1 inline-block text-xs text-steel hover:underline">View impact analysis</Link>
        </div>
      )}
      <p className="sr-only">Showing {direction} relationships.</p>
    </section>
  );
}

function DependenciesView() {
  const { id } = useParams<{ id: string }>();
  const user = useUser();
  const [project, setProject] = useState<Project | null>(null);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [direction, setDirection] = useState<"downstream" | "upstream">("downstream");
  const [impact, setImpact] = useState<ImpactData | null>(null);
  const [overview, setOverview] = useState<DocumentOverview | null>(null);
  const [step, setStep] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [autoPlay, setAutoPlay] = useState(false);
  const autoStarted = useRef(false);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<DependencyRecord | null>(null);
  const action = useAction();

  const load = useCallback(() => {
    Promise.all([getProject(id), getGraph(id)]).then(([p, g]) => { setProject(p); setGraph(g); setError(null); })
      .catch((e) => setError(e.message));
  }, [id]);
  useEffect(load, [load]);
  useEffect(() => {
    if (!selected) { setImpact(null); setOverview(null); return; }
    getImpact(selected, direction).then(setImpact).catch((e) => setError(e.message));
    getDocumentOverview(selected).then(setOverview).catch((e) => setError(e.message));
  }, [selected, direction, graph]);

  // When the project has stale dependencies, open on the document whose change caused them and replay how it spread.
  useEffect(() => {
    if (!graph || autoStarted.current) return;
    const stale = graph.edges.find((e) => e.is_stale && e.provider_document_id);
    if (stale?.provider_document_id) { autoStarted.current = true; setSelected(stale.provider_document_id); setAutoPlay(true); }
  }, [graph]);
  useEffect(() => {
    if (autoPlay && impact && impact.root_document_id === selected && impact.direction === "downstream") { setAutoPlay(false); setPlaying(true); }
  }, [autoPlay, impact, selected]);
  useEffect(() => {
    if (!playing || !impact) return;
    const max = impact.radius;
    if (max === 0 || window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setStep(null); setPlaying(false); return; }
    let current = 0;
    setStep(0);
    const timer = setInterval(() => {
      current += 1;
      setStep(current);
      if (current >= max) { clearInterval(timer); setTimeout(() => { setStep(null); setPlaying(false); }, 1000); }
    }, 800);
    return () => clearInterval(timer);
  }, [playing, impact]);

  if (error && !graph) return <><Link href={`/projects/${id}`} className="text-sm text-steel hover:underline">Back to project</Link><ErrorNote message={error} /></>;
  if (!graph || !project) return <p className="text-muted">Loading</p>;

  const editable = can.editDocuments(user.role) && project.status === "active";
  const reached = new Set(impact && direction === "downstream" ? impact.items.filter((i) => step === null || i.distance <= step).map((i) => i.document_id) : []);
  const selectedNode = graph.nodes.find((n) => n.id === selected);

  return (
    <>
      <Link href={`/projects/${id}`} className="text-sm text-steel hover:underline">Back to {project.name}</Link>
      <div className="mt-3 flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-semibold">Dependencies</h1>
          <p className="mt-1 text-sm text-muted">{graph.nodes.length} documents · {graph.edges.length} relationships ·{" "}
            <span className={graph.stale_count ? "font-medium text-status-stale" : ""}>{graph.stale_count} stale</span></p>
        </div>
        {editable && graph.nodes.length >= 2 && <button className={btnPrimary} onClick={() => setAdding(true)}>Add dependency</button>}
      </div>
      <ErrorNote message={error ?? action.error} />

      {graph.cycles.map((c) => (
        <p key={c.join()} role="alert" className="mt-4 rounded border border-status-warn/50 bg-status-warn/5 px-3 py-2 text-sm">
          Circular dependency: {c.join(", ")} depend on each other. Impact analysis still works, but check whether this is intended.
        </p>
      ))}

      {graph.nodes.length < 2 && (
        <div className="mt-6 rounded border border-dashed border-line bg-white p-8">
          <p className="font-medium">Add at least two documents first.</p>
          <p className="mt-1 text-sm text-muted">Dependencies connect documents, so they appear here once the project has some.</p>
        </div>
      )}

      {graph.nodes.length >= 2 && (
        <section className="mt-6">
          <GraphView graph={graph} selected={selected} reached={reached} onSelect={(n) => { setPlaying(false); setStep(null); setSelected(selected === n ? null : n); }} />
          <GraphLegend />
          <p className="mt-2 text-xs text-muted">Arrows point the way a change travels. Orange arrows are stale dependencies and dashed lines run both ways. Select a document to inspect it and see what a change to it reaches.</p>
        </section>
      )}

      {selectedNode && (
        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          {overview && overview.document.id === selectedNode.id
            ? <NodePanel o={overview} projectId={id} direction={direction} /> : <p className="text-sm text-muted">Loading</p>}
          <div>
            {impact && (
        <section className="rounded border border-line bg-white p-4" aria-label="Impact of the selected document">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">
              <span className="font-mono">{selectedNode.document_number}</span>{" "}
              <span className="text-base font-normal text-muted">{direction === "downstream" ? "can affect" : "relies on"}</span>
            </h2>
            <div className="flex flex-wrap gap-2">
              <button className={`${btnSecondary} ${direction === "downstream" ? "border-steel bg-steel-light" : ""}`} onClick={() => { setPlaying(false); setStep(null); setDirection("downstream"); }}>What a change affects</button>
              <button className={`${btnSecondary} ${direction === "upstream" ? "border-steel bg-steel-light" : ""}`} onClick={() => { setPlaying(false); setStep(null); setDirection("upstream"); }}>What it relies on</button>
              {direction === "downstream" && impact.items.length > 0 && (
                <button className={btnPrimary} disabled={playing} onClick={() => setPlaying(true)}>{playing ? "Showing how it spreads" : "Show how it spreads"}</button>)}
            </div>
          </div>
          {impact.items.length === 0 ? (
            <p className="mt-3 text-sm text-muted">{direction === "downstream" ? "A change to this document does not reach any other document." : "This document does not rely on any other document."}</p>
          ) : (
            <table className="mt-3 w-full text-sm">
              <thead className="border-b border-line text-left text-muted">
                <tr><th className="py-1.5 font-medium">Document</th><th className="font-medium">Distance</th>
                    <th className="font-medium">Strength</th><th className="font-medium">Path and reason</th></tr>
              </thead>
              <tbody>
                {impact.items.map((i) => (
                  <tr key={i.document_id} className="border-b border-line align-top last:border-0">
                    <td className="py-1.5"><span className="font-mono">{i.document_number}</span><div className="text-xs text-muted">{i.name}</div></td>
                    <td>{i.direct ? "Direct" : `${i.distance} steps`}</td>
                    <td>{Math.round(i.strength * 100)}%</td>
                    <td className="text-xs">{i.path.map((s) => (
                      <div key={s.edge_id}><span className="font-mono">{s.from_number}</span> to <span className="font-mono">{s.to_number}</span>{" "}
                        <span className="text-muted">({RELATIONSHIPS[s.relationship_type].label.toLowerCase()}: {s.reason})</span></div>))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
            )}
          </div>
        </div>
      )}

      <h2 className="mt-8 text-lg font-semibold">Relationships</h2>
      {graph.edges.length === 0 ? (
        <div className="mt-3 rounded border border-dashed border-line bg-white p-8">
          <p className="font-medium">No dependencies registered yet.</p>
          <p className="mt-1 text-sm text-muted">Add one to tell BIMGuard which documents rely on each other.</p>
        </div>
      ) : (
        <table className="mt-3 w-full border border-line bg-white text-sm">
          <thead className="border-b border-line bg-paper text-left text-muted">
            <tr><th className="px-3 py-2 font-medium">Relationship</th><th className="px-3 font-medium">Confidence</th>
                <th className="px-3 font-medium">Validated against</th><th className="px-3 font-medium">State</th><th /></tr>
          </thead>
          <tbody>
            {graph.edges.map((e) => (
              <tr key={e.id} className="border-b border-line align-top last:border-0">
                <td className="px-3 py-2">
                  <div className="font-medium"><span className="font-mono">{e.source_number}</span> {RELATIONSHIPS[e.relationship_type].label.toLowerCase()} <span className="font-mono">{e.target_number}</span></div>
                  <div className="text-xs text-muted">{flowSentence(e.flow, e.source_number, e.target_number)} {e.reason}</div>
                </td>
                <td className="px-3 py-2">{Math.round(e.confidence * 100)}%</td>
                <td className="px-3 py-2">
                  {e.provider_number ? <>{e.provider_number} {e.validated_against_revision ? `v${e.validated_against_revision}` : "never"}
                    {e.validated_at && <div className="text-xs text-muted">{formatDate(e.validated_at)} · {e.validated_by_name}</div>}</>
                    : <span className="text-muted">Not tracked (works both ways)</span>}
                </td>
                <td className="px-3 py-2">
                  {e.is_stale ? <span className="rounded border border-status-stale px-2 py-0.5 text-xs font-medium text-status-stale">Stale: {e.provider_number} is now v{e.provider_current_revision}</span>
                    : e.provider_number ? <span className="rounded border border-status-ok px-2 py-0.5 text-xs font-medium text-status-ok">Up to date</span> : null}
                </td>
                <td className="space-x-2 whitespace-nowrap px-3 py-2 text-right">
                  {e.is_stale && can.changeStatus(user.role) && project.status === "active" && (
                    <button className={btnSecondary} disabled={action.busy}
                            onClick={() => action.run(async () => { await validateDependency(e.id); load(); })}>
                      Mark reviewed against v{e.provider_current_revision}</button>
                  )}
                  {editable && <button className={btnSecondary} onClick={() => setRemoving(e)}>Remove</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {adding && <AddDialog graph={graph} onClose={() => setAdding(false)} onCreated={() => { setAdding(false); load(); }} />}
      {removing && (
        <Modal title="Remove dependency" onClose={() => setRemoving(null)}>
          <p className="mt-3 text-sm">Remove <strong>{RELATIONSHIPS[removing.relationship_type].phrase(removing.source_number, removing.target_number)}</strong>?
            Changes to {removing.provider_number ?? "either document"} will no longer be traced to the other. The removal is recorded in the audit log.</p>
          <div className="mt-6 flex justify-end gap-2">
            <button className={btnSecondary} onClick={() => setRemoving(null)}>Cancel</button>
            <button className={btnDanger} disabled={action.busy}
                    onClick={() => action.run(async () => { await deleteDependency(removing.id); setRemoving(null); load(); })}>Remove</button>
          </div>
        </Modal>
      )}
    </>
  );
}

export default function DependenciesPage() {
  return <AppShell><DependenciesView /></AppShell>;
}
