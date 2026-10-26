"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppShell, useUser } from "@/components/AppShell";
import { ErrorNote, Field, Modal, Pager, SeverityBadge, btnPrimary, btnSecondary, inputCls } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { downloadBcf } from "@/lib/api";
import {
  acknowledgeIssue, getLatestRun, getProject, listIssues, revokeAcknowledgement, runValidation,
  ApiError, type Page, type Project, type ReadinessStatus, type ValidationIssue, type ValidationRun,
} from "@/lib/api";
import { SEVERITIES, formatDate } from "@/lib/labels";

const PAGE_SIZE = 20;

const BANNER_TONE: Record<ReadinessStatus, string> = {
  BLOCKED: "border-status-critical bg-status-critical/5 text-status-critical",
  READY_WITH_WARNINGS: "border-status-warn bg-status-warn/5 text-status-warn",
  READY: "border-status-ok bg-status-ok/5 text-status-ok",
};

const WHERE: Record<string, { labelKey: string; path: string }> = {
  dependency: { labelKey: "validation.whereOpenDeps", path: "dependencies" },
  consistency: { labelKey: "validation.whereOpenImpact", path: "impact" },
};

function AcknowledgeDialog({ issue, onClose, onDone }: { issue: ValidationIssue; onClose: () => void; onDone: () => void }) {
  const { t } = useT();
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={t("validation.acknowledgeTitle")} onClose={onClose}>
      <p className="mt-3 text-sm">{issue.message}</p>
      <p className="mt-3 rounded bg-paper px-3 py-2 text-xs text-muted">{t("validation.acknowledgeWarning")}</p>
      <form onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true); setError(null);
        try { await acknowledgeIssue(issue.id, note.trim()); onDone(); }
        catch (err) { setError((err as Error).message); }
        finally { setBusy(false); }
      }}>
        <Field label={t("validation.reasonLabel")}>
          <textarea className={inputCls} rows={3} value={note} onChange={(e) => setNote(e.target.value)} autoFocus />
        </Field>
        <ErrorNote message={error} />
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className={btnSecondary} onClick={onClose}>{t("action.cancel")}</button>
          <button type="submit" className={btnPrimary} disabled={busy || note.trim().length < 5}>{t("validation.acknowledge")}</button>
        </div>
      </form>
    </Modal>
  );
}

