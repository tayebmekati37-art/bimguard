"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ErrorNote, btnSecondary } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { listSessions, logout, revokeAllSessions, revokeSession, type SessionRecord } from "@/lib/api";
import { formatDate } from "@/lib/labels";

function SessionsView() {
  const router = useRouter();
  const { t } = useT();
  const [sessions, setSessions] = useState<SessionRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [revokeAllBusy, setRevokeAllBusy] = useState(false);

  const load = useCallback(() => {
    listSessions().then((s) => { setSessions(s); setError(null); }).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  async function revokeOne(familyId: string, isCurrent: boolean) {
    if (isCurrent) {
      if (!window.confirm(t("sessions.signOutThis"))) return;
      await logout();
      router.replace("/login");
      return;
    }
    if (!window.confirm(t("sessions.revokeConfirm"))) return;
    setBusy(familyId);
    setError(null);
    try { await revokeSession(familyId); load(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  }

  async function revokeOthers() {
    if (!window.confirm(t("sessions.revokeAllConfirm"))) return;
    setRevokeAllBusy(true);
    setError(null);
    try { await revokeAllSessions(true); load(); }
    catch (e) { setError((e as Error).message); }
    finally { setRevokeAllBusy(false); }
  }

  return (
    <>
      <h1 className="text-2xl font-semibold">{t("sessions.title")}</h1>
      <p className="mt-1 text-sm text-muted">{t("sessions.description")}</p>
      <ErrorNote message={error} />

      {sessions && sessions.length > 1 && (
        <div className="mt-4">
          <button className={btnSecondary} disabled={revokeAllBusy} onClick={revokeOthers}>
            {revokeAllBusy ? t("sessions.busy") : t("sessions.revokeAll")}
          </button>
        </div>
      )}

      {!sessions && !error && <p className="mt-6 text-muted">{t("sessions.loading")}</p>}
      {sessions && sessions.length === 0 && <p className="mt-6 text-sm text-muted">{t("sessions.empty")}</p>}

      {sessions && sessions.length > 0 && (
        <table className="mt-6 w-full border border-line bg-white text-sm">
          <thead className="border-b border-line bg-paper text-left text-muted">
            <tr>
              <th className="px-3 py-2 font-medium">{t("sessions.colStarted")}</th>
              <th className="px-3 font-medium">{t("sessions.colLastActive")}</th>
              <th className="px-3 font-medium">{t("sessions.colExpires")}</th>
              <th className="px-3 font-medium">{t("sessions.colRotations")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.family_id} className="border-b border-line last:border-0 align-top">
                <td className="px-3 py-2">
                  {formatDate(s.started_at)}
                  {s.is_current && <span className="ml-2 rounded border border-steel px-1.5 py-0.5 text-xs text-steel">{t("sessions.current")}</span>}
                </td>
                <td className="px-3 py-2 text-muted">{formatDate(s.last_active_at)}</td>
                <td className="px-3 py-2 text-muted">{formatDate(s.expires_at)}</td>
                <td className="px-3 py-2">{s.rotation_count}</td>
                <td className="px-3 py-2 text-right">
                  <button className={btnSecondary} disabled={busy !== null || revokeAllBusy}
                          onClick={() => revokeOne(s.family_id, s.is_current)}>
                    {s.is_current ? t("sessions.signOutThis") : t("sessions.revoke")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <p className="mt-6 text-sm">
        <Link href="/settings" className="text-steel hover:underline">{t("breadcrumb.backToSettings")}</Link>
      </p>
    </>
  );
}

export default function SessionsPage() {
  return <AppShell><SessionsView /></AppShell>;
}