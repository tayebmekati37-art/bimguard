"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useState } from "react";
import { AppShell, useUser } from "@/components/AppShell";
import { PlanView } from "@/components/PlanView";
import { ErrorNote, Pager, SeverityBadge, btnPrimary, btnSecondary, useDebounced } from "@/components/ui";
import { useT } from "@/lib/i18n";
import {
  ApiError, getPlan, getRevisionComparison, listChanges, runComparison,
  type ChangeRecord, type Comparison, type Page, type PlanData,
} from "@/lib/api";
import { CHANGE_TYPES, SEVERITIES, can, formatDate } from "@/lib/labels";

const PAGE_SIZE = 25;

type Translate = (key: string, params?: Record<string, string | number>) => string;

function show(v: unknown, t: Translate): string {
  if (v === null || v === undefined) return t("compare.showNone");
  if (Array.isArray(v)) return v.map((n) => (typeof n === "number" ? String(Math.round(n * 1000) / 1000) : String(n))).join(", ");
  if (typeof v === "number") return String(Math.round(v * 1000) / 1000);
  if (typeof v === "boolean") return v ? t("common.yes") : t("common.no");
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button onClick={onClick} aria-pressed={active}
                 className={`${btnSecondary} ${active ? "border-steel bg-steel-light" : ""}`}>{children}</button>;
}

