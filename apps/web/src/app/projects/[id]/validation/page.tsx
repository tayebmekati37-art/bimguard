"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppShell, useUser } from "@/components/AppShell";
import { ErrorNote, Field, Modal, Pager, SeverityBadge, btnPrimary, btnSecondary, inputCls } from "@/components/ui";
import {
  acknowledgeIssue, getLatestRun, getProject, listIssues, revokeAcknowledgement, runValidation,
  ApiError, type Page, type Project, type ReadinessStatus, type ValidationIssue, type ValidationRun,
} from "@/lib/api";
import { SEVERITIES, formatDate } from "@/lib/labels";

const PAGE_SIZE = 20;
const BANNER: Record<ReadinessStatus, { title: string; tone: string; text: string }> = {
  BLOCKED: { title: "NOT READY FOR ISSUE", tone: "border-status-critical bg-status-critical/5 text-status-critical", text: "Resolve the blocking issues below, then validate again." },
  READY_WITH_WARNINGS: { title: "READY FOR ISSUE, WITH WARNINGS", tone: "border-status-warn bg-status-warn/5 text-status-warn", text: "Nothing blocks the release. Review the remaining issues or acknowledge them with a reason." },
  READY: { title: "READY FOR ISSUE", tone: "border-status-ok bg-status-ok/5 text-status-ok", text: "No open issues. Accepted risks are listed in the report." },
};
const WHERE: Record<string, { label: string; path: string }> = {
  dependency: { label: "Open dependencies", path: "dependencies" }, consistency: { label: "Open impact analysis", path: "impact" },
};