function ValidationView() {
  const { id } = useParams<{ id: string }>();
  const user = useUser();
  const { t } = useT();
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
  const [bcfBusy, setBcfBusy] = useState(false);

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

  if (error && !project) return <><Link href={`/projects/${id}`} className="text-sm text-steel hover:underline">{t("breadcrumb.backToProject")}</Link><ErrorNote message={error} /></>;
  if (!project) return <p className="text-muted">{t("common.loading")}</p>;

  const canRun = user.role !== "viewer";
  const canAck = user.role === "admin" || user.role === "bim_coordinator" || user.role === "reviewer";
  const s = run?.summary ?? {};

  return (
    <>
      <Link href={`/projects/${id}`} className="text-sm text-steel hover:underline">{t("breadcrumb.backToProject")} {project.name}</Link>
      <div className="mt-3 flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-semibold">{t("project.validateForIssue")}</h1>
          <p className="mt-1 text-sm text-muted">{t("validation.description")}</p>
        </div>
        <div className="flex shrink-0 gap-2">
          {run && (
            <button className={btnSecondary} disabled={bcfBusy} onClick={async () => {
              if (!run) return;
              setBcfBusy(true);
              try { await downloadBcf(run.id); }
              catch (e) { setError((e as Error).message); }
              finally { setBcfBusy(false); }
            }}>
              {bcfBusy ? t("validation.bcfDownloading") : t("validation.downloadBcf")}
            </button>
          )}
          {canRun && (
            <button className={btnPrimary} disabled={busy}
                    onClick={() => act(async () => { setRun(await runValidation(id)); setNone(false); setOffset(0); })}>
              {busy ? t("validation.validating") : t("project.validateForIssue")}
            </button>
          )}
        </div>
      </div>
      <ErrorNote message={error} />

      {none && (
        <div className="mt-6 rounded border border-dashed border-line bg-white p-8">
          <p className="font-medium">{t("validation.notValidatedYet")}</p>
          <p className="mt-1 text-sm text-muted">{canRun ? t("validation.runHint") : t("validation.askEngineer")}</p>
        </div>
      )}

      {run && (
        <>
          <section className={`mt-6 rounded border-2 p-5 ${BANNER_TONE[run.status]}`} aria-label={t("readiness.READY")}>
            <p className="text-2xl font-semibold tracking-tight">{t(`validation.banner.${run.status}.title`)}</p>
            <p className="mt-1 text-sm text-ink">{t(`validation.banner.${run.status}.text`)}</p>
            <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-ink">
              {SEVERITIES.map((sev) => (
                <span key={sev} className="flex items-center gap-1.5">
                  <SeverityBadge severity={sev} />
                  <span className="text-lg font-semibold">{s.open_by_severity?.[sev] ?? 0}</span>
                </span>
              ))}
              <span className="text-sm text-muted">{t("validation.acknowledgedCount", { n: s.acknowledged ?? 0 })}</span>
              <span className="text-sm text-muted">{t("validation.documentsChecked", { n: s.documents_checked ?? 0 })}</span>
            </div>
            <p className="mt-3 text-xs text-muted">
              {t("validation.validatedPrefix", {
                date: formatDate(run.created_at),
                name: run.created_by_name,
                ms: run.duration_ms,
                severity: (s.blocking_severity ?? "").toLowerCase(),
              })}
              <Link href="/rules" className="text-steel hover:underline">{t("validation.releasePolicyLink")}</Link>
              {t("validation.validatedSuffix")}
            </p>
            {(s.documents_checked ?? 0) === 0 && <p className="mt-2 text-sm">{t("validation.noDocuments")}</p>}
          </section>

          <div className="mt-6 flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted">{t("validation.severity")}</span>
            <button className={`${btnSecondary} ${severity === "" ? "border-steel bg-steel-light" : ""}`} onClick={() => { setSeverity(""); setOffset(0); }}>{t("action.all")}</button>
            {SEVERITIES.map((sev) => (
              <button key={sev} aria-pressed={severity === sev} className={`${btnSecondary} ${severity === sev ? "border-steel bg-steel-light" : ""}`}
                onClick={() => { setSeverity(severity === sev ? "" : sev); setOffset(0); }}>{t(`severity.${sev}`)}</button>
            ))}
            <select aria-label={t("validation.status")} className="ml-3 rounded border border-line bg-white px-3 py-1.5 text-sm" value={status}
                    onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
              <option value="">{t("validation.statusAll")}</option>
              <option value="open">{t("validation.open")}</option>
              <option value="acknowledged">{t("validation.acknowledged")}</option>
            </select>
          </div>

          {issues && issues.items.length === 0 && (
            <p className="mt-4 rounded border border-line bg-white p-4 text-sm">
              {(s.total ?? 0) === 0 ? t("validation.noIssues") : t("validation.noMatch")}
            </p>
          )}
          <ul className="mt-4 space-y-3">
            {issues?.items.map((i) => {
              const ackLine = i.acknowledged_at
                ? t("validation.acknowledgedByWithDate", {
                    name: i.acknowledged_by_name,
                    date: formatDate(i.acknowledged_at),
                    note: i.acknowledgement_note,
                  })
                : t("validation.acknowledgedBy", {
                    name: i.acknowledged_by_name,
                    note: i.acknowledgement_note,
                  });
              return (
                <li key={i.id} className={`rounded border bg-white p-4 ${i.status === "acknowledged" ? "border-line opacity-80" : "border-line"}`}>
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={i.severity} />
                    {i.document_number && <span className="font-mono text-sm font-medium">{i.document_number}</span>}
                    {i.element_tag && <span className="font-mono text-xs text-muted">{i.element_tag}</span>}
                    <span className="font-medium">{i.title}</span>
                    <span className="ml-auto text-xs text-muted">{i.rule_name}</span>
                  </div>
                  <p className="mt-2 text-sm">{i.message}</p>
                  <p className="mt-2 text-sm"><span className="font-medium">{t("validation.whatToDo")} </span>{i.recommended_action}</p>
                  {i.status === "acknowledged" && (
                    <p className="mt-2 rounded bg-paper px-3 py-2 text-xs">{ackLine}</p>
                  )}
                  <div className="mt-3 flex flex-wrap gap-2">
                    {WHERE[i.category] ? (
                      <Link href={`/projects/${id}/${WHERE[i.category].path}`} className={`${btnSecondary} inline-block`}>
                        {t(WHERE[i.category].labelKey)}
                      </Link>
                    ) : (
                      <Link href={`/projects/${id}`} className={`${btnSecondary} inline-block`}>
                        {t("validation.whereOpenDocuments")}
                      </Link>
                    )}
                    {canAck && i.status === "open" && i.severity !== "CRITICAL" && (
                      <button className={btnSecondary} onClick={() => setAcknowledging(i)}>{t("validation.acknowledge")}</button>
                    )}
                    {canAck && i.status === "acknowledged" && (
                      <button className={btnSecondary} disabled={busy}
                              onClick={() => act(async () => { await revokeAcknowledgement(i.id); loadRun(); })}>
                        {t("validation.revokeAck")}
                      </button>
                    )}
                    {i.severity === "CRITICAL" && i.status === "open" && (
                      <span className="self-center text-xs text-muted">{t("validation.criticalNote")}</span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
          {issues && <Pager total={issues.total} limit={issues.limit} offset={issues.offset} onChange={setOffset} />}
        </>
      )}

      {acknowledging && (
        <AcknowledgeDialog issue={acknowledging}
                           onClose={() => setAcknowledging(null)}
                           onDone={() => { setAcknowledging(null); loadRun(); }} />
      )}
    </>
  );
}

export default function ValidationPage() {
  return <AppShell><ValidationView /></AppShell>;
}