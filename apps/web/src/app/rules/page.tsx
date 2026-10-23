"use client";

import { useCallback, useEffect, useState } from "react";
import { AppShell, useUser } from "@/components/AppShell";
import { ErrorNote, btnPrimary, btnSecondary, inputCls } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { listRules, resetRule, updateRule, type RuleRecord } from "@/lib/api";
import { SEVERITIES, formatDate } from "@/lib/labels";

const CATEGORY_KEYS: Record<string, string> = {
  revision: "rules.category.revision",
  dependency: "rules.category.dependency",
  consistency: "rules.category.consistency",
  metadata: "rules.category.metadata",
  naming: "rules.category.naming",
  approval: "rules.category.approval",
  policy: "rules.category.policy",
};

function RuleRow({ rule, editable, onChanged }: { rule: RuleRecord; editable: boolean; onChanged: () => void }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [params, setParams] = useState(JSON.stringify(rule.params, null, 2));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => setParams(JSON.stringify(rule.params, null, 2)), [rule.params]);

  async function save(body: { enabled?: boolean; severity?: string; params?: Record<string, unknown> }) {
    setBusy(true); setError(null);
    try { await updateRule(rule.rule_id, body); onChanged(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  function saveParams() {
    try { save({ params: JSON.parse(params) }); }
    catch { setError(t("rules.invalidJson")); }
  }
  const hasParams = Object.keys(rule.default_params).length > 0;

  return (
    <li className="border-b border-line p-4 last:border-0">
      <div className="flex flex-wrap items-start gap-4">
        <label className="mt-1 flex items-center gap-2">
          <input type="checkbox" checked={rule.enabled} disabled={!editable || busy || !rule.can_disable} onChange={(e) => save({ enabled: e.target.checked })} />
          <span className="sr-only">{t("rules.enabled")}</span>
        </label>
        <div className="min-w-0 flex-1">
          <p className="font-medium">
            {rule.name}{" "}
            <span className="font-mono text-xs font-normal text-muted">{rule.rule_id}</span>
            {!rule.is_default && (
              <span className="ml-2 rounded border border-steel px-1.5 py-0.5 text-xs text-steel">
                {t("rules.customised")}
              </span>
            )}
          </p>
          <p className="mt-0.5 text-sm text-muted">{rule.description}</p>
          {!rule.is_default && (
            <p className="mt-0.5 text-xs text-muted">
              {t("rules.changedBy", { name: rule.updated_by_name, date: formatDate(rule.updated_at) })}
            </p>
          )}
        </div>
        {rule.configurable_severity && (
          <select
            aria-label={t("rules.severityAria", { name: rule.name })}
            className="rounded border border-line bg-white px-2 py-1.5 text-sm"
            value={rule.severity}
            disabled={!editable || busy}
            onChange={(e) => save({ severity: e.target.value })}
          >
            {SEVERITIES.map((s) => <option key={s} value={s}>{t(`severity.${s}`)}</option>)}
          </select>
        )}
        {hasParams && (
          <button className={btnSecondary} onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? t("rules.hideSettings") : t("rules.settings")}
          </button>
        )}
      </div>
      {open && hasParams && (
        <div className="mt-3">
          <textarea
            aria-label={t("rules.settingsAria", { name: rule.name })}
            className={`${inputCls} font-mono text-xs`}
            rows={Math.min(16, params.split("\n").length + 1)}
            value={params}
            readOnly={!editable}
            onChange={(e) => setParams(e.target.value)}
          />
          {editable && (
            <div className="mt-2 flex gap-2">
              <button className={btnPrimary} disabled={busy} onClick={saveParams}>{t("rules.saveSettings")}</button>
              <button
                className={btnSecondary}
                disabled={busy || rule.is_default}
                onClick={async () => {
                  setBusy(true); setError(null);
                  try { await resetRule(rule.rule_id); onChanged(); }
                  catch (e) { setError((e as Error).message); }
                  finally { setBusy(false); }
                }}
              >
                {t("rules.resetToDefault")}
              </button>
            </div>
          )}
        </div>
      )}
      <ErrorNote message={error} />
    </li>
  );
}

function RulesView() {
  const user = useUser();
  const { t } = useT();
  const [rules, setRules] = useState<RuleRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => { listRules().then(setRules).catch((e) => setError(e.message)); }, []);
  useEffect(load, [load]);
  const editable = user.role === "admin";
  const categories = rules ? Array.from(new Set(rules.map((r) => r.category))) : [];
  return (
    <>
      <h1 className="text-2xl font-semibold">{t("rules.validationRules")}</h1>
      <p className="mt-1 text-sm text-muted">
        {t("rules.description")}{!editable && " " + t("rules.adminNote")}
      </p>
      <ErrorNote message={error} />
      {!rules && !error && <p className="mt-4 text-muted">{t("common.loading")}</p>}
      {categories.map((c) => (
        <section key={c} className="mt-6">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">
            {t(CATEGORY_KEYS[c] ?? c)}
          </h2>
          <ul className="rounded border border-line bg-white">
            {rules!.filter((r) => r.category === c).map((r) =>
              <RuleRow key={r.rule_id} rule={r} editable={editable} onChanged={load} />
            )}
          </ul>
        </section>
      ))}
    </>
  );
}

export default function RulesPage() {
  return <AppShell><RulesView /></AppShell>;
}