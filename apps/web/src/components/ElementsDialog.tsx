"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { ErrorNote, Modal, Pager, btnSecondary, useDebounced } from "@/components/ui";
import { getModelSummary, listElements, type ElementRecord, type ModelSummary, type Page, type Revision } from "@/lib/api";

const PAGE_SIZE = 25;
const mm = (n: number) => Math.round(n).toLocaleString("en-US").replace(/,/g, " ");
const shortClass = (c: string) => (c.startsWith("Ifc") ? c.slice(3) : c);

function Location({ el }: { el: ElementRecord }) {
  const loc = el.geometry.location;
  if (!loc) return <span className="text-muted">None</span>;
  return <span className="font-mono text-xs">{mm(loc[0])}, {mm(loc[1])}, {mm(loc[2])}</span>;
}

function Details({ el }: { el: ElementRecord }) {
  const rows = Object.entries(el.properties);
  const dims = Object.entries(el.geometry.dimensions ?? {});
  return (
    <div className="grid gap-6 bg-paper px-4 py-3 text-xs md:grid-cols-2">
      <div>
        <p className="mb-1 font-medium">Geometry (mm)</p>
        <dl className="grid grid-cols-[8rem_1fr] gap-y-0.5">
          <dt className="text-muted">Element id</dt><dd className="break-all font-mono">{el.guid}</dd>
          {el.geometry.rotation_deg !== undefined && <><dt className="text-muted">Rotation</dt><dd>{el.geometry.rotation_deg} deg</dd></>}
          {dims.map(([k, v]) => <Fragment key={k}><dt className="text-muted">{k}</dt><dd>{mm(v)}</dd></Fragment>)}
          {el.material && <><dt className="text-muted">Material</dt><dd>{el.material}</dd></>}
        </dl>
      </div>
      <div>
        <p className="mb-1 font-medium">Properties</p>
        {rows.length === 0 ? <p className="text-muted">None</p> : (
          <dl className="grid grid-cols-[minmax(8rem,14rem)_1fr] gap-y-0.5">
            {rows.map(([k, v]) => <Fragment key={k}><dt className="break-all text-muted">{k}</dt><dd className="break-all">{String(v)}</dd></Fragment>)}
          </dl>
        )}
      </div>
    </div>
  );
}

export function ElementsDialog({ docNumber, revision, onClose }: { docNumber: string; revision: Revision; onClose: () => void }) {
  const [summary, setSummary] = useState<ModelSummary | null>(null);
  const [data, setData] = useState<Page<ElementRecord> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [ifcClass, setIfcClass] = useState("");
  const [level, setLevel] = useState("");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const q = useDebounced(search);

  useEffect(() => { getModelSummary(revision.id).then(setSummary).catch((e) => setError(e.message)); }, [revision.id]);
  const load = useCallback(() => {
    listElements(revision.id, { ifc_class: ifcClass, level, q, limit: PAGE_SIZE, offset })
      .then(setData).catch((e) => setError(e.message));
  }, [revision.id, ifcClass, level, q, offset]);
  useEffect(load, [load]);

  return (
    <Modal title={`${docNumber} v${revision.revision_number}: model elements`} onClose={onClose} wide>
      <p className="mt-1 text-sm text-muted">
        {revision.model_schema} · {summary ? `${summary.total} elements` : "Loading"} · Lengths in millimetres, model coordinates
      </p>
      <ErrorNote message={error} />

      {summary && summary.by_class.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          <button className={`${btnSecondary} ${ifcClass === "" ? "border-steel bg-steel-light" : ""}`}
                  onClick={() => { setIfcClass(""); setOffset(0); }}>All {summary.total}</button>
          {summary.by_class.map((c) => (
            <button key={c.key} className={`${btnSecondary} ${ifcClass === c.key ? "border-steel bg-steel-light" : ""}`}
                    onClick={() => { setIfcClass(c.key); setOffset(0); }}>{shortClass(c.key)} {c.count}</button>
          ))}
        </div>
      )}

      <div className="mt-3 flex gap-3">
        <input aria-label="Search elements" placeholder="Search name, tag or id" className="w-64 rounded border border-line bg-white px-3 py-2 text-sm"
               value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} />
        {summary && summary.by_level.length > 1 && (
          <select aria-label="Level filter" className="rounded border border-line bg-white px-3 py-2 text-sm" value={level}
                  onChange={(e) => { setLevel(e.target.value); setOffset(0); }}>
            <option value="">All levels</option>
            {summary.by_level.map((l) => <option key={l.key} value={l.key === "(none)" ? "" : l.key}>{l.key}</option>)}
          </select>
        )}
      </div>

      {data && data.items.length === 0 && <p className="mt-4 text-sm">No elements match these filters.</p>}
      {data && data.items.length > 0 && (
        <>
          <table className="mt-3 w-full border border-line text-sm">
            <thead className="border-b border-line bg-paper text-left text-muted">
              <tr><th className="px-2 py-1.5 font-medium">Class</th><th className="px-2 font-medium">Tag</th>
                  <th className="px-2 font-medium">Name</th><th className="px-2 font-medium">Level</th>
                  <th className="px-2 font-medium">Room</th><th className="px-2 font-medium">Location X, Y, Z</th></tr>
            </thead>
            <tbody>
              {data.items.map((el) => (
                <Fragment key={el.id}>
                  <tr className="cursor-pointer border-b border-line hover:bg-steel-light/40" tabIndex={0}
                      aria-expanded={open === el.id}
                      onClick={() => setOpen(open === el.id ? null : el.id)}
                      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(open === el.id ? null : el.id); } }}>
                    <td className="px-2 py-1.5">{shortClass(el.ifc_class)}</td>
                    <td className="px-2 font-mono">{el.tag}</td>
                    <td className="px-2">{el.name}</td>
                    <td className="px-2">{el.level ?? <span className="text-muted">None</span>}</td>
                    <td className="px-2">{el.room ?? <span className="text-muted">None</span>}</td>
                    <td className="px-2"><Location el={el} /></td>
                  </tr>
                  {open === el.id && <tr className="border-b border-line"><td colSpan={6}><Details el={el} /></td></tr>}
                </Fragment>
              ))}
            </tbody>
          </table>
          <Pager total={data.total} limit={data.limit} offset={data.offset} onChange={setOffset} />
        </>
      )}
    </Modal>
  );
}
