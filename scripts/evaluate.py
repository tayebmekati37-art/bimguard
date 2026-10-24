"""Measure BIMGuard rule accuracy on a labeled dataset.

What this measures:
  For each (rule_id, document_number) pair in the dataset's expected
  findings, and for each pair the engine actually produced, compute
  per-rule precision, recall, and F1.

What "ground truth" means:
  The labels are by design. Every document was constructed to either
  trigger or not trigger specific rules. That construction is the ground
  truth. This is NOT a validation study against human-labelled real
  projects. Do not present these numbers as real-world accuracy.

What is NOT measured:
  See the dataset's not_measured block. Rules not listed in
  measured_rules are excluded from precision/recall. Findings from those
  rules are reported separately as "unmeasured-rule findings".

Run with the API venv python:
  apps\\api\\.venv\\Scripts\\python.exe scripts\\evaluate.py
or via the orchestrator:
  scripts\\run-evaluation.ps1
"""
from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run with apps/api/.venv/Scripts/python.exe")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT / "benchmark" / "dataset.json"
LAST_RUN_PATH = ROOT / "benchmark" / "last-run.json"
RESULTS_MD_PATH = ROOT / "docs" / "evaluation" / "results.md"
BASE_URL = "http://127.0.0.1:8000"

PASSWORD = "admin-demo-pass"
ADMIN_EMAIL = "admin@example.local"


