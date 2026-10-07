"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AppShell, useUser } from "@/components/AppShell";
import { ErrorNote, Field, Modal, Pager, StatusBadge, btnPrimary, btnSecondary, inputCls, useDebounced } from "@/components/ui";
import { createProject, listProjects, type Page, type Project } from "@/lib/api";
import { can, formatDate } from "@/lib/labels";

const PAGE_SIZE = 20;

function NewProjectDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [client, setClient] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await createProject({ name, client, description }); onCreated(); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <Modal title="New project" onClose={onClose}>
      <form onSubmit={submit}>
        <Field label="Project name"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} required autoFocus /></Field>
        <Field label="Client"><input className={inputCls} value={client} onChange={(e) => setClient(e.target.value)} /></Field>
        <Field label="Description"><textarea className={inputCls} rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <ErrorNote message={error} />
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className={btnSecondary} onClick={onClose}>Cancel</button>
          <button type="submit" className={btnPrimary} disabled={busy || !name.trim()}>{busy ? "Creating" : "Create project"}</button>
        </div>
      </form>
    </Modal>
  );
}

function ProjectList() {
  const user = useUser();
  const [data, setData] = useState<Page<Project> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("active");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const q = useDebounced(search);

  const load = useCallback(() => {
    listProjects({ status: status === "all" ? undefined : status, q, limit: PAGE_SIZE, offset })
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(e.message));
  }, [status, q, offset]);

  useEffect(load, [load]);

  return (
    <>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Projects</h1>
        {can.manageProjects(user.role) && <button className={btnPrimary} onClick={() => setCreating(true)}>New project</button>}
      </div>

      <div className="mt-6 flex gap-3">
        <input aria-label="Search projects" placeholder="Search by name or client" className="w-72 rounded border border-line bg-white px-3 py-2 text-sm"
               value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} />
        <select aria-label="Status filter" className="rounded border border-line bg-white px-3 py-2 text-sm" value={status}
                onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
          <option value="active">Active</option><option value="archived">Archived</option><option value="all">All</option>
        </select>
      </div>

      <ErrorNote message={error} />
      {!data && !error && <p className="mt-6 text-muted">Loading</p>}

      {data && data.items.length === 0 && (
        <div className="mt-6 rounded border border-dashed border-line bg-white p-8">
          <p className="font-medium">{q || status !== "active" ? "No projects match these filters." : "No projects yet."}</p>
          <p className="mt-1 text-sm text-muted">
            {can.manageProjects(user.role) ? "Create a project to start registering documents and revisions."
              : "Ask a BIM coordinator or admin to create a project."}
          </p>
        </div>
      )}

      {data && data.items.length > 0 && (
        <>
          <table className="mt-4 w-full border border-line bg-white text-sm">
            <thead className="border-b border-line bg-paper text-left text-muted">
              <tr><th className="px-3 py-2 font-medium">Project</th><th className="px-3 py-2 font-medium">Client</th>
                  <th className="px-3 py-2 font-medium">Documents</th><th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Updated</th></tr>
            </thead>
            <tbody>
              {data.items.map((p) => (
                <tr key={p.id} className="border-b border-line last:border-0 hover:bg-steel-light/40">
                  <td className="px-3 py-2"><Link href={`/projects/${p.id}`} className="font-medium text-steel hover:underline">{p.name}</Link></td>
                  <td className="px-3 py-2">{p.client || <span className="text-muted">None</span>}</td>
                  <td className="px-3 py-2">{p.document_count}</td>
                  <td className="px-3 py-2"><StatusBadge status={p.status} /></td>
                  <td className="px-3 py-2 text-muted">{formatDate(p.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager total={data.total} limit={data.limit} offset={data.offset} onChange={setOffset} />
        </>
      )}

      {creating && <NewProjectDialog onClose={() => setCreating(false)} onCreated={() => { setCreating(false); load(); }} />}
    </>
  );
}

export default function ProjectsPage() {
  return <AppShell><ProjectList /></AppShell>;
}
