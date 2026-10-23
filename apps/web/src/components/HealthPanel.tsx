"use client";

import Link from "next/link";
import type { HealthState, ProjectHealth } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { HEALTH, HEALTH_ORDER, READINESS, SEVERITIES, formatDate } from "@/lib/labels";
import { SeverityBadge } from "@/components/ui";

export function HealthBar({ counts }: { counts: Record<HealthState, number> }) {
  const { t } = useT();
  const total = HEALTH_ORDER.reduce((n, s) => n + (counts[s] ?? 0), 0);
  if (total === 0) return <p className="text-xs text-muted">{t("health.noDocuments")}</p>;
  return (
    <div>
      <div className="flex h-2.5 overflow-hidden rounded bg-line" role="img"
           aria-label={HEALTH_ORDER.map((s) => `${counts[s] ?? 0} ${t(`health.${s}`).toLowerCase()}`).join(", ")}>
        {HEALTH_ORDER.map((s) => (counts[s] ?? 0) > 0 && <div key={s} style={{ width: `${(counts[s] / total) * 100}%`, background: HEALTH[s].hex }} />)}
      </div>
      <p className="mt-1 text-xs text-muted">{HEALTH_ORDER.filter((s) => counts[s]).map((s) => `${counts[s]} ${t(`health.${s}`).toLowerCase()}`).join(" · ")}</p>
    </div>
  );
}

function Stat({ label, value, tone, children }: { label: string; value: React.ReactNode; tone?: string; children?: React.ReactNode }) {
  return (
    <div className="rounded border border-line bg-white p-3">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone ?? ""}`}>{value}</p>
      {children}
    </div>
  );
}

export function HealthPanel({ health }: { health: ProjectHealth }) {
  const { t } = useT();
  const v = health.validation;
  const sev = v?.open_by_severity ?? {};
  const base = `/projects/${health.project_id}`;
  return (
    <section aria-label={t("health.projectHealth")} className="mt-6">
      <h2 className="text-lg font-semibold">{t("health.projectHealth")}</h2>
      <div className={`mt-3 rounded border-2 p-4 ${v ? READINESS[v.status].cls : "border-line bg-white text-ink"}`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xl font-semibold tracking-tight">
              {v ? t(`readiness.${v.status}`).toUpperCase() : t("health.notValidatedYet")}
            </p>
            <p className="mt-0.5 text-sm text-ink">
              {v ? t("health.validatedSummary", {
                date: formatDate(v.created_at),
                blocking: v.blocking,
                open: v.open,
                acknowledged: v.acknowledged,
              }) : t("health.runValidationHint")}
            </p>
            {v?.outdated && <p className="mt-1 text-sm font-medium text-status-stale">{t("health.changedSinceValidation")}</p>}
          </div>
          <Link href={`${base}/validation`} className="rounded bg-steel px-4 py-2 text-sm font-medium text-white hover:bg-steel-dark">
            {t("project.validateForIssue")}
          </Link>
        </div>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={t("health.statDocuments")} value={health.documents}>
          <p className="text-xs text-muted">{t("health.withCurrentRevision", { count: health.documents_with_revision })}</p>
        </Stat>
        <Stat label={t("health.statStaleDependencies")} value={health.stale_dependencies} tone={health.stale_dependencies ? "text-status-stale" : "text-status-ok"}>
          <p className="text-xs text-muted">
            {t("health.ofDependencies", { count: health.dependencies })}{" "}
            <Link href={`${base}/dependencies`} className="text-steel hover:underline">{t("project.dependencies")}</Link>
          </p>
        </Stat>
        <Stat label={t("health.statOpenImpacts")} value={health.open_impacts.total}>
          <div className="mt-1 flex flex-wrap gap-1">
            {SEVERITIES.filter((s) => health.open_impacts.by_severity[s]).map((s) =>
              <span key={s} className="flex items-center gap-1"><SeverityBadge severity={s} /><span className="text-xs">{health.open_impacts.by_severity[s]}</span></span>)}
          </div>
          <p className="mt-1 text-xs"><Link href={`${base}/impact`} className="text-steel hover:underline">{t("health.viewImpactAnalysis")}</Link></p>
        </Stat>
        <Stat label={t("health.statOpenValidationIssues")} value={v ? v.open : t("health.noneYet")}>
          {v && <div className="mt-1 flex flex-wrap gap-1">{(["CRITICAL", "HIGH"] as const).map((s) =>
            <span key={s} className="flex items-center gap-1"><SeverityBadge severity={s} /><span className="text-xs">{sev[s] ?? 0}</span></span>)}</div>}
        </Stat>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <p className="text-sm font-medium">{t("health.documentHealth")}</p>
          <div className="mt-2 max-w-md"><HealthBar counts={health.document_health} /></div>
          <ul className="mt-3 flex flex-wrap gap-2">
            {health.documents_health.map((d) => (
              <li key={d.document_id}>
                <Link href={`${base}/dependencies`} title={d.reasons.length ? d.reasons.join("\n") : HEALTH[d.state].text}
                      className={`inline-flex items-center gap-1.5 rounded border px-2 py-1 text-xs ${HEALTH[d.state].cls}`}>
                  <span aria-hidden className="inline-block h-2 w-2 rounded-full" style={{ background: HEALTH[d.state].hex }} />
                  <span className="font-mono">{d.document_number}</span><span className="sr-only">{t(`health.${d.state}`)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-sm font-medium">{t("health.recentChanges")}</p>
          {health.recent_activity.length === 0 ? <p className="mt-2 text-sm text-muted">{t("health.nothingYet")}</p> : (
            <ul className="mt-2 space-y-1.5 text-sm">
              {health.recent_activity.slice(0, 6).map((a, i) => (
                <li key={i}><span>{a.text}</span><div className="text-xs text-muted">{formatDate(a.at)} · {a.user.split("@")[0]}</div></li>))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}