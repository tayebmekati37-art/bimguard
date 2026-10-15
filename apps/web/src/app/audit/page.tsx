"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ErrorNote, Pager, btnSecondary } from "@/components/ui";
import {
  listAuditLogs, listProjects,
  type AuditLogRecord, type Project,
} from "@/lib/api";
import { formatDate } from "@/lib/labels";

const PAGE_SIZE = 50;

function formatDetail(detail: Record<string, unknown>): string {
  const entries = Object.entries(detail ?? {});
  if (entries.length === 0) return "";
  return entries
    .map(([k, v]) => {
      const value = v === null || v === undefined ? "-" : typeof v === "object" ? JSON.stringify(v) : String(v);
      return `${k}=${value}`;
    })
    .join("  ");
}

function AuditView() {
  const [items, setItems] = useState<AuditLogRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [action, setAction] = useState("");
  const [actionDraft, setActionDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects({ limit: 100 })
      .then((p) => setProjects(p.items))
      .catch(() => {});
  }, []);

  const load = useCallback(() => {
    listAuditLogs({
      project_id: projectId || undefined,
      action: action || undefined,
      limit: PAGE_SIZE,
      offset,
    })
      .then((p) => { setItems(p.items); setTotal(p.total); setError(null); })
      .catch((e) => setError(e.message));
  }, [projectId, action, offset]);
  useEffect(load, [load]);

  function applyAction(e: React.FormEvent) {
    e.preventDefault();
    setOffset(0);
    setAction(actionDraft.trim());
  }

  const projectName = (id: string | null) => {
    if (!id) return "-";
    return projects.find((p) => p.id === id)?.name ?? id.slice(0, 8);
  };

  return (
    <>
      <div className="flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-semibold">Audit log</h1>
          <p className="mt-1 text-sm text-muted">
            Every change recorded by the app: uploads, dependencies, validation runs, acknowledgements.
          </p>
        </div>
      </div>

      <ErrorNote message={error} />

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <select
          aria-label="Filter by project"
          className="rounded border border-line bg-white px-3 py-1.5 text-sm"
          value={projectId}
          onChange={(e) => { setProjectId(e.target.value); setOffset(0); }}
        >
          <option value="">All projects</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>

        <form onSubmit={applyAction} className="flex items-center gap-2">
          <input
            aria-label="Filter by action"
            placeholder="e.g. dependency.created"
            value={actionDraft}
            onChange={(e) => setActionDraft(e.target.value)}
            className="rounded border border-line bg-white px-3 py-1.5 text-sm"
          />
          <button type="submit" className={btnSecondary}>Filter</button>
          {action && (
            <button type="button" className={btnSecondary}
                    onClick={() => { setAction(""); setActionDraft(""); setOffset(0); }}>
              Clear
            </button>
          )}
        </form>
      </div>

      {items.length === 0 ? (
        <p className="mt-6 text-sm text-muted">No entries match these filters.</p>
      ) : (
        <table className="mt-4 w-full border border-line bg-white text-sm">
          <thead className="border-b border-line bg-paper text-left text-muted">
            <tr>
              <th className="px-3 py-2 font-medium">When</th>
              <th className="px-3 font-medium">User</th>
              <th className="px-3 font-medium">Action</th>
              <th className="px-3 font-medium">Entity</th>
              <th className="px-3 font-medium">Project</th>
              <th className="px-3 font-medium">Detail</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.id} className="border-b border-line align-top last:border-0">
                <td className="whitespace-nowrap px-3 py-2 text-muted">{formatDate(row.created_at)}</td>
                <td className="px-3 py-2">{row.user_email}</td>
                <td className="px-3 py-2 font-mono text-xs">{row.action}</td>
                <td className="px-3 py-2">
                  <span className="text-muted">{row.entity_type}</span>
                  {row.entity_id && <div className="font-mono text-xs text-muted">{row.entity_id.slice(0, 8)}</div>}
                </td>
                <td className="px-3 py-2">
                  {row.project_id ? (
                    <Link href={`/projects/${row.project_id}`} className="text-steel hover:underline">
                      {projectName(row.project_id)}
                    </Link>
                  ) : "-"}
                </td>
                <td className="px-3 py-2 font-mono text-xs text-muted break-all">{formatDetail(row.detail)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Pager total={total} limit={PAGE_SIZE} offset={offset} onChange={setOffset} />
    </>
  );
}

export default function AuditPage() {
  return <AppShell><AuditView /></AppShell>;
}