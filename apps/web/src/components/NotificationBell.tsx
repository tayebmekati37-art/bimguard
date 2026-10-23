"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import { getUnreadCount } from "@/lib/api";

export function NotificationBell() {
  const { t } = useT();
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

  const label = `${t("nav.notifications")} (${count})`;

  return (
    <Link
      href="/notifications"
      aria-label={label}
      className="relative rounded border border-line px-2 py-1 text-sm hover:bg-paper"
    >
      <span>{t("nav.notifications")}</span>
      {count > 0 && (
        <span className="ml-1 inline-block rounded-full bg-status-critical px-1.5 text-xs font-medium text-white">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </Link>
  );
}