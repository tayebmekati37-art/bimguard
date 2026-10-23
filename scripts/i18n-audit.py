"""Find hardcoded English strings in the frontend that need t() wrapping.

Not a linter. A practical finder. Reports:
  - JSX text nodes that are literal English
  - String props (placeholder, aria-label, title, alt) with literal English
  - JSX string literals in common attributes

Each finding includes the file, line, and the offending string. Use it as
a checklist for M21b wiring. Does not modify files.

Usage:
  cd C:\\dev\\bimguard
  python scripts/i18n-audit.py
  python scripts/i18n-audit.py --json   # machine-readable
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"

# Files already wired or exempted.
WIRED_PATHS = {
    "components/AppShell.tsx",
    "components/LanguageSwitcher.tsx",
    "app/projects/[id]/ask/page.tsx",
    "app/projects/[id]/reports/page.tsx",
    "app/audit/page.tsx",
    "app/notifications/page.tsx",
    "app/settings/page.tsx",
}

# Modules that should never be scanned.
EXEMPT_PATTERNS = [
    re.compile(r"^app/.*/layout\.tsx$"),
    re.compile(r"^lib/api\.ts$"),
    re.compile(r"^lib/i18n"),
    re.compile(r"^lib/labels\.ts$"),
    re.compile(r"^components/ui\.tsx$"),
]

# Attributes that commonly hold user-facing text.
TEXT_ATTRS = re.compile(
    r'(placeholder|aria-label|title|alt)\s*=\s*"([^"]+)"',
    re.IGNORECASE,
)

# A rough heuristic for "English-looking": at least one letter, no CJK
# characters, and more than two letters so single-letter props don't trip.
CJK = re.compile(r"[\u3000-\u9fff]")
HAS_LETTER = re.compile(r"[A-Za-z]")
SKIP_STRINGS = {
    "use client", "use server", "GET", "POST", "PUT", "PATCH", "DELETE",
    "primary", "secondary", "danger", "wide", "sm", "md", "lg", "xl",
}


@dataclass
class Finding:
    file: str
    line: int
    kind: str
    text: str


def _is_probably_english(value: str) -> bool:
    if not value or len(value) < 3:
        return False
    if value in SKIP_STRINGS:
        return False
    if CJK.search(value):
        return False
    if not HAS_LETTER.search(value):
        return False
    # Class strings, urls, hex, etc.
    if value.startswith("http") or value.startswith("/") or value.startswith("#"):
        return False
    if re.fullmatch(r"[a-z0-9_-]+", value) and len(value) < 4:
        return False
    return True


def _find_in_file(path: Path, rel: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return findings

    lines = text.splitlines()

    # 1. Attribute-based text
    for i, line in enumerate(lines, start=1):
        for match in TEXT_ATTRS.finditer(line):
            attr, value = match.group(1), match.group(2)
            if _is_probably_english(value):
                findings.append(Finding(rel, i, f"attr:{attr}", value))

    # 2. Literal JSX text nodes like >Some text<
    for i, line in enumerate(lines, start=1):
        for match in re.finditer(r">([A-Z][^<>{}]{4,80})<", line):
            value = match.group(1).strip()
            if _is_probably_english(value) and " " in value:
                findings.append(Finding(rel, i, "jsx-text", value))

    # 3. Common patterns: toast/label calls with literal strings
    for i, line in enumerate(lines, start=1):
        for match in re.finditer(r'(?:label|title|message|placeholder)\s*:\s*"([^"]{4,80})"', line):
            value = match.group(1)
            if _is_probably_english(value):
                findings.append(Finding(rel, i, "obj-literal", value))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
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
        return 0 if not all_findings else 0

    print(f"i18n audit")
    print(f"=========")
    print(f"Scanned: {scanned} files")
    print(f"Wired:   {wired} files (excluded from scan)")
    print(f"Findings: {len(all_findings)}")
    print("")

    if not all_findings:
        print("No hardcoded English found in scanned files.")
        return 0

    by_file: dict[str, list[Finding]] = {}
    for f in all_findings:
        by_file.setdefault(f.file, []).append(f)

    for fname in sorted(by_file):
        group = by_file[fname]
        print(f"{fname}  ({len(group)})")
        for f in group:
            marker = {"attr:placeholder": "attr:placeholder", "attr:aria-label": "attr:aria-label",
                      "attr:title": "attr:title", "attr:alt": "attr:alt",
                      "jsx-text": "text", "obj-literal": "literal"}.get(f.kind, f.kind)
            text = f.text if len(f.text) <= 70 else f.text[:67] + "..."
            print(f"  L{f.line:<5} [{marker:18}] {text}")
        print("")

    print(f"Wiring these is M21b. Dictionary keys are already present in lib/i18n.ts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())