"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppShell, useUser } from "@/components/AppShell";
import { ElementsDialog } from "@/components/ElementsDialog";
import { HealthPanel } from "@/components/HealthPanel";
import { ErrorNote, Field, Modal, Pager, StatusBadge, btnDanger, btnPrimary, btnSecondary, inputCls, useDebounced } from "@/components/ui";
import { useT } from "@/lib/i18n";
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
  const { t } = useT();
  const [name, setName] = useState(project.name);
  const [client, setClient] = useState(project.client);
  const [description, setDescription] = useState(project.description);
  const { busy, error, run } = useAction();
  return (
    <Modal title={t("project.editDialogTitle")} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); run(async () => { await updateProject(project.id, { name, client, description }); onSaved(); }); }}>
        <Field label={t("project.projectName")}><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} required /></Field>
        <Field label={t("project.clientLabel")}><input className={inputCls} value={client} onChange={(e) => setClient(e.target.value)} /></Field>
        <Field label={t("project.descriptionLabel")}><textarea className={inputCls} rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <ErrorNote message={error} />
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className={btnSecondary} onClick={onClose}>{t("action.cancel")}</button>
          <button type="submit" className={btnPrimary} disabled={busy || !name.trim()}>{t("project.saveChanges")}</button>
        </div>
      </form>
    </Modal>
  );
}

function DeleteProjectDialog({ project, onClose, onDeleted }: { project: Project; onClose: () => void; onDeleted: () => void }) {
  const { t } = useT();
  const [typed, setTyped] = useState("");
  const { busy, error, run } = useAction();
  return (
    <Modal title={t("project.deleteDialogTitle")} onClose={onClose}>
      <p className="mt-3 text-sm">
        <strong>{project.name}</strong>, {t("project.deleteWarningTail", { count: project.document_count })}
      </p>
      <Field label={t("project.deleteConfirmType")}><input className={inputCls} value={typed} onChange={(e) => setTyped(e.target.value)} /></Field>
      <ErrorNote message={error} />
      <div className="mt-6 flex justify-end gap-2">
        <button className={btnSecondary} onClick={onClose}>{t("action.cancel")}</button>
        <button className={btnDanger} disabled={busy || typed !== project.name}
                onClick={() => run(async () => { await deleteProject(project.id); onDeleted(); })}>{t("project.delete")}</button>
      </div>
    </Modal>
  );
}

function AddDocumentDialog({ projectId, onClose, onCreated }: { projectId: string; onClose: () => void; onCreated: () => void }) {
  const { t } = useT();
  const [number, setNumber] = useState("");
  const [name, setName] = useState("");
  const [discipline, setDiscipline] = useState<Discipline>("architecture");
  const { busy, error, run } = useAction();
  return (
    <Modal title={t("project.addDocumentDialogTitle")} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); run(async () => { await createDocument(projectId, { document_number: number.trim(), name: name.trim(), discipline }); onCreated(); }); }}>
        <Field label={t("project.docNumber")} hint={t("project.docNumberHint")}>
          <input className={`${inputCls} font-mono`} value={number} onChange={(e) => setNumber(e.target.value)} required autoFocus />
        </Field>
        <Field label={t("project.docName")}><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("project.docNamePlaceholder")} required /></Field>
        <Field label={t("project.discipline")}>
          <select className={inputCls} value={discipline} onChange={(e) => setDiscipline(e.target.value as Discipline)}>
            {Object.keys(DISCIPLINES).map((k) => <option key={k} value={k}>{t(`discipline.${k}`)}</option>)}
          </select>
        </Field>
        <ErrorNote message={error} />
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className={btnSecondary} onClick={onClose}>{t("action.cancel")}</button>
          <button type="submit" className={btnPrimary} disabled={busy || !number.trim() || !name.trim()}>{t("project.addDocument")}</button>
        </div>
      </form>
    </Modal>
  );
}

