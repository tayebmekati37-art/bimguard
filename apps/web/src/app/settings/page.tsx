"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ErrorNote } from "@/components/ui";
import { getAiStatus, type AiStatus } from "@/lib/api";

function SettingsView() {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAiStatus().then(setStatus).catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <h1 className="text-2xl font-semibold">Settings</h1>

      <section className="mt-5 rounded border border-line bg-white p-4">
        <h2 className="font-medium">AI explanation layer</h2>
        <ErrorNote message={error} />
        {status && (
          <dl className="mt-3 space-y-1 text-sm">
            <div className="flex gap-3"><dt className="w-32 text-muted">Status</dt><dd>{status.enabled ? "Enabled" : "Disabled"}</dd></div>
            <div className="flex gap-3"><dt className="w-32 text-muted">Model</dt><dd className="font-mono">{status.model ?? "(not configured)"}</dd></div>
            <div className="flex gap-3"><dt className="w-32 text-muted">Hourly limit</dt><dd>{status.hourly_limit}</dd></div>
          </dl>
        )}
        <p className="mt-3 text-xs text-muted">
          Provider settings come from server environment variables (AI_BASE_URL, AI_API_KEY, AI_MODEL).
          The deterministic templates always work, even when AI is disabled.
        </p>
      </section>
    </>
  );
}

export default function SettingsPage() {
  return <AppShell><SettingsView /></AppShell>;
}
