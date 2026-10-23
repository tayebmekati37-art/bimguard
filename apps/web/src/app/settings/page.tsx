"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ErrorNote } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { getAiStatus, type AiStatus } from "@/lib/api";

function SettingsView() {
  const { t } = useT();
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAiStatus().then(setStatus).catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <h1 className="text-2xl font-semibold">{t("settings.title")}</h1>

      <p className="mt-3 rounded border border-line bg-paper px-3 py-2 text-xs text-muted">
        {t("settings.translationNotice")}
      </p>

      <section className="mt-5 rounded border border-line bg-white p-4">
        <h2 className="font-medium">{t("settings.aiLayer")}</h2>
        <ErrorNote message={error} />
        {status && (
          <dl className="mt-3 space-y-1 text-sm">
            <div className="flex gap-3">
              <dt className="w-40 text-muted">{t("settings.aiStatus")}</dt>
              <dd>{status.enabled ? t("settings.aiEnabled") : t("settings.aiDisabled")}</dd>
            </div>
            <div className="flex gap-3">
              <dt className="w-40 text-muted">{t("settings.aiModel")}</dt>
              <dd className="font-mono">{status.model ?? t("settings.aiNotConfigured")}</dd>
            </div>
            <div className="flex gap-3">
              <dt className="w-40 text-muted">{t("settings.aiHourlyLimit")}</dt>
              <dd>{status.hourly_limit}</dd>
            </div>
          </dl>
        )}
        <p className="mt-3 text-xs text-muted">{t("settings.aiProviderNote")}</p>
      </section>

      <section className="mt-4 rounded border border-line bg-white p-4">
        <p className="text-sm">
          <Link href="/settings/profiles" className="text-steel hover:underline font-medium">
            {t("settings.profilesLink")}
          </Link>{" "}
          <span className="text-muted">— {t("settings.profilesDescription")}</span>
        </p>
      </section>
    </>
  );
}

export default function SettingsPage() {
  return <AppShell><SettingsView /></AppShell>;
}