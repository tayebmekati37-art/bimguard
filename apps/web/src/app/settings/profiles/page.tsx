"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ErrorNote, btnPrimary, btnSecondary } from "@/components/ui";
import { useT } from "@/lib/i18n";
import {
  activateProjectProfile, deactivateProjectProfile, getProjectProfile,
  listProfiles, listProjects,
  type ProfileActivation, type ProfileSummary, type Project,
} from "@/lib/api";
import { formatDate } from "@/lib/labels";

function ProfilesView() {
  const { t } = useT();
  const [profiles, setProfiles] = useState<ProfileSummary[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [activation, setActivation] = useState<ProfileActivation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([listProfiles(), listProjects({ limit: 100 })])
      .then(([p, pr]) => {
        setProfiles(p);
        setProjects(pr.items);
        const fromUrl = new URLSearchParams(window.location.search).get("project");
        if (fromUrl) setProjectId(fromUrl);
        else if (pr.items.length > 0) setProjectId(pr.items[0].id);
      })
      .catch((e) => setError(e.message));
  }, []);

  const loadActivation = useCallback(() => {
    if (!projectId) { setActivation(null); return; }
    getProjectProfile(projectId).then(setActivation).catch((e) => setError(e.message));
  }, [projectId]);
  useEffect(loadActivation, [loadActivation]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await fn(); loadActivation(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  function activatedLabel(a: ProfileActivation): string {
    if (!a.activated_at) return "";
    const date = formatDate(a.activated_at);
    return a.activated_by_name
      ? t("profiles.activatedBy", { date, name: a.activated_by_name })
      : t("profiles.activatedAt", { date });
  }

  return (
    <>
      <h1 className="text-2xl font-semibold">{t("profiles.title")}</h1>
      <p className="mt-1 text-sm text-muted">{t("profiles.description")}</p>

      <ErrorNote message={error} />

      <div className="mt-5 flex flex-wrap items-end gap-3">
        <label className="flex flex-col text-sm">
          <span className="mb-1 text-muted">{t("profiles.project")}</span>
          <select
            className="rounded border border-line bg-white px-3 py-2 text-sm"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
          >
            <option value="">{t("profiles.chooseProject")}</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>

        {activation && (
          <div className="text-sm">
            <span className="text-muted">{t("profiles.activeProfile")} </span>
            {activation.profile_id ? (
              <>
                <span className="font-mono">{activation.profile_id}</span>
                <span className="ml-2 text-xs text-muted">{activatedLabel(activation)}</span>
                <button
                  className={`${btnSecondary} ml-3`}
                  disabled={busy}
                  onClick={() => act(() => deactivateProjectProfile(projectId))}
                >
                  {t("profiles.deactivate")}
                </button>
              </>
            ) : (
              <span className="text-muted">{t("profiles.none")}</span>
            )}
          </div>
        )}
      </div>

      <table className="mt-6 w-full border border-line bg-white text-sm">
        <thead className="border-b border-line bg-paper text-left text-muted">
          <tr>
            <th className="px-3 py-2 font-medium">{t("profiles.id")}</th>
            <th className="px-3 py-2 font-medium">{t("profiles.name")}</th>
            <th className="px-3 py-2 font-medium">{t("profiles.rules")}</th>
            <th className="px-3 py-2 font-medium">{t("profiles.illustrative")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {profiles.map((p) => (
            <tr key={p.id} className="border-b border-line last:border-0 align-top">
              <td className="px-3 py-2 font-mono">{p.id}</td>
              <td className="px-3 py-2">
                <div className="font-medium">{p.name}</div>
                {p.description && <div className="mt-0.5 max-w-2xl text-xs text-muted">{p.description}</div>}
              </td>
              <td className="px-3 py-2">{p.rule_count}</td>
              <td className="px-3 py-2">
                {p.illustrative
                  ? <span className="rounded border border-status-warn px-2 py-0.5 text-xs text-status-warn">{t("profiles.illustrative")}</span>
                  : <span className="text-muted">{t("common.na")}</span>}
              </td>
              <td className="px-3 py-2 text-right">
                <button
                  className={btnPrimary}
                  disabled={busy || !projectId || activation?.profile_id === p.id}
                  onClick={() => act(() => activateProjectProfile(projectId, p.id))}
                >
                  {activation?.profile_id === p.id ? t("profiles.active") : t("profiles.activate")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="mt-6 text-xs text-muted">
        {t("profiles.bundledNoteBefore")}{" "}
        <span className="font-mono">jp-bimcim-v1</span>{" "}
        {t("profiles.bundledNoteAfter")}
      </p>

      <p className="mt-4 text-sm">
        <Link href="/settings" className="text-steel hover:underline">{t("breadcrumb.backToSettings")}</Link>
      </p>
    </>
  );
}

export default function ProfilesPage() {
  return <AppShell><ProfilesView /></AppShell>;
}