"use client";

import { useEffect, useState } from "react";
import { ApiError, askProject, getAiStatus, type AiStatus, type AskResponse } from "@/lib/api";

export default function AskPage({ params }: { params: { id: string } }) {
  const [question, setQuestion] = useState("");
  const [aiEnabled, setAiEnabled] = useState(false);
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getAiStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await askProject(params.id, question, aiEnabled && !!status?.enabled);
      setResult(r);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="mb-4 text-2xl font-semibold">Ask about this project</h1>

      <form onSubmit={submit} className="space-y-3">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          placeholder="e.g. what depends on A-101, status of S-201, validation issues"
          className="w-full rounded border border-neutral-300 p-2"
          required
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={aiEnabled}
            disabled={!status?.enabled}
            onChange={(e) => setAiEnabled(e.target.checked)}
          />
          Use AI to reword the answer
          {!status?.enabled && (
            <span className="text-xs text-neutral-500">(AI not configured on the server)</span>
          )}
        </label>
        <button
          type="submit"
          disabled={loading || question.trim().length === 0}
          className="rounded bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {loading ? "Asking..." : "Ask"}
        </button>
      </form>

      {error && <p className="mt-4 text-red-600">{error}</p>}

      {result && (
        <section className="mt-6 space-y-2 rounded border border-neutral-200 p-4">
          <div className="flex items-center gap-2">
            <span className={"rounded px-2 py-0.5 text-xs " +
              (result.path === "ai" ? "bg-blue-100 text-blue-800" : "bg-neutral-200 text-neutral-700")}>
              {result.path === "ai" ? "AI" : "Template"}
            </span>
            <span className="text-xs text-neutral-500">{result.question_type}</span>
          </div>
          <p className="whitespace-pre-line">{result.answer}</p>
          {result.violations.length > 0 && (
            <p className="text-xs text-amber-700">
              Grounding check failed: {result.violations.join("; ")}
            </p>
          )}
        </section>
      )}
    </main>
  );
}
