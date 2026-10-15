"use client";

import { useEffect, useState } from "react";
import { getAiStatus, type AiStatus } from "@/lib/api";

export default function SettingsPage() {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAiStatus().then(setStatus).catch(() => setError("Could not load AI status."));
  }, []);

  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="mb-4 text-2xl font-semibold">Settings</h1>

      <section className="rounded border border-neutral-200 p-4">
        <h2 className="mb-2 font-medium">AI explanation layer</h2>
        {error && <p className="text-red-600">{error}</p>}
        {status && (
          <dl className="space-y-1 text-sm">
            <div className="flex gap-2">
              <dt className="w-40 text-neutral-500">Status</dt>
              <dd>{status.enabled ? "Enabled" : "Disabled"}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-40 text-neutral-500">Model</dt>
              <dd>{status.model ?? "(not configured)"}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-40 text-neutral-500">Hourly limit</dt>
              <dd>{status.hourly_limit}</dd>
            </div>
            <p className="pt-2 text-xs text-neutral-500">
              Provider settings come from server environment variables
              (AI_BASE_URL, AI_API_KEY, AI_MODEL). The deterministic templates
              always work, even when AI is disabled.
            </p>
          </dl>
        )}
      </section>
    </main>
  );
}
