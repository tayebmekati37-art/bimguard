"""Find hardcoded English strings in the frontend that need t() wrapping.

Reports each finding with file, line, and — when possible — the i18n key
that should replace it, based on a curated English→key map. Unmapped
strings are listed too; they need a new key added to lib/i18n.ts first.

Usage:
  cd C:\\dev\\bimguard
  python scripts/i18n-audit.py
  python scripts/i18n-audit.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"

WIRED_PATHS = {
    "components/AppShell.tsx",
    "components/LanguageSwitcher.tsx",
    "components/NotificationBell.tsx",
    "components/ExplainButton.tsx",
    "app/projects/[id]/ask/page.tsx",
    "app/projects/[id]/reports/page.tsx",
    "app/audit/page.tsx",
    "app/notifications/page.tsx",
    "app/settings/page.tsx",
}

EXEMPT_PATTERNS = [
    re.compile(r"^app/.*/layout\.tsx$"),
    re.compile(r"^lib/api\.ts$"),
    re.compile(r"^lib/i18n"),
    re.compile(r"^lib/labels\.ts$"),
]

TEXT_ATTRS = re.compile(
    r'(placeholder|aria-label|title|alt)\s*=\s*"([^"]+)"',
    re.IGNORECASE,
)

CJK = re.compile(r"[\u3000-\u9fff]")
HAS_LETTER = re.compile(r"[A-Za-z]")
SKIP_STRINGS = {
    "use client", "use server", "GET", "POST", "PUT", "PATCH", "DELETE",
    "primary", "secondary", "danger", "wide", "sm", "md", "lg", "xl",
}

# English → likely key. Curated from what's already in lib/i18n.ts.
ENGLISH_TO_KEY = {
    # actions
    "Save": "action.save",
    "Cancel": "action.cancel",
    "Delete": "action.delete",
    "Edit": "action.edit",
    "Add": "action.add",
    "Create": "action.create",
    "Run": "action.run",
    "Refresh": "action.refresh",
    "Validate": "action.validate",
    "Download": "action.download",
    "Confirm": "action.confirm",
    "Close": "action.close",
    "Open": "action.open",
    "Back": "action.back",
    "Next": "action.next",
    "Reset": "action.reset",
    "Filter": "action.filter",
    "Clear": "action.clear",
    "Search": "action.search",
    # login
    "Sign in": "login.submit",
    "Email": "login.email",
    "Password": "login.password",
    "Incorrect email or password.": "login.badCredentials",
    # dashboard
    "Dashboard": "dashboard.title",
    "Projects": "projects.title",
    "Documents": "dashboard.documents",
    "Open impacts": "dashboard.openImpacts",
    "Stale deps": "dashboard.staleDeps",
    "Not validated": "dashboard.notValidated",
    "No projects yet.": "dashboard.noProjects",
    # projects list
    "New project": "projects.new",
    "Search projects": "projects.search",
    "Name": "projects.name",
    "Client": "projects.client",
    "Status": "projects.status",
    "Updated": "projects.updated",
    # project detail
    "Add document": "project.addDocument",
    "No documents in this project yet.": "project.noDocuments",
    "Search number or name": "project.searchDocs",
    "All disciplines": "project.filterDiscipline",
    "All statuses": "project.filterStatus",
    "All file types": "project.filterFileType",
    "Revision": "project.revisionFilter",
    "Modified since": "project.modifiedSince",
    "Number": "project.colNumber",
    "Discipline": "project.colDiscipline",
    "Author": "project.colAuthor",
    "Modified": "project.colModified",
    "History": "project.history",
    "Upload revision": "project.upload",
    "Validate for issue": "project.validateForIssue",
    "Impact": "project.impact",
    "Dependencies": "project.dependencies",
    "Ask": "project.ask",
    "Reports": "project.reports",
    "Audit": "project.audit",
    "Archive": "project.archive",
    "Restore": "project.restore",
    "Edit project": "project.editDialogTitle",
    "Delete project": "project.deleteDialogTitle",
    "Add document ": "project.addDocumentDialogTitle",
    "Project name": "project.projectName",
    "Description": "project.descriptionLabel",
    "Document number": "project.docNumber",
    "File": "project.file",
    "Revision number": "project.revisionNumber",
    "Change summary": "project.changeSummary",
    # rules
    "Rules": "rules.title",
    "Category": "rules.category",
    "Enabled": "rules.enabled",
    "Severity": "rules.severity",
    "Parameters": "rules.params",
    "Default": "rules.default",
    "Updated by": "rules.updatedBy",
    # dependencies
    "Add dependency": "deps.add",
    "Source": "deps.source",
    "Target": "deps.target",
    "Type": "deps.type",
    "Confidence": "deps.confidence",
    "Reason": "deps.reason",
    "Mark reviewed": "deps.validate",
    # impact
    "Impact analysis": "impact.title",
    "Score": "impact.score",
    "Distance": "impact.distance",
    "State": "impact.state",
    "Re-run analysis": "impact.reRun",
    "No impact to report yet.": "impact.noImpacts",
    "Details": "impact.details",
    # validation
    "Validation": "validation.title",
    "Run validation": "validation.run",
    "Rule": "validation.rule",
    "Document": "validation.document",
    "Element": "validation.element",
    "Message": "validation.message",
    "Acknowledge": "validation.acknowledge",
    "Revoke": "validation.revoke",
    "Open": "validation.open",
    "Acknowledged": "validation.acknowledged",
    # settings + profiles
    "Quality profiles": "profiles.title",
    "Project": "profiles.project",
    "Choose a project": "profiles.chooseProject",
    "Active profile:": "profiles.activeProfile",
    "none": "profiles.none",
    "Deactivate": "profiles.deactivate",
    "Id": "profiles.id",
    "Illustrative": "profiles.illustrative",
    "Activate": "profiles.activate",
    "Active": "profiles.active",
}


@dataclass
class Finding:
    file: str
    line: int
    kind: str
    text: str
    suggested_key: str | None = None


def _is_probably_english(value: str) -> bool:
    if not value or len(value) < 3:
        return False
    if value in SKIP_STRINGS:
        return False
    if CJK.search(value):
        return False
    if not HAS_LETTER.search(value):
        return False
    if value.startswith("http") or value.startswith("/") or value.startswith("#"):
        return False
    if re.fullmatch(r"[a-z0-9_-]+", value) and len(value) < 4:
        return False
    return True


def _suggest_key(value: str) -> str | None:
    v = value.strip()
    if v in ENGLISH_TO_KEY:
        return ENGLISH_TO_KEY[v]
    # Try stripping trailing punctuation
    stripped = v.rstrip(".:!?")
    if stripped in ENGLISH_TO_KEY:
        return ENGLISH_TO_KEY[stripped]
    return None


def _find_in_file(path: Path, rel: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return findings

    lines = text.splitlines()

    for i, line in enumerate(lines, start=1):
        for match in TEXT_ATTRS.finditer(line):
            attr, value = match.group(1), match.group(2)
            if _is_probably_english(value):
                findings.append(Finding(rel, i, f"attr:{attr}", value, _suggest_key(value)))

    for i, line in enumerate(lines, start=1):
        for match in re.finditer(r">([A-Z][^<>{}]{4,80})<", line):
            value = match.group(1).strip()
            if _is_probably_english(value) and " " in value:
                findings.append(Finding(rel, i, "jsx-text", value, _suggest_key(value)))

    for i, line in enumerate(lines, start=1):
        for match in re.finditer(r'(?:label|title|message|placeholder)\s*:\s*"([^"]{4,80})"', line):
            value = match.group(1)
            if _is_probably_english(value):
                findings.append(Finding(rel, i, "obj-literal", value, _suggest_key(value)))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not SRC_ROOT.exists():
        print(f"error: {SRC_ROOT} does not exist", file=sys.stderr)
        return 1

    all_findings: list[Finding] = []
    scanned = 0
    wired = 0

    for path in sorted(SRC_ROOT.rglob("*.tsx")):
        rel = str(path.relative_to(SRC_ROOT)).replace("\\", "/")
        if rel in WIRED_PATHS:
            wired += 1
            continue
        if any(p.search(rel) for p in EXEMPT_PATTERNS):
            continue
        scanned += 1
        all_findings.extend(_find_in_file(path, rel))

    if args.json:
        print(json.dumps(
            {"scanned": scanned, "wired": wired, "findings": [asdict(f) for f in all_findings]},
            indent=2,
        ))
        return 0

    mapped = [f for f in all_findings if f.suggested_key]
    unmapped = [f for f in all_findings if not f.suggested_key]

    print(f"i18n audit")
    print(f"=========")
    print(f"Scanned:  {scanned} files")
    print(f"Wired:    {wired} files (excluded)")
    print(f"Findings: {len(all_findings)}  ({len(mapped)} mapped to a key, {len(unmapped)} need a new key)")
    print("")

    if not all_findings:
        print("No hardcoded English found in scanned files. Wiring is complete.")
        return 0

    by_file: dict[str, list[Finding]] = {}
    for f in all_findings:
        by_file.setdefault(f.file, []).append(f)

    for fname in sorted(by_file):
        group = by_file[fname]
        m = sum(1 for f in group if f.suggested_key)
        print(f"{fname}  ({len(group)} strings, {m} mapped)")
        for f in group:
            text = f.text if len(f.text) <= 60 else f.text[:57] + "..."
            key = f.suggested_key or "(no key yet)"
            print(f"  L{f.line:<5} [{f.kind:18}] {text:60}  -> {key}")
        print("")

    print(f"Next: wire the mapped strings first, then add keys for the unmapped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())