class API:
    def __init__(self) -> None:
        self.client = httpx.Client(base_url=BASE_URL, timeout=120.0)
        self.token: str | None = None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def login(self) -> None:
        r = self.client.post("/auth/login", data={"username": ADMIN_EMAIL, "password": PASSWORD})
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def find_project(self, name: str) -> str | None:
        r = self.client.get("/projects", params={"q": name, "limit": 100}, headers=self._headers())
        r.raise_for_status()
        for p in r.json()["items"]:
            if p["name"] == name:
                return p["id"]
        return None

    def delete_project(self, project_id: str) -> None:
        r = self.client.delete(f"/projects/{project_id}", headers=self._headers())
        r.raise_for_status()

    def create_project(self, name: str, description: str) -> str:
        r = self.client.post(
            "/projects",
            json={"name": name, "client": "", "description": description},
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()["id"]

    def create_document(self, project_id: str, number: str, name: str, discipline: str, author: str) -> str:
        r = self.client.post(
            f"/projects/{project_id}/documents",
            json={"document_number": number, "name": name, "discipline": discipline, "author": author},
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()["id"]

    def upload_revision(self, document_id: str, content: bytes, revision_number: int, status: str) -> dict:
        files = {"file": ("revision.json", content, "application/json")}
        data = {"revision_number": str(revision_number), "status": status, "change_summary": ""}
        r = self.client.post(
            f"/documents/{document_id}/revisions",
            files=files, data=data, headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()

    def wait_extraction(self, document_id: str, timeout: int = 30) -> None:
        for _ in range(timeout):
            r = self.client.get(f"/documents/{document_id}/revisions", headers=self._headers())
            r.raise_for_status()
            revisions = r.json()
            if all(rv["extraction_status"] != "pending" for rv in revisions):
                return
            time.sleep(1)
        raise RuntimeError(f"extraction did not complete for document {document_id}")

    def create_dependency(
        self, project_id: str, source_id: str, target_id: str,
        rel_type: str, confidence: float, reason: str,
    ) -> None:
        r = self.client.post(
            "/dependencies",
            json={
                "project_id": project_id,
                "source_document_id": source_id,
                "target_document_id": target_id,
                "relationship_type": rel_type,
                "confidence": confidence,
                "reason": reason,
            },
            headers=self._headers(),
        )
        r.raise_for_status()

    def trigger_compare(self, revision_id: str) -> None:
        r = self.client.post(f"/revisions/{revision_id}/compare", headers=self._headers())
        # Accept 200 or 201; report other statuses as errors
        if r.status_code not in (200, 201, 409):
            r.raise_for_status()

    def trigger_impact(self, project_id: str) -> None:
        r = self.client.post(f"/projects/{project_id}/impact-analysis", headers=self._headers())
        if r.status_code not in (200, 201, 404):
            r.raise_for_status()

    def validate(self, project_id: str) -> dict:
        r = self.client.post(f"/projects/{project_id}/validate", headers=self._headers())
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


def fixture_content(key: str, elements: list[dict] | None = None) -> bytes:
    payload = {"schema": "bimguard.elements/1", "elements": elements or [], "note": key}
    return json.dumps(payload).encode("utf-8")


def build_project(api: API, spec: dict) -> dict:
    name = spec["name"]
    print(f"\n=== Building {name} ===")

    # Idempotent: delete an existing eval project with this name
    existing = api.find_project(name)
    if existing:
        print(f"  deleting existing project {existing}")
        api.delete_project(existing)

    project_id = api.create_project(name, spec.get("description", ""))
    print(f"  created project {project_id}")

    doc_ids: dict[str, str] = {}
    for doc in spec["documents"]:
        doc_id = api.create_document(project_id, doc["document_number"], doc["name"], doc["discipline"], doc["author"])
        doc_ids[doc["document_number"]] = doc_id
    print(f"  created {len(doc_ids)} documents")

    # Upload first revision of every document (if any)
    rev_meta: dict[str, dict[int, dict]] = {}
    for doc in spec["documents"]:
        if not doc["revisions"]:
            continue
        first = doc["revisions"][0]
        revision = api.upload_revision(
            doc_ids[doc["document_number"]],
            fixture_content(first["content_key"], first.get("elements")),
            first["revision_number"],
            first["status"],
        )
        rev_meta.setdefault(doc["document_number"], {})[first["revision_number"]] = revision
    print(f"  uploaded first revisions")

    # Create dependencies now, so a later v2 upload makes them stale by design
    for dep in spec.get("dependencies", []):
        api.create_dependency(
            project_id,
            doc_ids[dep["source_number"]],
            doc_ids[dep["target_number"]],
            dep["type"],
            float(dep["confidence"]),
            dep["reason"],
        )
    print(f"  created {len(spec.get('dependencies', []))} dependencies")

    # Upload remaining revisions (v2, v3, ...)
    for doc in spec["documents"]:
        for rev in doc["revisions"][1:]:
            revision = api.upload_revision(
                doc_ids[doc["document_number"]],
                fixture_content(rev["content_key"], rev.get("elements")),
                rev["revision_number"],
                rev["status"],
            )
            rev_meta.setdefault(doc["document_number"], {})[rev["revision_number"]] = revision
    print(f"  uploaded remaining revisions")

    # Wait for all extractions
    for doc_id in doc_ids.values():
        api.wait_extraction(doc_id)
    print(f"  extractions complete")

    # Trigger comparison for any revision with a previous
    compared = 0
    for doc_number, revs in rev_meta.items():
        for rev_num, rev in revs.items():
            if rev.get("previous_revision_id"):
                api.trigger_compare(rev["id"])
                compared += 1
    print(f"  triggered {compared} comparison(s)")

    # Trigger impact analysis
    api.trigger_impact(project_id)
    print(f"  triggered impact analysis")

    # Run validation
    run = api.validate(project_id)
    issues = api.list_issues(run["id"])
    print(f"  validation run {run['id']}: status={run['status']}, {len(issues)} issue(s)")

    return {
        "project_id": project_id,
        "project_name": name,
        "expected_readiness": spec["expected_readiness"],
        "actual_readiness": run["status"],
        "expected_findings": [(f["rule_id"], f["document_number"]) for f in spec["expected_findings"]],
        "actual_findings": [(i["rule_id"], i["document_number"]) for i in issues],
        "raw_issues": issues,
    }


def compute_metrics(results: list[dict], measured_rules: list[str], unmeasured_rule_ids: set[str]) -> dict:
    # Aggregate all expected and actual pairs across projects
    expected_all: set[tuple[str, str]] = set()
    actual_all: set[tuple[str, str]] = set()
    for r in results:
        expected_all.update(r["expected_findings"])
        actual_all.update(r["actual_findings"])

    per_rule: dict[str, dict] = {}
    for rule in measured_rules:
        expected_rule = {(r, d) for (r, d) in expected_all if r == rule}
        actual_rule = {(r, d) for (r, d) in actual_all if r == rule}
        tp = len(expected_rule & actual_rule)
        fp = len(actual_rule - expected_rule)
        fn = len(expected_rule - actual_rule)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        per_rule[rule] = {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "expected_pairs": sorted(expected_rule),
            "actual_pairs": sorted(actual_rule),
        }

    # Unmeasured rule fires (informational; not scored)
    unmeasured_fires: list[tuple[str, str]] = sorted(
        [(r, d) for (r, d) in actual_all if r in unmeasured_rule_ids or r not in measured_rules]
    )

    # Project-level readiness check
    readiness = [
        {
            "project": r["project_name"],
            "expected": r["expected_readiness"],
            "actual": r["actual_readiness"],
            "pass": r["expected_readiness"] == r["actual_readiness"],
        }
        for r in results
    ]

    return {
        "per_rule": per_rule,
        "unmeasured_fires": unmeasured_fires,
        "readiness": readiness,
        "measured_rule_count": len(measured_rules),
    }


def render_markdown(dataset: dict, metrics: dict, run_started: datetime) -> str:
    lines: list[str] = []
    lines.append("# Benchmark results")
    lines.append("")
    lines.append(f"Generated: {run_started.isoformat()}")
    lines.append("")
    lines.append("## What this measures")
    lines.append("")
    lines.append(
        "Precision and recall for the rules listed under *Measured rules*, on a "
        "synthetic dataset whose expected findings are defined by construction. "
        "See `docs/evaluation/methodology.md` for the full scope and limitations."
    )
    lines.append("")
    lines.append("## Readiness assertions")
    lines.append("")
    lines.append("| Project | Expected | Actual | Pass |")
    lines.append("| :--- | :--- | :--- | :--- |")
    for r in metrics["readiness"]:
        status = "PASS" if r["pass"] else "FAIL"
        lines.append(f"| `{r['project']}` | {r['expected']} | {r['actual']} | {status} |")
    lines.append("")
    lines.append("## Measured rules")
    lines.append("")
    lines.append("| Rule | TP | FP | FN | Precision | Recall | F1 |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for rule, m in metrics["per_rule"].items():
        lines.append(
            f"| `{rule}` | {m['tp']} | {m['fp']} | {m['fn']} | "
            f"{m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} |"
        )
    lines.append("")

    # Detail: any rule with fp or fn
    mismatches = {r: m for r, m in metrics["per_rule"].items() if m["fp"] > 0 or m["fn"] > 0}
    if mismatches:
        lines.append("## Mismatches")
        lines.append("")
        for rule, m in mismatches.items():
            lines.append(f"### `{rule}`")
            if m["fp"] > 0:
                fp_pairs = sorted(set(m["actual_pairs"]) - set(m["expected_pairs"]))
                lines.append(f"False positives: {fp_pairs}")
            if m["fn"] > 0:
                fn_pairs = sorted(set(m["expected_pairs"]) - set(m["actual_pairs"]))
                lines.append(f"False negatives: {fn_pairs}")
            lines.append("")
    else:
        lines.append("No mismatches. Every measured rule fired on exactly the documents it was expected to, and on none it was not.")
        lines.append("")

    if metrics["unmeasured_fires"]:
        lines.append("## Findings from unmeasured rules")
        lines.append("")
        lines.append(
            "These findings came from rules that are not scored in v1 (see "
            "`benchmark/dataset.json` under `not_measured`). They are reported "
            "for completeness, not counted in precision/recall."
        )
        lines.append("")
        for rule, doc in metrics["unmeasured_fires"]:
            lines.append(f"- `{rule}` on `{doc}`")
        lines.append("")
    else:
        lines.append("## Findings from unmeasured rules")
        lines.append("")
        lines.append("None. Every finding came from a rule that was measured.")
        lines.append("")

    lines.append("## Not measured")
    lines.append("")
    lines.append("The following rules are documented as out of scope for this evaluation and why:")
    lines.append("")
    for rule, reason in dataset["not_measured"].items():
        if rule.endswith("_note"):
            continue
        lines.append(f"- `{rule}` — {reason}")
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    lines.append("- **Synthetic dataset.** The labels come from the designer's intent, not from a BIM engineer's review of real project data. Precision and recall here measure whether the engine finds what the fixture designer said it should find.")
    lines.append("- **8 of 18 rules measured.** The remaining 10 need fixtures the current HTTP-only setup cannot construct (element-level geometry, cross-document psets, manufacturing-domain setup).")
    lines.append("- **Single project per scenario.** One clean project and one problem project. Real projects have many more permutations and false-positive opportunities.")
    lines.append("- **No cross-machine testing.** These numbers were produced on one machine with one API version.")
    lines.append("- **Do not interpret as real-world accuracy.** These numbers do not generalize to commercial BIM projects. That would require an independently labelled dataset from a real project.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if not DATASET_PATH.exists():
        print(f"ERROR: dataset not found: {DATASET_PATH}")
        return 1

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    measured_rules = dataset["measured_rules"]
    unmeasured_rule_ids = set(dataset["not_measured"].keys())

    run_started = datetime.now(UTC)
    api = API()
    print("Logging in...")
    api.login()

    results: list[dict] = []
    for spec in dataset["projects"]:
        results.append(build_project(api, spec))

    metrics = compute_metrics(results, measured_rules, unmeasured_rule_ids)

    # Write JSON results
    output = {
        "dataset_version": dataset.get("version"),
        "run_started": run_started.isoformat(),
        "base_url": BASE_URL,
        "measured_rules": measured_rules,
        "per_rule": metrics["per_rule"],
        "readiness": metrics["readiness"],
        "unmeasured_fires": metrics["unmeasured_fires"],
        "results": results,
    }
    LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN_PATH.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {LAST_RUN_PATH}")

    # Write markdown
    RESULTS_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_MD_PATH.write_text(render_markdown(dataset, metrics, run_started), encoding="utf-8")
    print(f"Wrote {RESULTS_MD_PATH}")

    # Console summary
    print("\n=== Summary ===")
    for rule, m in metrics["per_rule"].items():
        print(f"  {rule:32s}  P={m['precision']:.2f}  R={m['recall']:.2f}  F1={m['f1']:.2f}")
    print("\n=== Readiness ===")
    for r in metrics["readiness"]:
        print(f"  {r['project']:20s}  expected={r['expected']:20s}  actual={r['actual']:20s}  {'PASS' if r['pass'] else 'FAIL'}")

    # Exit non-zero if any measured rule has FP or FN, or readiness mismatched
    has_errors = (
        any(m["fp"] > 0 or m["fn"] > 0 for m in metrics["per_rule"].values())
        or any(not r["pass"] for r in metrics["readiness"])
    )
    return 0 if not has_errors else 2


if __name__ == "__main__":
    sys.exit(main())