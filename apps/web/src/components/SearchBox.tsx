"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useT } from "@/lib/i18n";
import { searchAll, type SearchHit, type SearchResults } from "@/lib/api";
import { useDebounced } from "@/components/ui";

const GROUPS: { key: keyof Omit<SearchResults, "query">; titleKey: string }[] = [
  { key: "projects", titleKey: "search.groupProjects" },
  { key: "documents", titleKey: "search.groupDocuments" },
  { key: "elements", titleKey: "search.groupElements" },
  { key: "issues", titleKey: "search.groupIssues" },
];

function destination(hit: SearchHit): string {
  if (hit.kind === "project") return `/projects/${hit.project_id}`;
  if (hit.kind === "issue") return `/projects/${hit.project_id}/validation`;
  return `/projects/${hit.project_id}?q=${encodeURIComponent(hit.document_number)}`;
}

export function SearchBox() {
  const router = useRouter();
  const { t } = useT();
  const [text, setText] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const q = useDebounced(text.trim(), 250);

  useEffect(() => {
    if (q.length < 2) { setResults(null); setError(null); return; }
    let current = true;
    searchAll(q).then((r) => { if (current) { setResults(r); setError(null); setActive(0); } })
      .catch((e) => { if (current) setError(e.message); });
    return () => { current = false; };
  }, [q]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); input.current?.focus(); } };
    const onClick = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("keydown", onKey); window.addEventListener("mousedown", onClick);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("mousedown", onClick); };
  }, []);

  const flat = useMemo(() => (results ? GROUPS.flatMap((g) => results[g.key]) : []), [results]);

  function go(hit: SearchHit) { setOpen(false); setText(""); setResults(null); router.push(destination(hit)); }
  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") { setOpen(false); input.current?.blur(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, flat.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter" && flat[active]) { e.preventDefault(); go(flat[active]); }
  }

  const showPanel = open && q.length >= 2;
  let index = -1;
  return (
    <div ref={box} className="relative w-72">
      <input ref={input} type="search" role="combobox" aria-expanded={showPanel} aria-controls="search-results" aria-label={t("search.ariaLabel")}
             placeholder={t("search.placeholder")} className="w-full rounded border border-line bg-white px-3 py-1.5 text-sm"
             value={text} onChange={(e) => { setText(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onKeyDown={onKeyDown} />
      {showPanel && (
        <div id="search-results" role="listbox" className="absolute right-0 z-30 mt-1 max-h-[28rem] w-[26rem] overflow-y-auto rounded border border-line bg-white shadow-lg">
          {error && <p className="p-3 text-sm text-status-critical">{error}</p>}
          {!error && results && flat.length === 0 && <p className="p-3 text-sm text-muted">{t("search.nothingFound", { query: q })}</p>}
          {!error && !results && <p className="p-3 text-sm text-muted">{t("search.searching")}</p>}
          {results && GROUPS.map((g) => results[g.key].length > 0 && (
            <div key={g.key}>
              <p className="border-b border-line bg-paper px-3 py-1 text-xs font-semibold uppercase tracking-wide text-muted">{t(g.titleKey)}</p>
              {results[g.key].map((hit) => {
                index += 1;
                const mine = index;
                return (
                  <button key={`${hit.kind}-${hit.id}`} role="option" aria-selected={mine === active} onMouseEnter={() => setActive(mine)} onClick={() => go(hit)}
                          className={`block w-full border-b border-line px-3 py-2 text-left last:border-0 ${mine === active ? "bg-steel-light" : ""}`}>
                    <span className="block truncate text-sm font-medium">{hit.title}</span>
                    <span className="block truncate text-xs text-muted">{hit.subtitle}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}