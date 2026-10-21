"use client";

import { useEffect, useState } from "react";

export type Locale = "en" | "ja";

export const LOCALES: Locale[] = ["en", "ja"];
export const LOCALE_LABELS: Record<Locale, string> = { en: "English", ja: "日本語" };

const LOCALE_KEY = "bimguard.locale";
const LOCALE_EVENT = "bimguard:locale-changed";

const DICTS: Record<Locale, Record<string, string>> = {
  en: {
    "nav.dashboard": "Dashboard",
    "nav.projects": "Projects",
    "nav.rules": "Rules",
    "nav.settings": "Settings",
    "nav.audit": "Audit",
    "nav.notifications": "Notifications",
    "nav.signout": "Sign out",
    "nav.search": "Search",

    "role.admin": "Admin",
    "role.bim_coordinator": "BIM coordinator",
    "role.engineer": "Engineer",
    "role.reviewer": "Reviewer",
    "role.viewer": "Viewer",

    "health.healthy": "Healthy",
    "health.warning": "Warning",
    "health.stale": "Stale",
    "health.critical": "Critical",

    "readiness.READY": "Ready for issue",
    "readiness.READY_WITH_WARNINGS": "Ready, with warnings",
    "readiness.BLOCKED": "Not ready for issue",
    "readiness.NOT_VALIDATED": "Not yet validated",

    "severity.CRITICAL": "Critical",
    "severity.HIGH": "High",
    "severity.MEDIUM": "Medium",
    "severity.LOW": "Low",

    "status.draft": "Draft",
    "status.in_review": "In review",
    "status.approved": "Approved",
    "status.issued": "Issued",
    "status.superseded": "Superseded",
    "status.rejected": "Rejected",

    "discipline.architecture": "Architecture",
    "discipline.structure": "Structure",
    "discipline.mep": "MEP",
    "discipline.equipment": "Equipment",
    "discipline.quantity": "Quantity",
    "discipline.general": "General",

    "action.save": "Save",
    "action.cancel": "Cancel",
    "action.delete": "Delete",
    "action.edit": "Edit",
    "action.add": "Add",
    "action.run": "Run",
    "action.refresh": "Refresh",
    "action.validate": "Validate",
    "action.download": "Download",
    "action.confirm": "Confirm",

    "common.loading": "Loading",
    "common.noResults": "No results",
  },
  ja: {
    "nav.dashboard": "ダッシュボード",
    "nav.projects": "プロジェクト",
    "nav.rules": "ルール",
    "nav.settings": "設定",
    "nav.audit": "監査ログ",
    "nav.notifications": "通知",
    "nav.signout": "サインアウト",
    "nav.search": "検索",

    "role.admin": "管理者",
    "role.bim_coordinator": "BIM コーディネーター",
    "role.engineer": "エンジニア",
    "role.reviewer": "レビュアー",
    "role.viewer": "閲覧者",

    "health.healthy": "正常",
    "health.warning": "注意",
    "health.stale": "要確認",
    "health.critical": "重大",

    "readiness.READY": "発行可能",
    "readiness.READY_WITH_WARNINGS": "注意付き発行可能",
    "readiness.BLOCKED": "発行不可",
    "readiness.NOT_VALIDATED": "未検証",

    "severity.CRITICAL": "重大",
    "severity.HIGH": "高",
    "severity.MEDIUM": "中",
    "severity.LOW": "低",

    "status.draft": "下書き",
    "status.in_review": "レビュー中",
    "status.approved": "承認済み",
    "status.issued": "発行済み",
    "status.superseded": "失効",
    "status.rejected": "却下",

    "discipline.architecture": "建築",
    "discipline.structure": "構造",
    "discipline.mep": "設備",
    "discipline.equipment": "機器",
    "discipline.quantity": "数量",
    "discipline.general": "共通",

    "action.save": "保存",
    "action.cancel": "キャンセル",
    "action.delete": "削除",
    "action.edit": "編集",
    "action.add": "追加",
    "action.run": "実行",
    "action.refresh": "更新",
    "action.validate": "検証",
    "action.download": "ダウンロード",
    "action.confirm": "確定",

    "common.loading": "読み込み中",
    "common.noResults": "該当なし",
  },
};

export function loadLocale(): Locale {
  if (typeof window === "undefined") return "en";
  const stored = window.localStorage.getItem(LOCALE_KEY) as Locale | null;
  if (stored === "ja" || stored === "en") return stored;
  if (typeof navigator !== "undefined" && navigator.language?.toLowerCase().startsWith("ja")) {
    return "ja";
  }
  return "en";
}

export function saveLocale(locale: Locale): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LOCALE_KEY, locale);
  window.dispatchEvent(new Event(LOCALE_EVENT));
}

export function translate(locale: Locale, key: string): string {
  return DICTS[locale]?.[key] ?? DICTS.en[key] ?? key;
}

export function useT() {
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    setLocaleState(loadLocale());
    const handler = () => setLocaleState(loadLocale());
    window.addEventListener(LOCALE_EVENT, handler);
    return () => window.removeEventListener(LOCALE_EVENT, handler);
  }, []);

  function setLocale(next: Locale) {
    saveLocale(next);
    setLocaleState(next);
  }

  return {
    locale,
    setLocale,
    t: (key: string) => translate(locale, key),
  };
}

// For tests and the parity check
export const ALL_DICTS = DICTS;