function UploadRevisionDialog({ doc, onClose, onUploaded }: { doc: DocumentRecord; onClose: () => void; onUploaded: () => void }) {
  const { t } = useT();
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState("");
  const [status, setStatus] = useState<RevisionStatus>("draft");
  const [number, setNumber] = useState("");
  const { busy, error, run } = useAction();
  const next = (doc.current_revision_number ?? 0) + 1;
  return (
    <Modal title={t("project.uploadTitle", { number: doc.document_number })} onClose={onClose}>
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
        <Field label={t("project.file")} hint={t("project.fileHint")}>
          <input type="file" className={inputCls} accept=".ifc,.json,.pdf,.csv,.xlsx,.dwg,.rvt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
        </Field>
        <Field label={t("project.revisionNumber")} hint={t("project.revisionNumberHint", { next })}>
          <input className={inputCls} inputMode="numeric" pattern="[0-9]*" value={number} onChange={(e) => setNumber(e.target.value)} placeholder={`v${next}`} />
        </Field>
        <Field label={t("project.revisionStatus")}>
          <select className={inputCls} value={status} onChange={(e) => setStatus(e.target.value as RevisionStatus)}>
            {(Object.keys(STATUSES) as RevisionStatus[]).filter((s) => s !== "superseded").map((s) => (
              <option key={s} value={s}>{t(`status.${s}`)}</option>
            ))}
          </select>
        </Field>
        <Field label={t("project.changeSummary")}>
          <textarea className={inputCls} rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} placeholder={t("project.changeSummaryPlaceholder")} />
        </Field>
        <ErrorNote message={error} />
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className={btnSecondary} onClick={onClose}>{t("action.cancel")}</button>
          <button type="submit" className={btnPrimary} disabled={busy || !file}>
            {busy ? t("project.uploading") : t("project.upload")}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function HistoryDialog({ doc, onClose, onChanged }: { doc: DocumentRecord; onClose: () => void; onChanged: () => void }) {
  const user = useUser();
  const { t } = useT();
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
    <Modal title={t("project.historyTitle", { number: doc.document_number })} onClose={onClose} wide>
      <p className="mt-1 text-sm text-muted">{t("project.historyImmutable")}</p>
      <ErrorNote message={error} />
      {!revisions && <p className="mt-4 text-muted">{t("common.loading")}</p>}
      {revisions && revisions.length === 0 && <p className="mt-4 text-sm">{t("project.noRevisions")}</p>}
      {revisions && revisions.length > 0 && (
        <table className="mt-4 w-full text-sm">
          <thead className="border-b border-line text-left text-muted">
            <tr>
              <th className="py-2 font-medium">{t("project.colRev")}</th>
              <th className="font-medium">{t("project.colStatus")}</th>
              <th className="font-medium">{t("project.colFile")}</th>
              <th className="font-medium">{t("project.colModelData")}</th>
              <th className="font-medium">{t("project.colUploaded")}</th>
              <th className="font-medium">{t("project.colSummary")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {revisions.map((r) => (
              <tr key={r.id} className="border-b border-line align-top last:border-0">
                <td className="py-2 font-mono">v{r.revision_number}</td>
                <td><StatusBadge status={r.status} /></td>
                <td>{r.original_filename}<div className="text-xs text-muted">{formatSize(r.file_size)} · SHA-256 {r.checksum.slice(0, 10)}</div></td>
                <td className="text-xs">
                  {r.extraction_status === "pending" && <span className="text-status-warn">{t("project.processing")}</span>}
                  {r.extraction_status === "ok" && <span>{t("project.elementsCount", { count: r.element_count ?? 0 })}<div className="text-muted">{r.model_schema}</div></span>}
                  {r.extraction_status === "failed" && <span className="text-status-critical">{t("project.extractionFailed")}<div className="max-w-[12rem] text-muted">{r.extraction_message}</div></span>}
                  {r.extraction_status === "unsupported" && <span className="text-muted">{t("project.noModelData")}</span>}
                </td>
                <td>{formatDate(r.uploaded_at)}<div className="text-xs text-muted">{r.created_by_name}</div></td>
                <td className="max-w-[14rem]">{r.change_summary || <span className="text-muted">{t("project.none")}</span>}</td>
                <td className="space-y-1 text-right">
                  {r.extraction_status === "ok" && <button className={btnSecondary} onClick={() => setViewing(r)}>{t("project.btnElements")}</button>}
                  {r.extraction_status === "ok" && r.previous_revision_id && (
                    <Link href={`/revisions/${r.id}/compare`} className={`${btnSecondary} ml-1 inline-block`}>{t("project.btnChanges")}</Link>
                  )}
                  {can.editDocuments(user.role) && (r.extraction_status === "failed" || r.extraction_status === "pending") && (
                    <button className={`${btnSecondary} ml-1`} disabled={busy}
                            onClick={() => run(async () => { await reextractRevision(r.id); load(); })}>{t("project.btnRetry")}</button>
                  )}
                  <button className={`${btnSecondary} ml-1`} onClick={() => run(() => downloadRevision(r))}>{t("action.download")}</button>
                  {can.changeStatus(user.role) && allowed(r).map((s) => (
                    <button key={s} className={`${btnSecondary} ml-1`} disabled={busy}
                            onClick={() => run(async () => { await setRevisionStatus(r.id, s); load(); onChanged(); })}>
                      {t("project.markStatus", { status: t(`status.${s}`) })}
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
  const { t } = useT();
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

  if (error) return <><Link href="/projects" className="text-sm text-steel hover:underline">{t("breadcrumb.backToProjects")}</Link><ErrorNote message={error} /></>;
  if (!project) return <p className="text-muted">{t("common.loading")}</p>;

  const archived = project.status === "archived";
  const canManage = can.manageProjects(user.role);
  const canEdit = can.editDocuments(user.role) && !archived;
  const filtersOn = Boolean(q || discipline || status || fileType || revisionFilter || since);

  return (
    <>
      <Link href="/projects" className="text-sm text-steel hover:underline">{t("breadcrumb.backToProjects")}</Link>
      <div className="mt-3 flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-semibold">{project.name} <StatusBadge status={project.status} /></h1>
          <p className="mt-1 text-sm text-muted">
            {project.client || t("project.noClientSet")} · {project.document_count} {t("project.documents")} · {t("project.updated")} {formatDate(project.updated_at)}
          </p>
          {project.description && <p className="mt-3 max-w-2xl text-sm">{project.description}</p>}
        </div>
        <div className="flex shrink-0 gap-2">
          <Link href={`/projects/${project.id}/validation`} className={`${btnPrimary} inline-block`}>{t("project.validateForIssue")}</Link>
          <Link href={`/projects/${project.id}/impact`} className={`${btnSecondary} inline-block`}>{t("project.impact")}</Link>
          <Link href={`/projects/${project.id}/dependencies`} className={`${btnSecondary} inline-block`}>{t("project.dependencies")}</Link>
          <Link href={`/projects/${project.id}/ask`} className={`${btnSecondary} inline-block`}>{t("project.ask")}</Link>
          <Link href={`/projects/${project.id}/reports`} className={`${btnSecondary} inline-block`}>{t("project.reports")}</Link>
          <Link href={`/audit?project=${project.id}`} className={`${btnSecondary} inline-block`}>{t("project.audit")}</Link>
          {canManage && (<>
            <button className={btnSecondary} onClick={() => setDialog({ kind: "edit" })}>{t("project.edit")}</button>
            <button className={btnSecondary} disabled={archive.busy}
                    onClick={() => archive.run(async () => { await updateProject(project.id, { status: archived ? "active" : "archived" }); refresh(); })}>
              {archived ? t("project.restore") : t("project.archive")}
            </button>
            {can.deleteProjects(user.role) && <button className={btnSecondary} onClick={() => setDialog({ kind: "delete" })}>{t("project.delete")}</button>}
          </>)}
        </div>
      </div>
      <ErrorNote message={archive.error} />
      {archived && <p className="mt-4 rounded border border-line bg-white px-3 py-2 text-sm">{t("project.archivedBanner")}</p>}

      {health && <HealthPanel health={health} />}

      <div className="mt-8 flex items-center justify-between">
        <h2 className="text-lg font-semibold">{t("project.documents")}</h2>
        {canEdit && <button className={btnPrimary} onClick={() => setDialog({ kind: "add" })}>{t("project.addDocument")}</button>}
      </div>
      <div className="mt-3 flex flex-wrap gap-3">
        <input aria-label={t("project.searchDocsAria")} placeholder={t("project.searchDocs")} className="w-64 rounded border border-line bg-white px-3 py-2 text-sm"
               value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} />
        <select aria-label={t("project.filterDisciplineAria")} className="rounded border border-line bg-white px-3 py-2 text-sm" value={discipline}
                onChange={(e) => { setDiscipline(e.target.value); setOffset(0); }}>
          <option value="">{t("project.filterDiscipline")}</option>
          {Object.keys(DISCIPLINES).map((k) => <option key={k} value={k}>{t(`discipline.${k}`)}</option>)}
        </select>
        <select aria-label={t("project.filterStatusAria")} className="rounded border border-line bg-white px-3 py-2 text-sm" value={status}
                onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
          <option value="">{t("project.filterStatus")}</option>
          {Object.keys(STATUSES).map((k) => <option key={k} value={k}>{t(`status.${k}`)}</option>)}
        </select>
        <select aria-label={t("project.filterFileTypeAria")} className="rounded border border-line bg-white px-3 py-2 text-sm" value={fileType}
                onChange={(e) => { setFileType(e.target.value); setOffset(0); }}>
          <option value="">{t("project.filterFileType")}</option>
          {FILE_TYPES.map((ft) => <option key={ft} value={ft}>{ft.toUpperCase()}</option>)}
        </select>
        <input aria-label={t("project.revisionFilterAria")} placeholder={t("project.revisionFilterPlaceholder")} inputMode="numeric" pattern="[0-9]*" className="w-24 rounded border border-line bg-white px-3 py-2 text-sm"
               value={revisionFilter} onChange={(e) => { setRevisionFilter(e.target.value.replace(/\D/g, "")); setOffset(0); }} />
        <label className="flex items-center gap-2 text-sm text-muted">{t("project.modifiedSince")}
          <input type="date" aria-label={t("project.modifiedSinceAria")} className="rounded border border-line bg-white px-2 py-1.5 text-sm text-ink" value={since}
                 onChange={(e) => { setSince(e.target.value); setOffset(0); }} /></label>
      </div>

      {docs && docs.items.length === 0 && (
        <div className="mt-4 rounded border border-dashed border-line bg-white p-8">
          <p className="font-medium">{filtersOn ? t("project.noMatchFilters") : t("project.noDocuments")}</p>
          {!filtersOn && <p className="mt-1 text-sm text-muted">{canEdit ? t("project.addFirstHint") : t("project.engineerHint")}</p>}
        </div>
      )}

      {docs && docs.items.length > 0 && (
        <>
          <table className="mt-4 w-full border border-line bg-white text-sm">
            <thead className="border-b border-line bg-paper text-left text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">{t("project.colNumber")}</th>
                <th className="px-3 py-2 font-medium">{t("project.colName")}</th>
                <th className="px-3 py-2 font-medium">{t("project.colDiscipline")}</th>
                <th className="px-3 py-2 font-medium">{t("project.colRevision")}</th>
                <th className="px-3 py-2 font-medium">{t("project.colStatus")}</th>
                <th className="px-3 py-2 font-medium">{t("project.colAuthor")}</th>
                <th className="px-3 py-2 font-medium">{t("project.colModified")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {docs.items.map((d) => (
                <tr key={d.id} className="border-b border-line last:border-0">
                  <td className="px-3 py-2 font-mono">{d.document_number}</td>
                  <td className="px-3 py-2">{d.name}</td>
                  <td className="px-3 py-2">{t(`discipline.${d.discipline}`)}</td>
                  <td className="px-3 py-2 font-mono">{d.current_revision_number ? `v${d.current_revision_number}` : <span className="font-sans text-muted">{t("project.none")}</span>}</td>
                  <td className="px-3 py-2"><StatusBadge status={d.status} /></td>
                  <td className="px-3 py-2">{d.author}</td>
                  <td className="px-3 py-2 text-muted">{formatDate(d.modified_at)}</td>
                  <td className="space-x-2 whitespace-nowrap px-3 py-2 text-right">
                    <button className={btnSecondary} onClick={() => setDialog({ kind: "history", doc: d })}>{t("project.history")}</button>
                    {canEdit && <button className={btnSecondary} onClick={() => setDialog({ kind: "upload", doc: d })}>{t("project.upload")}</button>}
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