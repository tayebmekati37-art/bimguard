"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { HealthBar } from "@/components/HealthPanel";
import { ErrorNote, SeverityBadge } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { getDashboard, type Dashboard } from "@/lib/api";
import { READINESS, formatDate } from "@/lib/labels";

function Total({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded border border-line bg-white p-3">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone ?? ""}`}>{value}</p>
    </div>
  );
}

function DashboardView() {
  const { t } = useT();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { getDashboard().then(setData).catch((e) => setError(e.message)); }, []);
  if (error) return <ErrorNote message={error} />;
  if (!data) return <p className="text-muted">{t("common.loading")}</p>;
  const totals = data.totals;
  return (
    <>
      <h1 className="text-2xl font-semibold">{t("dashboard.title")}</h1>
      <p className="mt-1 text-sm text-muted">{t("dashboard.subtitle")}</p>

      <div className="mt-6 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Total label={t("dashboard.projects")} value={totals.projects} />
        <Total label={t("dashboard.documents")} value={totals.documents} />
        <Total label={t("dashboard.blocked")} value={totals.blocked} tone={totals.blocked ? "text-status-critical" : ""} />
        <Total label={t("dashboard.criticalDocuments")} value={totals.critical_documents} tone={totals.critical_documents ? "text-status-critical" : ""} />
        <Total label={t("dashboard.staleDependenciesLabel")} value={totals.stale_dependencies} tone={totals.stale_dependencies ? "text-status-stale" : ""} />
        <Total label={t("dashboard.openImpacts")} value={totals.open_impacts} />
      </div>

      {data.projects.length === 0 ? (
        <div className="mt-6 rounded border border-dashed border-line bg-white p-8">
          <p className="font-medium">{t("dashboard.noActiveProjects")}</p>
          <p className="mt-1 text-sm text-muted">
            <Link href="/projects" className="text-steel hover:underline">{t("dashboard.goToProjects")}</Link> {t("dashboard.createFirst")}
          </p>
        </div>
      ) : (
        <ul className="mt-6 grid gap-4 lg:grid-cols-2">
          {data.projects.map((p) => {
            const v = p.validation;
            return (
              <li key={p.project_id} className="rounded border border-line bg-white p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link href={`/projects/${p.project_id}`} className="block truncate text-lg font-semibold text-steel hover:underline">{p.project_name}</Link>
                    <p className="text-sm text-muted">{p.client || t("dashboard.noClient")} · {p.documents} {t("dashboard.documents")}</p>
                  </div>
                  <span className={`shrink-0 rounded border px-2 py-1 text-xs font-semibold ${v ? READINESS[v.status].cls : "border-line text-muted"}`}>
                    {v ? t(`readiness.${v.status}`) : t("readiness.NOT_VALIDATED")}
                  </span>
                </div>
                {v?.outdated && <p className="mt-2 text-xs font-medium text-status-stale">{t("dashboard.changedSinceValidation")}</p>}
                <div className="mt-3"><HealthBar counts={p.document_health} /></div>
                <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
                  <span className={p.stale_dependencies ? "font-medium text-status-stale" : "text-muted"}>
                    {p.stale_dependencies} {t("dashboard.staleDepsLower")}
                  </span>
                  <span className="text-muted">{p.open_impacts.total} {t("dashboard.openImpactsLower")}</span>
                  {(["CRITICAL", "HIGH"] as const).filter((s) => p.open_impacts.by_severity[s]).map((s) => (
                    <span key={s} className="flex items-center gap-1"><SeverityBadge severity={s} /><span>{p.open_impacts.by_severity[s]}</span></span>
                  ))}
                </div>
                <div className="mt-3 flex items-center justify-between text-xs text-muted">
                  <span>{p.last_change_at ? `${t("dashboard.lastChange")} ${formatDate(p.last_change_at)}` : t("dashboard.noActivity")}</span>
                  <span className="space-x-3">
                    <Link href={`/projects/${p.project_id}/validation`} className="text-steel hover:underline">{t("dashboard.validationLink")}</Link>
                    <Link href={`/projects/${p.project_id}/dependencies`} className="text-steel hover:underline">{t("dashboard.graphLink")}</Link>
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}

export default function DashboardPage() {
  return <AppShell><DashboardView /></AppShell>;
}