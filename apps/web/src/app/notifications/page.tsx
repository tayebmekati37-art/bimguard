"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ErrorNote, Pager, btnPrimary, btnSecondary } from "@/components/ui";
import {
  listNotifications, markAllNotificationsRead, markNotificationRead,
  type NotificationRecord,
} from "@/lib/api";
import { formatDate } from "@/lib/labels";

const PAGE_SIZE = 25;

function NotificationsView() {
  const [items, setItems] = useState<NotificationRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    listNotifications({ unread_only: unreadOnly, limit: PAGE_SIZE, offset })
      .then((p) => { setItems(p.items); setTotal(p.total); setError(null); })
      .catch((e) => setError(e.message));
  }, [unreadOnly, offset]);
  useEffect(load, [load]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await fn(); load(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <>
      <div className="flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-semibold">Notifications</h1>
          <p className="mt-1 text-sm text-muted">Events that need your attention.</p>
        </div>
        <button className={btnSecondary} disabled={busy} onClick={() => act(markAllNotificationsRead)}>
          Mark all read
        </button>
      </div>

      <ErrorNote message={error} />

      <div className="mt-4 flex items-center gap-3 text-sm">
        <button className={`${btnSecondary} ${!unreadOnly ? "border-steel bg-steel-light" : ""}`}
                onClick={() => { setUnreadOnly(false); setOffset(0); }}>All</button>
        <button className={`${btnSecondary} ${unreadOnly ? "border-steel bg-steel-light" : ""}`}
                onClick={() => { setUnreadOnly(true); setOffset(0); }}>Unread only</button>
      </div>

      {items.length === 0 ? (
        <p className="mt-6 text-sm text-muted">Nothing here.</p>
      ) : (
        <ul className="mt-4 space-y-2">
          {items.map((n) => (
            <li key={n.id}
                className={`rounded border bg-white p-3 text-sm ${n.read_at ? "border-line" : "border-steel"}`}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-medium">{n.title}</p>
                  {n.body && <p className="mt-0.5 text-muted">{n.body}</p>}
                  <p className="mt-1 text-xs text-muted">{formatDate(n.created_at)} · {n.kind}</p>
                </div>
                <div className="flex shrink-0 gap-2">
                  {n.link && <Link href={n.link} className={btnPrimary}>Open</Link>}
                  {!n.read_at && (
                    <button className={btnSecondary} disabled={busy}
                            onClick={() => act(() => markNotificationRead(n.id))}>
                      Mark read
                    </button>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Pager total={total} limit={PAGE_SIZE} offset={offset} onChange={setOffset} />
    </>
  );
}

export default function NotificationsPage() {
  return <AppShell><NotificationsView /></AppShell>;
}