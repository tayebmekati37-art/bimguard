"use client";

import { useCallback, useEffect, useState } from "react";
import { AppShell, useUser } from "@/components/AppShell";
import { ErrorNote, btnPrimary, btnSecondary, inputCls } from "@/components/ui";
import { listRules, resetRule, updateRule, type RuleRecord } from "@/lib/api";
import { SEVERITIES, formatDate } from "@/lib/labels";

const CATEGORY_TITLES: Record<string, string> = {
  revision: "Revisions", dependency: "Dependencies", consistency: "Consistency", metadata: "Metadata",
  naming: "Naming", approval: "Approval", policy: "Release policy",
};

function RuleRow({ rule, editable, onChanged }: { rule: RuleRecord; editable: boolean; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [params, setParams] = useState(JSON.stringify(rule.params, null, 2));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => setParams(JSON.stringify(rule.params, null, 2)), [rule.params]);

  async function save(body: { enabled?: boolean; severity?: string; params?: Record<string, unknown> }) {
    setBusy(true); setError(null);
    try { await updateRule(rule.rule_id, body); onChanged(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  function saveParams() {
    try { save({ params: JSON.parse(params) }); } catch { setError("The parameters are not valid JSON."); }
  }
  const hasParams = Object.keys(rule.default_params).length > 0;

  return (
    <li className="border-b border-line p-4 last:border-0">
      <div className="flex flex-wrap items-start gap-4">
        <label className="mt-1 flex items-center gap-2">
          <input type="checkbox" checked={rule.enabled} disabled={!editable || busy || !rule.can_disable} onChange={(e) => save({ enabled: e.target.checked })} />
          <span className="sr-only">Enabled</span>
        </label>
        <div className="min-w-0 flex-1">
          <p className="font-medium">{rule.name} <span className="font-mono text-xs font-normal text-muted">{rule.rule_id}</span>{!rule.is_default && <span className="ml-2 rounded border border-steel px-1.5 py-0.5 text-xs text-steel">Customised</span>}</p>
          <p className="mt-0.5 text-sm text-muted">{rule.description}</p>
          {!rule.is_default && <p className="mt-0.5 text-xs text-muted">Changed by {rule.updated_by_name}, {formatDate(rule.updated_at)}</p>}
        </div>
        {rule.configurable_severity && (
          <select aria-label={`Severity of ${rule.name}`} className="rounded border border-line bg-white px-2 py-1.5 text-sm" value={rule.severity}
                  disabled={!editable || busy} onChange={(e) => save({ severity: e.target.value })}>
            {SEVERITIES.map((s) => <option key={s} value={s}>{s.charAt(0) + s.slice(1).toLowerCase()}</option>)}
          </select>
        )}
        {hasParams && <button className={btnSecondary} onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Hide settings" : "Settings"}</button>}
      </div>
      {open && hasParams && (
        <div className="mt-3">
          <textarea aria-label={`Settings of ${rule.name}`} className={`${inputCls} font-mono text-xs`} rows={Math.min(16, params.split("\n").length + 1)}
                    value={params} readOnly={!editable} onChange={(e) => setParams(e.target.value)} />
          {editable && <div className="mt-2 flex gap-2">
            <button className={btnPrimary} disabled={busy} onClick={saveParams}>Save settings</button>
            <button className={btnSecondary} disabled={busy || rule.is_default} onClick={async () => { setBusy(true); setError(null); try { await resetRule(rule.rule_id); onChanged(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }}>Reset to default</button>
          </div>}
        </div>
      )}
      <ErrorNote message={error} />
    </li>
  );
}

function RulesView() {
  const user = useUser();
  const [rules, setRules] = useState<RuleRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => { listRules().then(setRules).catch((e) => setError(e.message)); }, []);
  useEffect(load, [load]);
  const editable = user.role === "admin";
  const categories = rules ? Array.from(new Set(rules.map((r) => r.category))) : [];
  return (
    <>
      <h1 className="text-2xl font-semibold">Validation rules</h1>
      <p className="mt-1 text-sm text-muted">The checks behind &quot;Validate for issue&quot;. Changes apply to all projects from the next validation, and are recorded in the audit log.
        {!editable && " Only administrators can change rules."}</p>
      <ErrorNote message={error} />
      {!rules && !error && <p className="mt-4 text-muted">Loading</p>}
      {categories.map((c) => (
        <section key={c} className="mt-6">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">{CATEGORY_TITLES[c] ?? c}</h2>
          <ul className="rounded border border-line bg-white">
            {rules!.filter((r) => r.category === c).map((r) => <RuleRow key={r.rule_id} rule={r} editable={editable} onChanged={load} />)}
          </ul>
        </section>
      ))}
    </>
  );
}

export default function RulesPage() {
  return <AppShell><RulesView /></AppShell>;
}
