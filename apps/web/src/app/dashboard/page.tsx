"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { HealthBar } from "@/components/HealthPanel";
import { ErrorNote, SeverityBadge } from "@/components/ui";
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
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { getDashboard().then(setData).catch((e) => setError(e.message)); }, []);
  if (error) return <ErrorNote message={error} />;
  if (!data) return <p className="text-muted">Loading</p>;
  const t = data.totals;
  return (
    <>
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      <p className="mt-1 text-sm text-muted">The health of every active project, from live data.</p>

      <div className="mt-6 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Total label="Projects" value={t.projects} />
        <Total label="Documents" value={t.documents} />
        <Total label="Blocked" value={t.blocked} tone={t.blocked ? "text-status-critical" : ""} />
        <Total label="Critical documents" value={t.critical_documents} tone={t.critical_documents ? "text-status-critical" : ""} />
        <Total label="Stale dependencies" value={t.stale_dependencies} tone={t.stale_dependencies ? "text-status-stale" : ""} />
        <Total label="Open impacts" value={t.open_impacts} />
      </div>

      {data.projects.length === 0 ? (
        <div className="mt-6 rounded border border-dashed border-line bg-white p-8">
          <p className="font-medium">No active projects.</p>
          <p className="mt-1 text-sm text-muted"><Link href="/projects" className="text-steel hover:underline">Go to Projects</Link> to create one.</p>
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
                    <p className="text-sm text-muted">{p.client || "No client"} · {p.documents} documents</p>
                  </div>
                  <span className={`shrink-0 rounded border px-2 py-1 text-xs font-semibold ${v ? READINESS[v.status].cls : "border-line text-muted"}`}>
                    {v ? READINESS[v.status].label : "Not validated"}</span>
                </div>
                {v?.outdated && <p className="mt-2 text-xs font-medium text-status-stale">Changed since the last validation</p>}
                <div className="mt-3"><HealthBar counts={p.document_health} /></div>
                <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
                  <span className={p.stale_dependencies ? "font-medium text-status-stale" : "text-muted"}>{p.stale_dependencies} stale dependencies</span>
                  <span className="text-muted">{p.open_impacts.total} open impacts</span>
                  {(["CRITICAL", "HIGH"] as const).filter((s) => p.open_impacts.by_severity[s]).map((s) => (
                    <span key={s} className="flex items-center gap-1"><SeverityBadge severity={s} /><span>{p.open_impacts.by_severity[s]}</span></span>))}
                </div>
                <div className="mt-3 flex items-center justify-between text-xs text-muted">
                  <span>{p.last_change_at ? `Last change ${formatDate(p.last_change_at)}` : "No activity yet"}</span>
                  <span className="space-x-3">
                    <Link href={`/projects/${p.project_id}/validation`} className="text-steel hover:underline">Validation</Link>
                    <Link href={`/projects/${p.project_id}/dependencies`} className="text-steel hover:underline">Graph</Link>
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