function AcknowledgeDialog({ issue, onClose, onDone }: { issue: ValidationIssue; onClose: () => void; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal title="Acknowledge issue" onClose={onClose}>
      <p className="mt-3 text-sm">{issue.message}</p>
      <p className="mt-3 rounded bg-paper px-3 py-2 text-xs text-muted">Acknowledging accepts the risk, it does not fix it. The reason is recorded in the audit log and the report. It only applies while the evidence stays the same: a new revision brings the issue back.</p>
      <form onSubmit={async (e) => { e.preventDefault(); setBusy(true); setError(null);
        try { await acknowledgeIssue(issue.id, note.trim()); onDone(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }}>
        <Field label="Reason (at least 5 characters)"><textarea className={inputCls} rows={3} value={note} onChange={(e) => setNote(e.target.value)} autoFocus /></Field>
        <ErrorNote message={error} />
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className={btnSecondary} onClick={onClose}>Cancel</button>
          <button type="submit" className={btnPrimary} disabled={busy || note.trim().length < 5}>Acknowledge</button>
        </div>
      </form>
    </Modal>
  );
}

function ValidationView() {
  const { id } = useParams<{ id: string }>();
  const user = useUser();
  const [project, setProject] = useState<Project | null>(null);
  const [run, setRun] = useState<ValidationRun | null>(null);
  const [none, setNone] = useState(false);
  const [issues, setIssues] = useState<Page<ValidationIssue> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [acknowledging, setAcknowledging] = useState<ValidationIssue | null>(null);

  const loadRun = useCallback(() => {
    getProject(id).then(setProject).catch((e) => setError(e.message));
    getLatestRun(id).then((r) => { setRun(r); setNone(false); })
      .catch((e: ApiError) => (e.status === 404 ? setNone(true) : setError(e.message)));
  }, [id]);
  useEffect(loadRun, [loadRun]);
  const loadIssues = useCallback(() => {
    if (!run) return;
    listIssues(run.id, { severity, status, limit: PAGE_SIZE, offset }).then(setIssues).catch((e) => setError(e.message));
  }, [run, severity, status, offset]);
  useEffect(loadIssues, [loadIssues]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  if (error && !project) return <><Link href={`/projects/${id}`} className="text-sm text-steel hover:underline">Back to project</Link><ErrorNote message={error} /></>;
  if (!project) return <p className="text-muted">Loading</p>;

  const canRun = user.role !== "viewer";
  const canAck = user.role === "admin" || user.role === "bim_coordinator" || user.role === "reviewer";
  const s = run?.summary ?? {};
  return (
    <>
      <Link href={`/projects/${id}`} className="text-sm text-steel hover:underline">Back to {project.name}</Link>
      <div className="mt-3 flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-semibold">Validate for issue</h1>
          <p className="mt-1 text-sm text-muted">Checks revisions, dependencies, shared values, metadata, naming and approvals against the project&apos;s rules.</p>
        </div>
        {canRun && <button className={btnPrimary} disabled={busy} onClick={() => act(async () => { setRun(await runValidation(id)); setNone(false); setOffset(0); })}>
          {busy ? "Validating" : "Validate for issue"}</button>}
      </div>
      <ErrorNote message={error} />

      {none && (
        <div className="mt-6 rounded border border-dashed border-line bg-white p-8">
          <p className="font-medium">This project has not been validated yet.</p>
          <p className="mt-1 text-sm text-muted">{canRun ? "Run the validation to see whether it can be issued." : "Ask an engineer or reviewer to run the validation."}</p>
        </div>
      )}

      {run && (
        <>
          <section className={`mt-6 rounded border-2 p-5 ${BANNER[run.status].tone}`} aria-label="Readiness">
            <p className="text-2xl font-semibold tracking-tight">{BANNER[run.status].title}</p>
            <p className="mt-1 text-sm text-ink">{BANNER[run.status].text}</p>
            <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-ink">
              {SEVERITIES.map((sev) => (
                <span key={sev} className="flex items-center gap-1.5"><SeverityBadge severity={sev} /><span className="text-lg font-semibold">{s.open_by_severity?.[sev] ?? 0}</span></span>))}
              <span className="text-sm text-muted">{s.acknowledged ?? 0} acknowledged</span>
              <span className="text-sm text-muted">{s.documents_checked ?? 0} documents checked</span>
            </div>
            <p className="mt-3 text-xs text-muted">
              Validated {formatDate(run.created_at)} by {run.created_by_name} in {run.duration_ms} ms. Open issues at {s.blocking_severity?.toLowerCase()} or above block the release
              (<Link href="/rules" className="text-steel hover:underline">release policy</Link>). If the project changed since, validate again.
            </p>
            {(s.documents_checked ?? 0) === 0 && <p className="mt-2 text-sm">This project has no documents yet, so there was nothing to check.</p>}
          </section>

          <div className="mt-6 flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted">Severity</span>
            <button className={`${btnSecondary} ${severity === "" ? "border-steel bg-steel-light" : ""}`} onClick={() => { setSeverity(""); setOffset(0); }}>All</button>
            {SEVERITIES.map((sev) => <button key={sev} aria-pressed={severity === sev} className={`${btnSecondary} ${severity === sev ? "border-steel bg-steel-light" : ""}`}
              onClick={() => { setSeverity(severity === sev ? "" : sev); setOffset(0); }}>{sev.charAt(0) + sev.slice(1).toLowerCase()}</button>)}
            <select aria-label="Status filter" className="ml-3 rounded border border-line bg-white px-3 py-1.5 text-sm" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
              <option value="">Open and acknowledged</option><option value="open">Open</option><option value="acknowledged">Acknowledged</option>
            </select>
          </div>

          {issues && issues.items.length === 0 && (
            <p className="mt-4 rounded border border-line bg-white p-4 text-sm">{(s.total ?? 0) === 0 ? "No issues were found." : "No issues match these filters."}</p>
          )}
          <ul className="mt-4 space-y-3">
            {issues?.items.map((i) => (
              <li key={i.id} className={`rounded border bg-white p-4 ${i.status === "acknowledged" ? "border-line opacity-80" : "border-line"}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <SeverityBadge severity={i.severity} />
                  {i.document_number && <span className="font-mono text-sm font-medium">{i.document_number}</span>}
                  {i.element_tag && <span className="font-mono text-xs text-muted">{i.element_tag}</span>}
                  <span className="font-medium">{i.title}</span>
                  <span className="ml-auto text-xs text-muted">{i.rule_name}</span>
                </div>
                <p className="mt-2 text-sm">{i.message}</p>
                <p className="mt-2 text-sm"><span className="font-medium">What to do: </span>{i.recommended_action}</p>
                {i.status === "acknowledged" && (
                  <p className="mt-2 rounded bg-paper px-3 py-2 text-xs">Acknowledged by {i.acknowledged_by_name}{i.acknowledged_at ? `, ${formatDate(i.acknowledged_at)}` : ""}: {i.acknowledgement_note}</p>
                )}
                <div className="mt-3 flex flex-wrap gap-2">
                  {WHERE[i.category] && <Link href={`/projects/${id}/${WHERE[i.category].path}`} className={`${btnSecondary} inline-block`}>{WHERE[i.category].label}</Link>}
                  {!WHERE[i.category] && <Link href={`/projects/${id}`} className={`${btnSecondary} inline-block`}>Open documents</Link>}
                  {canAck && i.status === "open" && i.severity !== "CRITICAL" && <button className={btnSecondary} onClick={() => setAcknowledging(i)}>Acknowledge</button>}
                  {canAck && i.status === "acknowledged" && <button className={btnSecondary} disabled={busy} onClick={() => act(async () => { await revokeAcknowledgement(i.id); loadRun(); })}>Revoke acknowledgement</button>}
                  {i.severity === "CRITICAL" && i.status === "open" && <span className="self-center text-xs text-muted">Critical issues must be resolved; they cannot be acknowledged.</span>}
                </div>
              </li>
            ))}
          </ul>
          {issues && <Pager total={issues.total} limit={issues.limit} offset={issues.offset} onChange={setOffset} />}
        </>
      )}

      {acknowledging && <AcknowledgeDialog issue={acknowledging} onClose={() => setAcknowledging(null)} onDone={() => { setAcknowledging(null); loadRun(); }} />}
    </>
  );
}

export default function ValidationPage() {
  return <AppShell><ValidationView /></AppShell>;
}
