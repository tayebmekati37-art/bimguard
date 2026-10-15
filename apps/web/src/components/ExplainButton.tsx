"use client";

import { useState } from "react";
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
    setResult(null);
    setOpen(true);
    try {
      const question = `Status of ${documentNumber}`;
      const r = await askProject(projectId, question, true);
      setResult(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-2">
      <button
        onClick={run}
        disabled={loading}
        className="rounded border border-neutral-300 px-3 py-1 text-sm hover:bg-neutral-100 disabled:opacity-50"
      >
        {loading ? "Explaining..." : "Explain"}
      </button>

      {open && (
        <div className="rounded border border-neutral-200 bg-neutral-50 p-3 text-sm">
          {error && <p className="text-red-600">{error}</p>}
          {result && (
            <>
              <div className="mb-2 flex items-center gap-2">
                <span className={"rounded px-2 py-0.5 text-xs " +
                  (result.path === "ai" ? "bg-blue-100 text-blue-800" : "bg-neutral-200 text-neutral-700")}>
                  {result.path === "ai" ? "AI" : "Template"}
                </span>
                <span className="text-xs text-neutral-500">{result.question_type}</span>
              </div>
              <p className="whitespace-pre-line">{result.answer}</p>
              {result.violations.length > 0 && (
                <p className="mt-2 text-xs text-amber-700">
                  Grounding check failed; showing template answer instead.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
