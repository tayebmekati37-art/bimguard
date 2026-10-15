"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppShell, useUser } from "@/components/AppShell";
import { ElementsDialog } from "@/components/ElementsDialog";
import { HealthPanel } from "@/components/HealthPanel";
import { ErrorNote, Field, Modal, Pager, StatusBadge, btnDanger, btnPrimary, btnSecondary, inputCls, useDebounced } from "@/components/ui";
import {
  createDocument, deleteProject, downloadRevision, getProject, getProjectHealth, listDocuments, listRevisions, reextractRevision, setRevisionStatus,
  updateProject, uploadRevision, type Discipline, type DocumentRecord, type Page, type Project, type ProjectHealth, type Revision, type RevisionStatus,
} from "@/lib/api";
import { DISCIPLINES, FILE_TYPES, STATUSES, STATUS_TRANSITIONS, can, formatDate, formatSize } from "@/lib/labels";

const PAGE_SIZE = 25;

function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(fn: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return { busy, error, run };
}

function EditProjectDialog({ project, onClose, onSaved }: { project: Project; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(project.name);
  const [client, setClient] = useState(project.client);
  const [description, setDescription] = useState(project.description);
  const { busy, error, run } = useAction();
  return (
    <Modal title="Edit project" onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); run(async () => { await updateProject(project.id, { name, client, description }); onSaved(); }); }}>
        <Field label="Project name"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} required /></Field>
        <Field label="Client"><input className={inputCls} value={client} onChange={(e) => setClient(e.target.value)} /></Field>
        <Field label="Description"><textarea className={inputCls} rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <ErrorNote message={error} />
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className={btnSecondary} onClick={onClose}>Cancel</button>
          <button type="submit" className={btnPrimary} disabled={busy || !name.trim()}>Save changes</button>
        </div>
      </form>
    </Modal>
  );
}

function DeleteProjectDialog({ project, onClose, onDeleted }: { project: Project; onClose: () => void; onDeleted: () => void }) {
  const [typed, setTyped] = useState("");
  const { busy, error, run } = useAction();
  return (
    <Modal title="Delete project" onClose={onClose}>
      <p className="mt-3 text-sm">
        This permanently deletes <strong>{project.name}</strong>, its {project.document_count} documents, all revisions and
        uploaded files. The audit log keeps a record that the project was deleted. Archive the project instead if you may need it again.
      </p>
      <Field label={`Type the project name to confirm`}><input className={inputCls} value={typed} onChange={(e) => setTyped(e.target.value)} /></Field>
      <ErrorNote message={error} />
      <div className="mt-6 flex justify-end gap-2">
        <button className={btnSecondary} onClick={onClose}>Cancel</button>
        <button className={btnDanger} disabled={busy || typed !== project.name}
                onClick={() => run(async () => { await deleteProject(project.id); onDeleted(); })}>Delete project</button>
      </div>
    </Modal>
  );
}

function AddDocumentDialog({ projectId, onClose, onCreated }: { projectId: string; onClose: () => void; onCreated: () => void }) {
  const [number, setNumber] = useState("");
  const [name, setName] = useState("");
  const [discipline, setDiscipline] = useState<Discipline>("architecture");
  const { busy, error, run } = useAction();
  return (
    <Modal title="Add document" onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); run(async () => { await createDocument(projectId, { document_number: number.trim(), name: name.trim(), discipline }); onCreated(); }); }}>
        <Field label="Document number" hint="Letters, numbers, dot, dash. Example: A-101">
          <input className={`${inputCls} font-mono`} value={number} onChange={(e) => setNumber(e.target.value)} required autoFocus />
        </Field>
        <Field label="Name"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Level 2 Floor Plan" required /></Field>
        <Field label="Discipline">
          <select className={inputCls} value={discipline} onChange={(e) => setDiscipline(e.target.value as Discipline)}>
            {Object.entries(DISCIPLINES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <ErrorNote message={error} />
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className={btnSecondary} onClick={onClose}>Cancel</button>
          <button type="submit" className={btnPrimary} disabled={busy || !number.trim() || !name.trim()}>Add document</button>
        </div>
      </form>
    </Modal>
  );
}

