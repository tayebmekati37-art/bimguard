"""Export a real project's validation findings to a labeling CSV (M28).

Runs against a live BIMGuard API. Picks one project, gets its latest
validation run, and produces a CSV with one row per finding. A BIM
engineer fills in `labeler_correct` (Y/N), optionally `labeler_severity_ok`
and a note, and adds rows at the bottom for findings the engine missed
(leave finding_id empty, fill rule_id + document_number + note).

Usage:
    python scripts/export-for-labeling.py --project <uuid> --out labeled.csv
    python scripts/export-for-labeling.py --list-projects
    python scripts/export-for-labeling.py --project <uuid> --out labeled.csv --api http://127.0.0.1:8000

Requires the API running on the given URL, and admin-demo-pass for
admin@example.local (the seeded demo user).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("[FAIL] httpx not installed. Run with apps/api/.venv/Scripts/python.exe", file=sys.stderr)
    sys.exit(1)

DEFAULT_API = "http://127.0.0.1:8000"
ADMIN_EMAIL = "admin@example.local"
ADMIN_PASSWORD = "admin-demo-pass"

COLUMNS = [
    "finding_id", "rule_id", "document_number", "element_tag",
    "severity", "title", "message", "recommended_action",
    "labeler_correct", "labeler_severity_ok", "labeler_note",
]

INSTRUCTIONS = """
# BIMGuard labeling instructions

# For each row below (non-blank finding_id), put Y or N in `labeler_correct`:
#   Y = the engine was right to report this
#   N = the engine should not have reported this (false positive)
#
# If Y, optionally put Y or N in `labeler_severity_ok`:
#   Y = the severity (CRITICAL/HIGH/MEDIUM/LOW) is appropriate
#   N = the severity should be different; explain in `labeler_note`
#
# For findings the engine MISSED:
#   Add new rows at the bottom with:
#     - finding_id: leave EMPTY
#     - rule_id: which rule should have fired
#     - document_number: which document
#     - element_tag: optional, if element-specific
#     - labeler_note: one sentence, why this is a missed finding
#   Do NOT fill labeler_correct for additions; the fact you added the row
#   means it's a missed finding.
#
# Base judgement on the rule's stated description, not on what you would
# prefer it to check. A rule that fires correctly according to its own
# description is a Y, even if you disagree with the rule's existence.
#
# Leave labeler_correct empty if you are not sure. That row will be
# excluded from metrics and the unlabeled rate will be reported.
"""


class Api:
    def __init__(self, base_url: str) -> None:
        self.client = httpx.Client(base_url=base_url, timeout=60.0)
        self.token: str | None = None

    def login(self) -> None:
        r = self.client.post("/auth/login", data={
            "username": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
        })
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def list_projects(self) -> list[dict]:
        r = self.client.get("/projects", params={"limit": 200}, headers=self._headers())
        r.raise_for_status()
        return r.json()["items"]

    def project(self, project_id: str) -> dict:
        r = self.client.get(f"/projects/{project_id}", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def latest_run(self, project_id: str) -> dict:
        r = self.client.get(f"/projects/{project_id}/validation-runs/latest", headers=self._headers())
        if r.status_code == 404:
            raise SystemExit(
                f"[FAIL] project {project_id} has not been validated yet. "
                "Run validation first (POST /projects/{id}/validate)."
            )
        r.raise_for_status()
        return r.json()

    def list_issues(self, run_id: str) -> list[dict]:
        out: list[dict] = []
        offset = 0
        while True:
            r = self.client.get(
                f"/validation-runs/{run_id}/issues",
                params={"limit": 200, "offset": offset},
                headers=self._headers(),
            )
            r.raise_for_status()
            page = r.json()
            out.extend(page["items"])
            if len(page["items"]) < 200:
                return out
            offset += 200


def build_row(issue: dict) -> dict:
    """Convert a validation issue from the API into a labeling CSV row."""
    return {
        "finding_id": issue.get("id", ""),
        "rule_id": issue.get("rule_id", ""),
        "document_number": issue.get("document_number", ""),
        "element_tag": issue.get("element_tag", ""),
        "severity": issue.get("severity", ""),
        "title": issue.get("title", ""),
        "message": issue.get("message", ""),
        "recommended_action": issue.get("recommended_action", ""),
        "labeler_correct": "",
        "labeler_severity_ok": "",
        "labeler_note": "",
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        # Instructions as comment lines are not valid CSV, so write them
        # to a sibling .txt file instead. The CSV itself is pure data.
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in COLUMNS})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="", help="Project UUID to export findings for")
    ap.add_argument("--out", default="", help="Output CSV path")
    ap.add_argument("--api", default=DEFAULT_API, help="API base URL")
    ap.add_argument("--list-projects", action="store_true", help="List projects and exit")
    args = ap.parse_args()

    api = Api(args.api)
    try:
        api.login()
    except Exception as e:
        print(f"[FAIL] could not log in to {args.api}: {e}", file=sys.stderr)
        return 1

    if args.list_projects:
        try:
            projects = api.list_projects()
        except Exception as e:
            print(f"[FAIL] could not list projects: {e}", file=sys.stderr)
            return 1
        print(f"{'id':38s}  {'documents':>10s}  {'status':10s}  name")
        for p in projects:
            print(f"{p['id']:38s}  {p.get('document_count', 0):10d}  {p.get('status', ''):10s}  {p.get('name', '')}")
        return 0

    if not args.project or not args.out:
        print("[FAIL] --project and --out are required (or use --list-projects)", file=sys.stderr)
        return 1

    try:
        project = api.project(args.project)
    except Exception as e:
        print(f"[FAIL] could not fetch project {args.project}: {e}", file=sys.stderr)
        return 1

    try:
        run = api.latest_run(args.project)
    except Exception as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1

    try:
        issues = api.list_issues(run["id"])
    except Exception as e:
        print(f"[FAIL] could not list issues: {e}", file=sys.stderr)
        return 1

    rows = [build_row(i) for i in issues]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_csv(out, rows)

    # Also write the instructions as a sibling text file, so the CSV stays pure data.
    instructions_path = out.with_suffix(out.suffix + ".readme.txt")
    instructions_path.write_text(INSTRUCTIONS, encoding="utf-8")

    print(f"[OK] Wrote {len(rows)} findings to {out}")
    print(f"[OK] Instructions: {instructions_path}")
    print()
    print(f"Project: {project.get('name')} ({project['id']})")
    print(f"Validation run: {run['id']} (status: {run.get('status')})")
    print(f"Findings: {len(rows)}")
    print()
    print("Send both files to the BIM engineer. They fill in the CSV and return it.")
    print("Then run: python scripts/eval-from-labels.py --labeled <returned.csv>")
    return 0


if __name__ == "__main__":
    sys.exit(main())