"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ErrorNote, btnPrimary, btnSecondary } from "@/components/ui";
import {
  activateProjectProfile, deactivateProjectProfile, getProjectProfile,
  listProfiles, listProjects,
  type ProfileActivation, type ProfileSummary, type Project,
} from "@/lib/api";
import { formatDate } from "@/lib/labels";

function ProfilesView() {
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

  return (
    <>
      <h1 className="text-2xl font-semibold">Quality profiles</h1>
      <p className="mt-1 text-sm text-muted">
        A profile bundles rule overrides for one project. Activating a profile
        changes the severity, parameters or enabled state of existing rules.
        It does not add new rules.
      </p>

      <ErrorNote message={error} />

      <div className="mt-5 flex flex-wrap items-end gap-3">
        <label className="flex flex-col text-sm">
          <span className="mb-1 text-muted">Project</span>
          <select
            className="rounded border border-line bg-white px-3 py-2 text-sm"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
          >
            <option value="">Choose a project</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>

        {activation && (
          <div className="text-sm">
            <span className="text-muted">Active profile: </span>
            {activation.profile_id ? (
              <>
                <span className="font-mono">{activation.profile_id}</span>
                <span className="ml-2 text-xs text-muted">
                  activated {activation.activated_at ? formatDate(activation.activated_at) : ""}
                  {activation.activated_by_name ? ` by ${activation.activated_by_name}` : ""}
                </span>
                <button
                  className={`${btnSecondary} ml-3`}
                  disabled={busy}
                  onClick={() => act(() => deactivateProjectProfile(projectId))}
                >
                  Deactivate
                </button>
              </>
            ) : (
              <span className="text-muted">none</span>
            )}
          </div>
        )}
      </div>

      <table className="mt-6 w-full border border-line bg-white text-sm">
        <thead className="border-b border-line bg-paper text-left text-muted">
          <tr>
            <th className="px-3 py-2 font-medium">Id</th>
            <th className="px-3 py-2 font-medium">Name</th>
            <th className="px-3 py-2 font-medium">Rules</th>
            <th className="px-3 py-2 font-medium">Illustrative</th>
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
                  ? <span className="rounded border border-status-warn px-2 py-0.5 text-xs text-status-warn">Illustrative</span>
                  : <span className="text-muted">-</span>}
              </td>
              <td className="px-3 py-2 text-right">
                <button
                  className={btnPrimary}
                  disabled={busy || !projectId || activation?.profile_id === p.id}
                  onClick={() => act(() => activateProjectProfile(projectId, p.id))}
                >
                  {activation?.profile_id === p.id ? "Active" : "Activate"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="mt-6 text-xs text-muted">
        The bundled <span className="font-mono">jp-bimcim-v1</span> profile is
        marked illustrative. It configures BIMGuard&apos;s own rules; it does
        not claim compliance with any official MLIT BIM/CIM requirement.
      </p>

      <p className="mt-4 text-sm">
        <Link href="/settings" className="text-steel hover:underline">Back to settings</Link>
      </p>
    </>
  );
}

export default function ProfilesPage() {
  return <AppShell><ProfilesView /></AppShell>;
}