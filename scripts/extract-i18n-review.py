"""Extract Japanese translations into a reviewer package. v2."""
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "apps" / "web" / "src" / "lib" / "i18n.ts"
OUT = ROOT / "docs" / "i18n" / "review"

text = I18N.read_text(encoding="utf-8")
en_idx = text.find("  en: {")
ja_idx = text.find("  ja: {")
if en_idx < 0 or ja_idx < 0:
    raise SystemExit("could not find en/ja blocks")

en_start = en_idx + len("  en: {")
en_end = text.rfind("  },\n", en_start, ja_idx)
en_block = text[en_start:en_end]

ja_start = ja_idx + len("  ja: {")
dicts_end = text.find("};", ja_start)
ja_end = text.rfind("  },\n", ja_start, dicts_end)
if ja_end < 0:
    ja_end = text.rfind("  }\n", ja_start, dicts_end)
ja_block = text[ja_start:ja_end]

# Map messy comment categories to canonical ones.
CATEGORY_MAP = {
    "navigation": "navigation",
    "common actions": "action",
    "common": "common",
    "roles": "role",
    "health": "health",
    "readiness": "readiness",
    "severity": "severity",
    "revision status": "status",
    "disciplines": "discipline",
    "breadcrumbs": "navigation",
    "ask page": "ask",
    "reports page": "reports",
    "audit page": "audit",
    "notifications page": "notifications",
    "settings page": "settings",
    "profiles page": "profiles",
    "login page": "login",
    "dashboard page": "dashboard",
    "projects list page": "projects",
    "project detail page": "project",
    "rules page": "rules",
    "dependencies page": "deps",
    "impact page": "impact",
    "validation page": "validation",
    "compare page": "compare",
    "graph": "graph",
    "plan view": "plan",
    "explain button": "explain",
    "searchbox": "search",
    "elementsdialog": "elements",
    "healthpanel": "health",
    "shared": "shared",
    "health state descriptions": "health",
    "compare page (remaining)": "compare",
    "graph (remaining)": "graph",
    "plan view (remaining)": "plan",
}


def clean_category(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"^M\d+[a-z]*-[a-z0-9]+(-[a-z])?:\s*", "", s)
    s = s.lower().strip()
    return CATEGORY_MAP.get(s, s)


def extract(block: str):
    result = {}
    cat = "uncategorized"
    for line in block.split("\n"):
        s = line.strip()
        if s.startswith("// ----------------"):
            raw = s.replace("// ----------------", "").strip()
            cat = clean_category(raw)
            continue
        m = re.match(r'"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)+)"', s)
        if m:
            key, val = m.group(1), m.group(2)
            val = val.replace('\\"', '"').replace("\\\\", "\\")
            result[key] = (cat, val)
    return result


en = extract(en_block)
ja = extract(ja_block)

# Keys with a specific reason for LOW confidence and a reviewer note.
LOW_NOTES = {
    "health.stale": "要確認 = 'requires confirmation'. Alternative: 古い (old).",
    "health.critical": "重大 = 'serious'. Alternative: 致命的 (fatal).",
    "health.warning": "注意 = 'caution'. Alternative: 警告.",
    "readiness.READY": "発行可能 = 'issuable'. Team wording may differ.",
    "readiness.READY_WITH_WARNINGS": "Long. Alternative: 条件付き発行可能.",
    "readiness.BLOCKED": "発行不可 = 'cannot issue'. Verify.",
    "validation.acknowledge": "確認応答 = formal. Team may use 承諾 or 認識.",
    "validation.open": "未解決. Alternatives: 未対応, オープン.",
    "validation.acknowledged": "確認済み. Same root as 確認応答.",
    "impact.state.advisory": "参考. Alternatives: 情報提供.",
    "deps.validate": "レビュー済みにする. Check tone.",
    "profiles.illustrative": "参考用. Alternatives: 例示用, サンプル.",
    "severity.CRITICAL": "Same 重大 as health.critical. Verify consistency.",
    "status.issued": "発行済み. Standard.",
    "status.superseded": "失効 = 'lapsed'. Standard in doc management.",
    "status.in_review": "レビュー中 uses loanword. Alternative: 審査中.",
}


def confidence(key: str, category: str) -> str:
    if key in LOW_NOTES:
        return "LOW"
    for prefix in ("nav.", "action.", "role.", "status.", "discipline.", "severity."):
        if key.startswith(prefix):
            return "HIGH"
    for prefix in ("readiness.", "health.", "validation.state.",
                   "impact.state.", "deps.state.", "profiles.illustrative"):
        if key.startswith(prefix):
            return "LOW"
    if key.startswith("common.") and len(key) <= 20:
        return "HIGH"
    return "MEDIUM"


PRIORITY_PATTERNS = (
    "readiness.", "health.", "severity.", "status.", "discipline.",
    "validation.acknowledge", "validation.open", "validation.acknowledged",
    "validation.banner.", "validation.critical",
    "impact.state.", "impact.markReviewed", "impact.whyAffected",
    "login.", "signin",
    "deps.relationship", "deps.state", "deps.stale", "deps.markReviewed",
    "profiles.",
    "project.docNumber", "project.docName", "project.discipline",
    "project.file", "project.revisionNumber", "project.changeSummary",
    "compare.noDifferences", "compare.change",
    "rule.", "validation.issue",
)


def is_priority(key: str, conf: str) -> bool:
    if conf == "LOW":
        return True
    for prefix in PRIORITY_PATTERNS:
        if key.startswith(prefix):
            return True
    return False


def write_csv(path: Path, keys: list, priority_only: bool = False) -> None:
    # utf-8-sig BOM so Excel opens it correctly.
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "key", "category", "english", "japanese_current",
            "confidence", "review_ok", "suggested_fix", "notes",
        ])
        for k in keys:
            cat, e = en.get(k, ("missing", ""))
            _, j = ja.get(k, ("missing", ""))
            conf = confidence(k, cat)
            note = LOW_NOTES.get(k, "")
            w.writerow([k, cat, e, j, conf, "", "", note])


all_keys = sorted(set(en) | set(ja))
priority_keys = [k for k in all_keys
                 if is_priority(k, confidence(k, en.get(k, ("", ""))[0]))]

OUT.mkdir(parents=True, exist_ok=True)
# Clean the output dir so regeneration is deterministic.
for f in OUT.iterdir():
    if f.is_file():
        f.unlink()

write_csv(OUT / "strings.csv", all_keys)
write_csv(OUT / "strings_priority.csv", priority_keys, priority_only=True)

counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
for k in all_keys:
    cat = en.get(k, ("", ""))[0]
    counts[confidence(k, cat)] += 1

cat_counts: dict[str, int] = {}
for k in all_keys:
    cat = en.get(k, ("uncategorized", ""))[0]
    cat_counts[cat] = cat_counts.get(cat, 0) + 1

manifest = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "total_keys": len(all_keys),
    "priority_keys": len(priority_keys),
    "confidence": counts,
    "categories": dict(sorted(cat_counts.items())),
    "i18n_source": "apps/web/src/lib/i18n.ts",
    "review_state": "not_reviewed",
}
(OUT / "manifest.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
)

print(f"OK: {len(all_keys)} keys, {len(priority_keys)} in priority file")
print(f"  HIGH   {counts['HIGH']}")
print(f"  MEDIUM {counts['MEDIUM']}")
print(f"  LOW    {counts['LOW']}")
print(f"  categories: {len(cat_counts)}")
print(f"Output: {OUT}")