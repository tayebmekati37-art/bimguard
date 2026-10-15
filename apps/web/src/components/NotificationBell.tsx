"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getUnreadCount } from "@/lib/api";

export function NotificationBell() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      getUnreadCount()
        .then((r) => { if (!cancelled) setCount(r.count); })
        .catch(() => {});
    };
    tick();
    const id = setInterval(tick, 60000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return (
    <Link href="/notifications" aria-label={`Notifications (${count} unread)`}
          className="relative rounded border border-line px-2 py-1 text-sm hover:bg-paper">
      <span>Notifications</span>
      {count > 0 && (
        <span className="ml-1 inline-block rounded-full bg-status-critical px-1.5 text-xs font-medium text-white">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </Link>
  );
}