function UploadRevisionDialog({ doc, onClose, onUploaded }: { doc: DocumentRecord; onClose: () => void; onUploaded: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState("");
  const [status, setStatus] = useState<RevisionStatus>("draft");
  const [number, setNumber] = useState("");
  const { busy, error, run } = useAction();
  const next = (doc.current_revision_number ?? 0) + 1;
  return (
    <Modal title={`Upload revision for ${doc.document_number}`} onClose={onClose}>
      <form onSubmit={(e) => {
        e.preventDefault();
        if (!file) return;
        const form = new FormData();
        form.append("file", file);
        form.append("change_summary", summary);
        form.append("status", status);
        if (number.trim()) form.append("revision_number", number.trim());
        run(async () => { await uploadRevision(doc.id, form); onUploaded(); });
      }}>
        <Field label="File" hint="IFC, JSON, PDF, CSV, XLSX, DWG or RVT. Maximum 50 MB.">
          <input type="file" className={inputCls} accept=".ifc,.json,.pdf,.csv,.xlsx,.dwg,.rvt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
        </Field>
        <Field label="Revision number" hint={`Leave empty to use v${next}. Must be higher than the current revision.`}>
          <input className={inputCls} inputMode="numeric" pattern="[0-9]*" value={number} onChange={(e) => setNumber(e.target.value)} placeholder={`v${next}`} />
        </Field>
        <Field label="Status">
          <select className={inputCls} value={status} onChange={(e) => setStatus(e.target.value as RevisionStatus)}>
            {(Object.keys(STATUSES) as RevisionStatus[]).filter((s) => s !== "superseded").map((s) => <option key={s} value={s}>{STATUSES[s]}</option>)}
          </select>
        </Field>
        <Field label="Change summary"><textarea className={inputCls} rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="What changed in this revision" /></Field>
        <ErrorNote message={error} />
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className={btnSecondary} onClick={onClose}>Cancel</button>
          <button type="submit" className={btnPrimary} disabled={busy || !file}>{busy ? "Uploading" : "Upload revision"}</button>
        </div>
      </form>
    </Modal>
  );
}

function HistoryDialog({ doc, onClose, onChanged }: { doc: DocumentRecord; onClose: () => void; onChanged: () => void }) {
  const user = useUser();
  const [revisions, setRevisions] = useState<Revision[] | null>(null);
  const { busy, error, run } = useAction();
  const [viewing, setViewing] = useState<Revision | null>(null);
  const load = useCallback(() => { listRevisions(doc.id).then(setRevisions).catch(() => setRevisions([])); }, [doc.id]);
  useEffect(load, [load]);
  const processing = revisions?.some((r) => r.extraction_status === "pending") ?? false;
  useEffect(() => {
    if (!processing) return;
    const timer = setTimeout(load, 1500);
    return () => clearTimeout(timer);
  }, [processing, revisions, load]);

  function allowed(rev: Revision): RevisionStatus[] {
    if (rev.revision_number !== doc.current_revision_number) return [];
    const options = STATUS_TRANSITIONS[rev.status];
    return user.role === "engineer" ? options.filter((s) => s === "in_review") : options;
  }

  return (
    <>
    <Modal title={`${doc.document_number} revision history`} onClose={onClose} wide>
      <p className="mt-1 text-sm text-muted">History is immutable. Uploading a new revision supersedes the previous one.</p>
      <ErrorNote message={error} />
      {!revisions && <p className="mt-4 text-muted">Loading</p>}
      {revisions && revisions.length === 0 && <p className="mt-4 text-sm">No revisions uploaded yet.</p>}
      {revisions && revisions.length > 0 && (
        <table className="mt-4 w-full text-sm">
          <thead className="border-b border-line text-left text-muted">
            <tr><th className="py-2 font-medium">Rev</th><th className="font-medium">Status</th><th className="font-medium">File</th><th className="font-medium">Model data</th>
                <th className="font-medium">Uploaded</th><th className="font-medium">Summary</th><th /></tr>
          </thead>
          <tbody>
            {revisions.map((r) => (
              <tr key={r.id} className="border-b border-line align-top last:border-0">
                <td className="py-2 font-mono">v{r.revision_number}</td>
                <td><StatusBadge status={r.status} /></td>
                <td>{r.original_filename}<div className="text-xs text-muted">{formatSize(r.file_size)} · SHA-256 {r.checksum.slice(0, 10)}</div></td>
                <td className="text-xs">
                  {r.extraction_status === "pending" && <span className="text-status-warn">Processing</span>}
                  {r.extraction_status === "ok" && <span>{r.element_count} elements<div className="text-muted">{r.model_schema}</div></span>}
                  {r.extraction_status === "failed" && <span className="text-status-critical">Extraction failed<div className="max-w-[12rem] text-muted">{r.extraction_message}</div></span>}
                  {r.extraction_status === "unsupported" && <span className="text-muted">No model data</span>}
                </td>
                <td>{formatDate(r.uploaded_at)}<div className="text-xs text-muted">{r.created_by_name}</div></td>
                <td className="max-w-[14rem]">{r.change_summary || <span className="text-muted">None</span>}</td>
                <td className="space-y-1 text-right">
                  {r.extraction_status === "ok" && <button className={btnSecondary} onClick={() => setViewing(r)}>Elements</button>}
                  {r.extraction_status === "ok" && r.previous_revision_id && (
                    <Link href={`/revisions/${r.id}/compare`} className={`${btnSecondary} ml-1 inline-block`}>Changes</Link>
                  )}
                  {can.editDocuments(user.role) && (r.extraction_status === "failed" || r.extraction_status === "pending") && (
                    <button className={`${btnSecondary} ml-1`} disabled={busy}
                            onClick={() => run(async () => { await reextractRevision(r.id); load(); })}>Retry extraction</button>
                  )}
                  <button className={`${btnSecondary} ml-1`} onClick={() => run(() => downloadRevision(r))}>Download</button>
                  {can.changeStatus(user.role) && allowed(r).map((s) => (
                    <button key={s} className={`${btnSecondary} ml-1`} disabled={busy}
                            onClick={() => run(async () => { await setRevisionStatus(r.id, s); load(); onChanged(); })}>
                      Mark {STATUSES[s].toLowerCase()}
                    </button>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Modal>
    {viewing && <ElementsDialog docNumber={doc.document_number} revision={viewing} onClose={() => setViewing(null)} />}
    </>
  );
}

function ProjectView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const user = useUser();
  const [project, setProject] = useState<Project | null>(null);
  const [docs, setDocs] = useState<Page<DocumentRecord> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [discipline, setDiscipline] = useState("");
  const [status, setStatus] = useState("");
  const [fileType, setFileType] = useState("");
  const [revisionFilter, setRevisionFilter] = useState("");
  const [since, setSince] = useState("");
  const [health, setHealth] = useState<ProjectHealth | null>(null);
  const [offset, setOffset] = useState(0);
  const [dialog, setDialog] = useState<
    | { kind: "edit" | "delete" | "add" }
    | { kind: "upload" | "history"; doc: DocumentRecord }
    | null
  >(null);
  const q = useDebounced(search);
  const archive = useAction();
  useEffect(() => { const initial = new URLSearchParams(window.location.search).get("q"); if (initial) setSearch(initial); }, []);

  const loadProject = useCallback(() => { getProject(id).then(setProject).catch((e) => setError(e.message)); }, [id]);
  const loadDocs = useCallback(() => {
    listDocuments(id, { discipline, status, q, file_type: fileType, revision: revisionFilter, modified_since: since ? `${since}T00:00:00Z` : "", limit: PAGE_SIZE, offset })
      .then(setDocs).catch((e) => setError(e.message));
  }, [id, discipline, status, q, fileType, revisionFilter, since, offset]);
  const loadHealth = useCallback(() => { getProjectHealth(id).then(setHealth).catch(() => setHealth(null)); }, [id]);
  useEffect(loadProject, [loadProject]);
  useEffect(loadDocs, [loadDocs]);
  useEffect(loadHealth, [loadHealth]);
  const refresh = () => { loadProject(); loadDocs(); loadHealth(); };

  if (error) return <><Link href="/projects" className="text-sm text-steel hover:underline">Back to projects</Link><ErrorNote message={error} /></>;
  if (!project) return <p className="text-muted">Loading</p>;

  const archived = project.status === "archived";
  const canManage = can.manageProjects(user.role);
  const canEdit = can.editDocuments(user.role) && !archived;
  const filtersOn = Boolean(q || discipline || status || fileType || revisionFilter || since);

  return (
    <>
      <Link href="/projects" className="text-sm text-steel hover:underline">Back to projects</Link>
      <div className="mt-3 flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-semibold">{project.name} <StatusBadge status={project.status} /></h1>
          <p className="mt-1 text-sm text-muted">{project.client || "No client set"} · {project.document_count} documents · Updated {formatDate(project.updated_at)}</p>
          {project.description && <p className="mt-3 max-w-2xl text-sm">{project.description}</p>}
        </div>
        <div className="flex shrink-0 gap-2">
          <Link href={`/projects/${project.id}/validation`} className={`${btnPrimary} inline-block`}>Validate for issue</Link>
          <Link href={`/projects/${project.id}/impact`} className={`${btnSecondary} inline-block`}>Impact</Link>
          <Link href={`/projects/${project.id}/dependencies`} className={`${btnSecondary} inline-block`}>Dependencies</Link>
          <Link href={`/projects/${project.id}/ask`} className={`${btnSecondary} inline-block`}>Ask</Link>
          <Link href={`/projects/${project.id}/reports`} className={`${btnSecondary} inline-block`}>Reports</Link>
          <Link href={`/audit?project=${project.id}`} className={`${btnSecondary} inline-block`}>Audit</Link>
          {canManage && (<>
            <button className={btnSecondary} onClick={() => setDialog({ kind: "edit" })}>Edit</button>
            <button className={btnSecondary} disabled={archive.busy}
                    onClick={() => archive.run(async () => { await updateProject(project.id, { status: archived ? "active" : "archived" }); refresh(); })}>
              {archived ? "Restore" : "Archive"}
            </button>
            {can.deleteProjects(user.role) && <button className={btnSecondary} onClick={() => setDialog({ kind: "delete" })}>Delete</button>}
          </>)}
        </div>
      </div>
      <ErrorNote message={archive.error} />
      {archived && <p className="mt-4 rounded border border-line bg-white px-3 py-2 text-sm">This project is archived. Restore it to add documents or upload revisions.</p>}

      {health && <HealthPanel health={health} />}

      <div className="mt-8 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Documents</h2>
        {canEdit && <button className={btnPrimary} onClick={() => setDialog({ kind: "add" })}>Add document</button>}
      </div>
      <div className="mt-3 flex flex-wrap gap-3">
        <input aria-label="Search documents" placeholder="Search number or name" className="w-64 rounded border border-line bg-white px-3 py-2 text-sm"
               value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} />
        <select aria-label="Discipline filter" className="rounded border border-line bg-white px-3 py-2 text-sm" value={discipline}
                onChange={(e) => { setDiscipline(e.target.value); setOffset(0); }}>
          <option value="">All disciplines</option>
          {Object.entries(DISCIPLINES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select aria-label="Status filter" className="rounded border border-line bg-white px-3 py-2 text-sm" value={status}
                onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
          <option value="">All statuses</option>
          {Object.entries(STATUSES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select aria-label="File type filter" className="rounded border border-line bg-white px-3 py-2 text-sm" value={fileType}
                onChange={(e) => { setFileType(e.target.value); setOffset(0); }}>
          <option value="">All file types</option>
          {FILE_TYPES.map((t) => <option key={t} value={t}>{t.toUpperCase()}</option>)}
        </select>
        <input aria-label="Revision filter" placeholder="Revision" inputMode="numeric" pattern="[0-9]*" className="w-24 rounded border border-line bg-white px-3 py-2 text-sm"
               value={revisionFilter} onChange={(e) => { setRevisionFilter(e.target.value.replace(/\D/g, "")); setOffset(0); }} />
        <label className="flex items-center gap-2 text-sm text-muted">Modified since
          <input type="date" aria-label="Modified since" className="rounded border border-line bg-white px-2 py-1.5 text-sm text-ink" value={since}
                 onChange={(e) => { setSince(e.target.value); setOffset(0); }} /></label>
      </div>

      {docs && docs.items.length === 0 && (
        <div className="mt-4 rounded border border-dashed border-line bg-white p-8">
          <p className="font-medium">{filtersOn ? "No documents match these filters." : "No documents in this project yet."}</p>
          {!filtersOn && <p className="mt-1 text-sm text-muted">{canEdit ? "Add a document, then upload its first revision." : "Documents appear here once an engineer adds them."}</p>}
        </div>
      )}

      {docs && docs.items.length > 0 && (
        <>
          <table className="mt-4 w-full border border-line bg-white text-sm">
            <thead className="border-b border-line bg-paper text-left text-muted">
              <tr><th className="px-3 py-2 font-medium">Number</th><th className="px-3 py-2 font-medium">Name</th>
                  <th className="px-3 py-2 font-medium">Discipline</th><th className="px-3 py-2 font-medium">Revision</th>
                  <th className="px-3 py-2 font-medium">Status</th><th className="px-3 py-2 font-medium">Author</th>
                  <th className="px-3 py-2 font-medium">Modified</th><th /></tr>
            </thead>
            <tbody>
              {docs.items.map((d) => (
                <tr key={d.id} className="border-b border-line last:border-0">
                  <td className="px-3 py-2 font-mono">{d.document_number}</td>
                  <td className="px-3 py-2">{d.name}</td>
                  <td className="px-3 py-2">{DISCIPLINES[d.discipline]}</td>
                  <td className="px-3 py-2 font-mono">{d.current_revision_number ? `v${d.current_revision_number}` : <span className="font-sans text-muted">None</span>}</td>
                  <td className="px-3 py-2"><StatusBadge status={d.status} /></td>
                  <td className="px-3 py-2">{d.author}</td>
                  <td className="px-3 py-2 text-muted">{formatDate(d.modified_at)}</td>
                  <td className="space-x-2 whitespace-nowrap px-3 py-2 text-right">
                    <button className={btnSecondary} onClick={() => setDialog({ kind: "history", doc: d })}>History</button>
                    {canEdit && <button className={btnSecondary} onClick={() => setDialog({ kind: "upload", doc: d })}>Upload revision</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager total={docs.total} limit={docs.limit} offset={docs.offset} onChange={setOffset} />
        </>
      )}

      {dialog?.kind === "edit" && <EditProjectDialog project={project} onClose={() => setDialog(null)} onSaved={() => { setDialog(null); refresh(); }} />}
      {dialog?.kind === "delete" && <DeleteProjectDialog project={project} onClose={() => setDialog(null)} onDeleted={() => router.replace("/projects")} />}
      {dialog?.kind === "add" && <AddDocumentDialog projectId={project.id} onClose={() => setDialog(null)} onCreated={() => { setDialog(null); refresh(); }} />}
      {dialog?.kind === "upload" && <UploadRevisionDialog doc={dialog.doc} onClose={() => setDialog(null)} onUploaded={() => { setDialog(null); refresh(); }} />}
      {dialog?.kind === "history" && <HistoryDialog doc={dialog.doc} onClose={() => setDialog(null)} onChanged={refresh} />}
    </>
  );
}

export default function ProjectPage() {
  return <AppShell><ProjectView /></AppShell>;
}
