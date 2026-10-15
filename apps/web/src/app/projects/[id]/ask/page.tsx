"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ErrorNote, btnPrimary } from "@/components/ui";
import {
  ApiError, askProject, getAiStatus, getProject,
  type AiStatus, type AskResponse, type Project,
} from "@/lib/api";

function AskView() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [question, setQuestion] = useState("");
  const [aiEnabled, setAiEnabled] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getProject(id).then(setProject).catch(() => {});
    getAiStatus().then(setStatus).catch(() => setStatus(null));
  }, [id]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await askProject(id, question, aiEnabled && !!status?.enabled);
      setResult(r);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Link href={`/projects/${id}`} className="text-sm text-steel hover:underline">
        Back to {project?.name ?? "project"}
      </Link>
      <div className="mt-3">
        <h1 className="text-2xl font-semibold">Ask about this project</h1>
        <p className="mt-1 text-sm text-muted">
          Answers come from the deterministic engine. When AI is enabled, the model only rewords the facts.
        </p>
      </div>

      <ErrorNote message={error} />

      <form onSubmit={submit} className="mt-5 space-y-3 rounded border border-line bg-white p-4">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          placeholder="e.g. what depends on A-101, status of S-201, validation issues for M-301"
          className="w-full rounded border border-line bg-paper px-3 py-2 text-sm"
          required
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={aiEnabled}
            disabled={!status?.enabled}
            onChange={(e) => setAiEnabled(e.target.checked)}
          />
          <span>Use AI to reword the answer</span>
          {!status?.enabled && (
            <span className="text-xs text-muted">(AI not configured on the server)</span>
          )}
        </label>
        <button type="submit" className={btnPrimary} disabled={loading || question.trim().length === 0}>
          {loading ? "Asking..." : "Ask"}
        </button>
      </form>

      {result && (
        <section className="mt-5 rounded border border-line bg-white p-4">
          <div className="flex items-center gap-2">
            <span className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${result.path === "ai" ? "border-steel text-steel" : "border-line text-muted"}`}>
              {result.path === "ai" ? "AI" : "Template"}
            </span>
            <span className="text-xs text-muted">{result.question_type}</span>
          </div>
          <p className="mt-2 whitespace-pre-line text-sm">{result.answer}</p>
          {result.violations.length > 0 && (
            <p className="mt-2 text-xs text-status-warn">
              Grounding check failed: {result.violations.join("; ")}
            </p>
          )}
        </section>
      )}
    </>
  );
}

export default function AskPage() {
  return <AppShell><AskView /></AppShell>;
}
