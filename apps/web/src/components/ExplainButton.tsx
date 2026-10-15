"use client";

import { useState } from "react";
import { ErrorNote, btnSecondary } from "@/components/ui";
import { ApiError, askProject, type AskResponse } from "@/lib/api";

export default function ExplainButton({ projectId, documentNumber }: {
  projectId: string;
  documentNumber: string;
}) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const r = await askProject(projectId, `Status of ${documentNumber}`, true);
      setResult(r);
      setOpen(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-3">
      <button className={btnSecondary} disabled={loading} onClick={run}>
        {loading ? "Explaining..." : "Explain"}
      </button>
      {error && <div className="mt-2"><ErrorNote message={error} /></div>}
      {open && result && (
        <div className="mt-3 rounded border border-line bg-white p-3 text-sm">
          <div className="mb-2 flex items-center gap-2">
            <span className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${result.path === "ai" ? "border-steel text-steel" : "border-line text-muted"}`}>
              {result.path === "ai" ? "AI" : "Template"}
            </span>
            <span className="text-xs text-muted">{result.question_type}</span>
          </div>
          <p className="whitespace-pre-line">{result.answer}</p>
          {result.violations.length > 0 && (
            <p className="mt-2 text-xs text-status-warn">
              Grounding check failed; showing template answer instead.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
