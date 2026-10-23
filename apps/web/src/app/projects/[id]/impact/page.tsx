"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Fragment, useCallback, useEffect, useState } from "react";
import { AppShell, useUser } from "@/components/AppShell";
import { ErrorNote, Pager, SeverityBadge, btnPrimary, btnSecondary } from "@/components/ui";
import { useT } from "@/lib/i18n";
import {
  getProject, getProjectImpact, runImpactAnalysis, validateDependency, type ImpactEvent, type Project, type ProjectImpact,
} from "@/lib/api";
import { DISCIPLINES, RELATIONSHIPS, SEVERITIES, can, formatDate } from "@/lib/labels";

const PAGE_SIZE = 25;
const BAR: Record<string, string> = { CRITICAL: "bg-status-critical", HIGH: "bg-status-stale", MEDIUM: "bg-status-warn", LOW: "bg-muted" };

function StateBadge({ state }: { state: ImpactEvent["state"] }) {
  const { t } = useT();
  const tone = state === "open" ? "border-status-stale text-status-stale" : state === "reviewed" ? "border-status-ok text-status-ok" : "border-line text-muted";
  return <span className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${tone}`}>{t(`impact.state.${state}`)}</span>;
}

function ScoreBar({ score, severity }: { score: number; severity: string }) {
  const { t } = useT();
  return (
    <div className="flex items-center gap-2" title={t("impact.scoreTitle", { score })}>
      <div className="h-2 w-20 rounded bg-line" aria-hidden>
        <div className={`h-2 rounded ${BAR[severity] ?? "bg-muted"}`} style={{ width: `${Math.min(100, score)}%` }} />
      </div>
      <span className="w-10 font-mono text-sm">{score.toFixed(1)}</span>
    </div>
  );
}

function Detail({ e, canReview, busy, onReview }: { e: ImpactEvent; canReview: boolean; busy: boolean; onReview: () => void }) {
  const { t } = useT();

  const reviewedSuffix = (() => {
    const parts: string[] = [t("impact.reviewedNote", { validated: e.dependency_validated_against ?? 0 })];
    if (e.validated_by_name) parts.push(t("impact.reviewedBy", { name: e.validated_by_name }));
    if (e.validated_at) parts.push(t("impact.reviewedAt", { date: formatDate(e.validated_at) }));
    return parts.join("") + ".";
  })();

  const kindLabel = (k: string) => {
    const key = `impact.kind.${k}`;
    const translated = t(key);
    return translated === key ? k : translated;
  };

  return (
    <div className="grid gap-6 bg-paper px-4 py-4 text-sm lg:grid-cols-2">
      <div>
        <p className="font-medium">{t("impact.whyAffected")}</p>
        <p className="mt-1">{e.reason}</p>
        <p className="mt-4 font-medium">{t("impact.path")}</p>
        <ol className="mt-1 space-y-1 text-xs">
          {e.path.map((s) => {
            const base = {
              from: s.from_number,
              to: s.to_number,
              type: RELATIONSHIPS[s.relationship_type].label.toLowerCase(),
              pct: Math.round(s.strength * 100),
            };
            const text = s.reason
              ? t("impact.pathStepWithReason", { ...base, reason: s.reason })
              : t("impact.pathStep", base);
            return <li key={s.edge_id}>{text}</li>;
          })}
        </ol>
        {e.state === "open" && e.direct && canReview && (
          <button className={`${btnPrimary} mt-4`} disabled={busy} onClick={onReview}>
            {t("impact.markReviewed", { doc: e.changed_document_number, rev: e.changed_revision_number })}
          </button>
        )}
        {e.state === "open" && !e.direct && (
          <p className="mt-4 text-xs text-muted">
            {t("impact.indirectNote", {
              through: e.path[0].to_number,
              doc: e.changed_document_number,
              rev: e.changed_revision_number,
            })}
          </p>
        )}
        {e.state === "reviewed" && <p className="mt-4 text-xs text-status-ok">{reviewedSuffix}</p>}
        {e.state === "advisory" && <p className="mt-4 text-xs text-muted">{t("impact.advisoryNote")}</p>}
      </div>

      <div>
        <p className="font-medium">{t("impact.whyScore")}</p>
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
        <p className="mt-2 text-xs text-muted">
          {t("impact.confidenceExplanation", { pct: Math.round(e.confidence * 100) })}
        </p>
      </div>

      <div className="lg:col-span-2">
        <p className="font-medium">
          {e.affected_element_count > 0
            ? t("impact.elementsAffectedWithCount", { doc: e.impacted_document_number, count: e.affected_element_count })
            : t("impact.elementsAffected", { doc: e.impacted_document_number })}
        </p>
        {e.note && <p className="mt-1 text-xs text-muted">{e.note}</p>}
        {!e.note && e.affected_elements.length === 0 && (
          <p className="mt-1 text-xs text-muted">{t("impact.noElementsLinked")}</p>
        )}
        {e.affected_elements.length > 0 && (
          <table className="mt-2 w-full text-xs">
            <thead className="border-b border-line text-left text-muted">
              <tr>
                <th className="py-1 font-medium">{t("impact.colElement")}</th>
                <th className="font-medium">{t("impact.colLink")}</th>
                <th className="font-medium">{t("impact.colWhy")}</th>
              </tr>
            </thead>
            <tbody>
              {e.affected_elements.map((a) => (
                <tr key={a.guid} className="border-b border-line align-top last:border-0">
                  <td className="py-1.5">
                    <span className="font-mono">{a.tag}</span>
                    <div className="text-muted">
                      {a.ifc_class.replace(/^Ifc/, "")}
                      {a.room ? t("impact.roomSuffix", { room: a.room }) : ""}
                    </div>
                  </td>
                  <td className="py-1.5">{a.kinds.map(kindLabel).join(", ")}</td>
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
  const { t } = useT();
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

  if (error && !data) return <><Link href={`/projects/${id}`} className="text-sm text-steel hover:underline">{t("breadcrumb.backToProject")}</Link><ErrorNote message={error} /></>;
  if (!data || !project) return <p className="text-muted">{t("common.loading")}</p>;

  const { counts } = data;
  const canRun = can.compare(user.role) && project.status === "active";

  const analysisLine = (a: typeof data.analyses[number]) => {
    const base = {
      doc: a.changed_document_number,
      rev: a.changed_revision_number,
      changes: a.summary.changes ?? 0,
      total: a.summary.total ?? 0,
      docWord: a.summary.total === 1 ? t("impact.docSingular") : t("impact.docPlural"),
      date: formatDate(a.created_at),
    };
    if (a.summary.radius) {
      return t("impact.analysisLineRadius", {
        ...base,
        radius: a.summary.radius,
        stepWord: a.summary.radius === 1 ? t("impact.stepSingular") : t("impact.stepPlural"),
      });
    }
    return t("impact.analysisLine", base);
  };

  return (
    <>
      <Link href={`/projects/${id}`} className="text-sm text-steel hover:underline">{t("breadcrumb.backToProject")} {project.name}</Link>
      <div className="mt-3 flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-semibold">{t("impact.title")}</h1>
          <p className="mt-1 text-sm text-muted">{t("impact.description")}</p>
        </div>
        {canRun && (
          <button className={btnSecondary} disabled={busy} onClick={() => act(() => runImpactAnalysis(id))}>
            {busy ? t("impact.analysing") : t("impact.reRun")}
          </button>
        )}
      </div>
      <ErrorNote message={error} />

      {data.analyses.length === 0 ? (
        <div className="mt-6 rounded border border-dashed border-line bg-white p-8">
          <p className="font-medium">{t("impact.noImpacts")}</p>
          <p className="mt-1 text-sm text-muted">{t("impact.noImpactsHint")}</p>
        </div>
      ) : (
        <>
          <section className="mt-6 rounded border border-line bg-white p-4" aria-label={t("impact.title")}>
            <div className="flex flex-wrap items-center gap-x-8 gap-y-2">
              <div><span className="text-2xl font-semibold">{counts.open}</span> <span className="text-sm text-muted">{t("impact.summary.open")}</span></div>
              <div><span className="text-2xl font-semibold text-status-ok">{counts.reviewed}</span> <span className="text-sm text-muted">{t("impact.summary.reviewed")}</span></div>
              {counts.advisory > 0 && (
                <div><span className="text-2xl font-semibold text-muted">{counts.advisory}</span> <span className="text-sm text-muted">{t("impact.summary.advisory")}</span></div>
              )}
              <div className="flex items-center gap-2">
                {SEVERITIES.filter((s) => counts.open_by_severity[s]).map((s) => (
                  <span key={s} className="flex items-center gap-1"><SeverityBadge severity={s} /><span className="text-sm">{counts.open_by_severity[s]}</span></span>
                ))}
              </div>
            </div>
            <ul className="mt-3 space-y-0.5 text-sm text-muted">
              {data.analyses.map((a) => <li key={a.id}>{analysisLine(a)}</li>)}
            </ul>
          </section>

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted">{t("impact.severity")}</span>
            <button className={`${btnSecondary} ${severity === "" ? "border-steel bg-steel-light" : ""}`} onClick={() => { setSeverity(""); setOffset(0); }}>{t("action.all")}</button>
            {SEVERITIES.map((s) => (
              <button key={s} aria-pressed={severity === s} className={`${btnSecondary} ${severity === s ? "border-steel bg-steel-light" : ""}`}
                onClick={() => { setSeverity(severity === s ? "" : s); setOffset(0); }}>{t(`severity.${s}`)}</button>
            ))}
            <select aria-label={t("impact.state")} className="ml-3 rounded border border-line bg-white px-3 py-1.5 text-sm" value={state}
                    onChange={(e) => { setState(e.target.value); setOffset(0); }}>
              <option value="">{t("impact.anyState")}</option>
              <option value="open">{t("impact.state.open")}</option>
              <option value="reviewed">{t("impact.state.reviewed")}</option>
              <option value="advisory">{t("impact.state.advisory")}</option>
            </select>
          </div>

          {data.events.items.length === 0 ? <p className="mt-4 text-sm">{t("impact.noMatch")}</p> : (
            <>
              <table className="mt-3 w-full border border-line bg-white text-sm">
                <thead className="border-b border-line bg-paper text-left text-muted">
                  <tr>
                    <th className="px-3 py-2 font-medium">{t("impact.score")}</th>
                    <th className="px-3 font-medium">{t("impact.severity")}</th>
                    <th className="px-3 font-medium">{t("impact.colDocument")}</th>
                    <th className="px-3 font-medium">{t("impact.distance")}</th>
                    <th className="px-3 font-medium">{t("impact.confidence")}</th>
                    <th className="px-3 font-medium">{t("impact.state")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.events.items.map((e) => (
                    <Fragment key={e.id}>
                      <tr className="cursor-pointer border-b border-line align-top hover:bg-steel-light/40" tabIndex={0}
                          aria-expanded={open === e.id}
                          onClick={() => setOpen(open === e.id ? null : e.id)}
                          onKeyDown={(k) => { if (k.key === "Enter" || k.key === " ") { k.preventDefault(); setOpen(open === e.id ? null : e.id); } }}>
                        <td className="px-3 py-2"><ScoreBar score={e.score} severity={e.severity} /></td>
                        <td className="px-3 py-2"><SeverityBadge severity={e.severity} /></td>
                        <td className="px-3 py-2">
                          <span className="font-mono">{e.impacted_document_number}</span>
                          <div className="text-xs text-muted">
                            {t("impact.rowDetail", {
                              name: e.impacted_name,
                              discipline: t(`discipline.${e.impacted_discipline}`),
                              doc: e.changed_document_number,
                              rev: e.changed_revision_number,
                            })}
                          </div>
                        </td>
                        <td className="px-3 py-2">{e.direct ? t("impact.direct") : t("deps.steps", { n: e.distance })}</td>
                        <td className="px-3 py-2">{Math.round(e.confidence * 100)}%</td>
                        <td className="px-3 py-2"><StateBadge state={e.state} /></td>
                      </tr>
                      {open === e.id && (
                        <tr className="border-b border-line"><td colSpan={6}>
                          <Detail e={e}
                                  canReview={can.changeStatus(user.role) && project.status === "active"}
                                  busy={busy}
                                  onReview={() => act(() => validateDependency(e.first_edge_id!))} />
                        </td></tr>
                      )}
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