function CompareView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const user = useUser();
  const { t } = useT();
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [missing, setMissing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [changes, setChanges] = useState<Page<ChangeRecord> | null>(null);
  const [plan, setPlan] = useState<PlanData | null>(null);
  const [severity, setSeverity] = useState("");
  const [type, setType] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const q = useDebounced(search);

  const loadComparison = useCallback(() => {
    getRevisionComparison(id).then((c) => { setComparison(c); setMissing(null); })
      .catch((e: ApiError) => (e.status === 404 ? setMissing(e.message) : setError(e.message)));
  }, [id]);
  useEffect(loadComparison, [loadComparison]);

  useEffect(() => {
    if (!comparison) return;
    getPlan(comparison.id).then(setPlan).catch((e) => setError(e.message));
  }, [comparison]);
  useEffect(() => {
    if (!comparison) return;
    listChanges(comparison.id, { severity, change_type: type, q, limit: PAGE_SIZE, offset })
      .then(setChanges).catch((e) => setError(e.message));
  }, [comparison, severity, type, q, offset]);

  async function run() {
    setBusy(true); setError(null);
    try { setComparison(await runComparison(id)); setMissing(null); setOffset(0); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  if (!comparison) {
    return (
      <>
        <button className="text-sm text-steel hover:underline" onClick={() => router.back()}>{t("action.back")}</button>
        <h1 className="mt-3 text-2xl font-semibold">{t("compare.title")}</h1>
        <ErrorNote message={error} />
        {missing && (
          <div className="mt-4 rounded border border-dashed border-line bg-white p-8">
            <p className="font-medium">{missing}</p>
            <p className="mt-1 text-sm text-muted">{t("compare.missingHint")}</p>
            {can.compare(user.role) && (
              <button className={`${btnPrimary} mt-4`} disabled={busy} onClick={run}>
                {busy ? t("compare.comparing") : t("compare.runComparison")}
              </button>
            )}
          </div>
        )}
        {!missing && !error && <p className="mt-4 text-muted">{t("common.loading")}</p>}
      </>
    );
  }

  const bySeverity = comparison.counts.by_severity ?? {}, byType = comparison.counts.by_type ?? {};
  const selectedTag = /^[A-Za-z0-9._-]+$/.test(search) ? search : "";

  return (
    <>
      <Link href={`/projects/${comparison.project_id}`} className="text-sm text-steel hover:underline">{t("compare.backToProject")}</Link>
      <div className="mt-3 flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-semibold">
            <span className="font-mono">{comparison.document_number}</span> v{comparison.from_revision_number}
            <span className="mx-2 text-muted">{t("compare.to")}</span>v{comparison.to_revision_number}
          </h1>
          <p className="mt-1 text-sm text-muted">
            {t("compare.comparedLine", {
              date: formatDate(comparison.created_at),
              name: comparison.created_by_name,
              old: comparison.counts.elements_old ?? 0,
              new: comparison.counts.elements_new ?? 0,
              unchanged: comparison.counts.elements_unchanged ?? 0,
            })}
          </p>
        </div>
        {can.compare(user.role) && (
          <button className={btnSecondary} disabled={busy} onClick={run}>
            {busy ? t("compare.comparing") : t("compare.reRunComparison")}
          </button>
        )}
      </div>
      <ErrorNote message={error} />

      <section className="mt-6 rounded border border-line bg-white p-4" aria-label={t("compare.summaryAria")}>
        <p className="text-lg font-semibold">
          {comparison.total_changes} {comparison.total_changes === 1 ? t("compare.changeSingular") : t("compare.changePlural")}
        </p>
        {comparison.total_changes === 0 && <p className="mt-1 text-sm text-muted">{t("compare.noDifferences")}</p>}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted">{t("compare.severity")}</span>
          <Chip active={severity === ""} onClick={() => { setSeverity(""); setOffset(0); }}>{t("action.all")}</Chip>
          {SEVERITIES.filter((s) => bySeverity[s]).map((s) => (
            <Chip key={s} active={severity === s} onClick={() => { setSeverity(severity === s ? "" : s); setOffset(0); }}>
              {t(`severity.${s}`)} {bySeverity[s]}
            </Chip>
          ))}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted">{t("compare.type")}</span>
          <Chip active={type === ""} onClick={() => { setType(""); setOffset(0); }}>{t("action.all")}</Chip>
          {Object.entries(byType).map(([tp, n]) => (
            <Chip key={tp} active={type === tp} onClick={() => { setType(type === tp ? "" : tp); setOffset(0); }}>
              {CHANGE_TYPES[tp] ?? tp} {n}
            </Chip>
          ))}
        </div>
      </section>

      <section className="mt-6">
        <h2 className="mb-2 text-lg font-semibold">{t("compare.planView")}</h2>
        {plan
          ? <PlanView plan={plan} selected={selectedTag} onSelect={(tag) => { setSearch(tag); setOffset(0); }} />
          : <p className="text-muted">{t("common.loading")}</p>}
      </section>

      <section className="mt-8">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">{t("compare.detectedChanges")}</h2>
          <input aria-label={t("compare.searchAria")} placeholder={t("compare.searchPlaceholder")}
                 className="w-64 rounded border border-line bg-white px-3 py-2 text-sm"
                 value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} />
        </div>
        {changes && changes.items.length === 0 && <p className="mt-4 text-sm">{t("compare.noMatch")}</p>}
        {changes && changes.items.length > 0 && (
          <>
            <table className="mt-3 w-full border border-line bg-white text-sm">
              <thead className="border-b border-line bg-paper text-left text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">{t("compare.severity")}</th>
                  <th className="px-3 font-medium">{t("compare.type")}</th>
                  <th className="px-3 font-medium">{t("compare.colElement")}</th>
                  <th className="px-3 font-medium">{t("compare.colChange")}</th>
                  <th className="px-3 font-medium">{t("compare.colOld")}</th>
                  <th className="px-3 font-medium">{t("compare.colNew")}</th>
                  <th className="px-3 text-right font-medium">{t("compare.colConfidence")}</th>
                </tr>
              </thead>
              <tbody>
                {changes.items.map((c) => (
                  <Fragment key={c.id}>
                    <tr className="cursor-pointer border-b border-line align-top hover:bg-steel-light/40" tabIndex={0}
                        aria-expanded={open === c.id}
                        onClick={() => setOpen(open === c.id ? null : c.id)}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(open === c.id ? null : c.id); } }}>
                      <td className="px-3 py-2"><SeverityBadge severity={c.severity} /></td>
                      <td className="px-3 py-2">{CHANGE_TYPES[c.change_type] ?? c.change_type}</td>
                      <td className="px-3 py-2"><span className="font-mono">{c.element_tag || t("compare.documentFallback")}</span></td>
                      <td className="px-3 py-2">{c.summary}</td>
                      <td className="px-3 py-2 text-muted">{c.change_type === "ELEMENT_ADDED" ? "" : show(c.old_value, t)}</td>
                      <td className="px-3 py-2">{c.change_type === "ELEMENT_REMOVED" ? "" : show(c.new_value, t)}</td>
                      <td className="px-3 py-2 text-right">{Math.round(c.confidence * 100)}%</td>
                    </tr>
                    {open === c.id && (
                      <tr className="border-b border-line"><td colSpan={7}>
                        <dl className="grid grid-cols-[10rem_1fr] gap-y-0.5 bg-paper px-4 py-3 text-xs">
                          <dt className="text-muted">{t("compare.detailsField")}</dt>
                          <dd className="break-all font-mono">{c.field}</dd>
                          <dt className="text-muted">{t("compare.elementId")}</dt>
                          <dd className="break-all font-mono">{c.element_guid ?? t("compare.showNone")}</dd>
                          <dt className="text-muted">{t("compare.matchedBy")}</dt>
                          <dd>
                            {c.match_method === "guid" ? t("compare.elementId")
                              : c.match_method === "tag" ? t("compare.matchTag")
                              : t("compare.matchNone")}
                          </dd>
                          {Object.entries(c.detail).map(([k, v]) => (
                            <Fragment key={k}>
                              <dt className="text-muted">{k}</dt>
                              <dd className="break-all">{show(v, t)}</dd>
                            </Fragment>
                          ))}
                        </dl>
                      </td></tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
            <Pager total={changes.total} limit={changes.limit} offset={changes.offset} onChange={setOffset} />
          </>
        )}
      </section>
    </>
  );
}

export default function ComparePage() {
  return <AppShell><CompareView /></AppShell>;
}