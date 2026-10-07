"use client";

import { useEffect, useState } from "react";
import type { ProjectStatus, RevisionStatus } from "@/lib/api";
import { STATUSES } from "@/lib/labels";

export const inputCls = "mt-1 w-full rounded border border-line bg-white px-3 py-2 text-sm";
export const btnPrimary = "rounded bg-steel px-4 py-2 text-sm font-medium text-white hover:bg-steel-dark disabled:opacity-50";
export const btnSecondary = "rounded border border-line bg-white px-3 py-1.5 text-sm hover:bg-paper disabled:opacity-50";
export const btnDanger = "rounded bg-status-critical px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50";

const STATUS_TONE: Record<RevisionStatus | ProjectStatus, string> = {
  draft: "border-line text-muted", in_review: "border-status-warn text-status-warn",
  approved: "border-steel text-steel", issued: "border-status-ok text-status-ok",
  superseded: "border-line text-muted line-through", rejected: "border-status-critical text-status-critical",
  active: "border-status-ok text-status-ok", archived: "border-line text-muted",
};

export function StatusBadge({ status }: { status: RevisionStatus | ProjectStatus }) {
  const label = status in STATUSES ? STATUSES[status as RevisionStatus] : status === "active" ? "Active" : "Archived";
  return <span className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${STATUS_TONE[status]}`}>{label}</span>;
}

export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="mt-4 block text-sm font-medium">
      {label}
      {children}
      {hint && <span className="mt-1 block text-xs font-normal text-muted">{hint}</span>}
    </label>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-4 rounded border border-status-critical/40 bg-status-critical/5 px-3 py-2 text-sm text-status-critical">
      {message}
    </p>
  );
}

export function Modal({ title, onClose, children, wide }: {
  title: string; onClose: () => void; children: React.ReactNode; wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-20 flex items-start justify-center overflow-y-auto bg-ink/40 p-6"
         onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-label={title}
           className={`mt-12 w-full rounded border border-line bg-white p-6 shadow-lg ${wide ? "max-w-3xl" : "max-w-md"}`}>
        <div className="flex items-start justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="text-muted hover:text-ink">Close</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Pager({ total, limit, offset, onChange }: {
  total: number; limit: number; offset: number; onChange: (offset: number) => void;
}) {
  if (total <= limit) return null;
  const end = Math.min(offset + limit, total);
  return (
    <div className="mt-3 flex items-center justify-between text-sm text-muted">
      <span>{offset + 1}–{end} of {total}</span>
      <span className="flex gap-2">
        <button className={btnSecondary} disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button>
        <button className={btnSecondary} disabled={end >= total} onClick={() => onChange(offset + limit)}>Next</button>
      </span>
    </div>
  );
}

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}
