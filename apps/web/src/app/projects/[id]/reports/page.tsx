"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ErrorNote, btnSecondary } from "@/components/ui";
import {
  downloadReadinessReport, getProject, getReadinessReport,
  type Project, type ReadinessReport,
} from "@/lib/api";
import { formatDate } from "@/lib/labels";

function statusTone(status: string): string {
  if (status === "READY") return "border-status-ok text-status-ok";
  if (status === "READY_WITH_WARNINGS") return "border-status-warn text-status-warn";
  if (status === "BLOCKED") return "border-status-critical text-status-critical";
  return "border-line text-muted";
}

function ReportsView() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [report, setReport] = useState<ReadinessReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([getProject(id), getReadinessReport(id)])
      .then(([p, r]) => { setProject(p); setReport(r); setError(null); })
      .catch((e) => setError(e.message));
  }, [id]);
  useEffect(load, [load]);

  async function download(fmt: "json" | "csv" | "pdf") {
    setBusy(fmt);
    setError(null);
    try { await downloadReadinessReport(id, fmt); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  }

  if (error && !report) return (
    <>
      <Link href={`/projects/${id}`} className="text-sm text-steel hover:underline">Back to project</Link>
      <ErrorNote message={error} />
    </>
  );
  if (!report || !project) return <p className="text-muted">Loading</p>;

  const s = report.summary;

  return (
    <>
      <Link href={`/projects/${id}`} className="text-sm text-steel hover:underline">Back to {project.name}</Link>
      <div className="mt-3">
        <h1 className="text-2xl font-semibold">Reports</h1>
        <p className="mt-1 text-sm text-muted">
          The readiness report as structured JSON, a spreadsheet-friendly CSV, and a printable PDF.
          All three contain the same data.
        </p>
      </div>

      <ErrorNote message={error} />

      <section className="mt-5 rounded border border-line bg-white p-4" aria-label="Summary">
        <div className="flex items-center gap-3">
          <span className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${statusTone(s.readiness_status)}`}>
            {s.readiness_status}
          </span>
          <span className="text-xs text-muted">Generated {formatDate(report.generated_at)}</span>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">
          <div><span className="text-2xl font-semibold">{s.documents}</span> <span className="text-muted">documents</span></div>
          <div><span className="text-2xl font-semibold">{s.stale_dependencies}</span> <span className="text-muted">stale deps</span></div>
          <div><span className="text-2xl font-semibold">{s.open_impacts.total}</span> <span className="text-muted">open impacts</span></div>
          <div><span className="text-2xl font-semibold">{s.issue_counts.total}</span> <span className="text-muted">issues ({s.issue_counts.open} open)</span></div>
        </div>
      </section>

      <section className="mt-5 flex flex-wrap gap-3" aria-label="Downloads">
        <button className={btnSecondary} disabled={busy !== null} onClick={() => download("json")}>
          {busy === "json" ? "Preparing..." : "Download JSON"}
        </button>
        <button className={btnSecondary} disabled={busy !== null} onClick={() => download("csv")}>
          {busy === "csv" ? "Preparing..." : "Download CSV"}
        </button>
        <button className={btnSecondary} disabled={busy !== null} onClick={() => download("pdf")}>
          {busy === "pdf" ? "Preparing..." : "Download PDF"}
        </button>
      </section>

      {report.validation ? (
        <p className="mt-4 text-xs text-muted">
          Based on validation run from {formatDate(report.validation.created_at)}
          {report.validation.created_by_name ? ` by ${report.validation.created_by_name}` : ""}.
        </p>
      ) : (
        <p className="mt-4 text-xs text-muted">
          This project has not been validated yet. Run a validation to include issue data in the report.
        </p>
      )}
    </>
  );
}

export default function ReportsPage() {
  return <AppShell><ReportsView /></AppShell>;
}