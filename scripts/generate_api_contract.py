import sys
sys.path.insert(0, r"C:\dev\bimguard\apps\api")
from app.main import app

lines = []
lines.append("# BIMGuard API contract")
lines.append("")
lines.append("Version: 1.0.0 (Milestone 15)")
lines.append("")
lines.append("Every endpoint below is part of the stable API. All endpoints except")
lines.append("`POST /auth/login` require a Bearer token in the `Authorization` header.")
lines.append("")
lines.append("Roles: `admin`, `bim_coordinator`, `engineer`, `reviewer`, `viewer`.")
lines.append("Read endpoints are open to any authenticated user unless noted.")
lines.append("")
lines.append("## Endpoints")
lines.append("")
lines.append("| Method | Path | Purpose |")
lines.append("| --- | --- | --- |")

# Curated purposes keyed by (method, path)
purposes = {
    ("POST", "/auth/login"): "Form-encoded login; returns `{access_token}`.",
    ("GET", "/auth/me"): "Current authenticated user.",
    ("GET", "/health"): "Liveness probe.",
    ("GET", "/projects"): "List projects, paginated.",
    ("POST", "/projects"): "Create project. Admin or BIM coordinator.",
    ("GET", "/projects/{project_id}"): "One project.",
    ("PATCH", "/projects/{project_id}"): "Update project. Admin or BIM coordinator.",
    ("DELETE", "/projects/{project_id}"): "Delete project. Admin only.",
    ("GET", "/projects/{project_id}/documents"): "List documents in a project.",
    ("POST", "/projects/{project_id}/documents"): "Add document. Engineer or above.",
    ("GET", "/documents/{document_id}"): "One document.",
    ("PATCH", "/documents/{document_id}"): "Update document metadata.",
    ("POST", "/documents/{document_id}/revisions"): "Upload a revision (multipart).",
    ("GET", "/documents/{document_id}/revisions"): "List revisions of a document.",
    ("PATCH", "/revisions/{revision_id}/status"): "Change revision status.",
    ("GET", "/revisions/{revision_id}/download"): "Download the original file.",
    ("GET", "/revisions/{revision_id}/elements.json"): "Export extracted elements as bimguard.elements/1. M15.",
    ("POST", "/revisions/{revision_id}/verify-round-trip"): "Verify the canonical JSON round-trip. M15.",
    ("POST", "/revisions/{revision_id}/verify-source"): "Re-parse the uploaded file and diff GUIDs. M15.",
    ("GET", "/projects/{project_id}/graph"): "Dependency graph with health states.",
    ("POST", "/dependencies"): "Register a typed dependency.",
    ("DELETE", "/dependencies/{id}"): "Delete a dependency.",
    ("POST", "/dependencies/{id}/validate"): "Mark a dependency reviewed against the current revision.",
    ("GET", "/documents/{document_id}/impact"): "Impact traversal from one document.",
    ("GET", "/projects/{project_id}/impact-analysis"): "Latest impact events for the project.",
    ("POST", "/projects/{project_id}/impact-analysis"): "Re-run impact analysis. Engineer or above.",
    ("GET", "/rules"): "List every rule with its current configuration.",
    ("PATCH", "/rules/{rule_id}"): "Update one rule's config. Admin only.",
    ("POST", "/rules/{rule_id}/reset"): "Reset one rule to factory defaults. Admin only.",
    ("POST", "/projects/{project_id}/validate"): "Run every enabled rule. Engineer or above.",
    ("GET", "/projects/{project_id}/validation-runs"): "List validation runs.",
    ("GET", "/projects/{project_id}/validation-runs/latest"): "Latest validation run.",
    ("GET", "/validation-runs/{run_id}"): "One validation run.",
    ("GET", "/validation-runs/{run_id}/issues"): "Issues of a run, filtered and paginated.",
    ("POST", "/issues/{issue_id}/acknowledge"): "Accept an issue with a note. Reviewer or above.",
    ("DELETE", "/issues/{issue_id}/acknowledge"): "Revoke an acknowledgement.",
    ("GET", "/projects/{project_id}/health"): "Live project health.",
    ("GET", "/dashboard"): "Aggregate across all projects.",
    ("GET", "/search"): "Cross-entity search.",
    ("GET", "/documents/{document_id}/overview"): "Everything about one document at a glance.",
    ("GET", "/projects/{project_id}/reports/readiness.json"): "Readiness report as JSON. M10.",
    ("GET", "/projects/{project_id}/reports/readiness.csv"): "Readiness report as CSV. M10.",
    ("GET", "/projects/{project_id}/reports/readiness.pdf"): "Readiness report as PDF. M10.",
    ("GET", "/notifications"): "In-app notifications for the current user. M10.",
    ("GET", "/notifications/unread-count"): "Unread count. M10.",
    ("POST", "/notifications/{notification_id}/read"): "Mark one notification read. M10.",
    ("POST", "/notifications/read-all"): "Mark all read. M10.",
    ("GET", "/audit-logs"): "Audit log, filterable by project and action.",
    ("POST", "/projects/{project_id}/ask"): "Ask a question, answered by facts + optional AI. M9.",
    ("GET", "/ai/status"): "Whether AI is configured on the server. M9.",
    ("GET", "/profiles"): "List quality profiles. M13.",
    ("GET", "/profiles/{profile_id}"): "One quality profile. M13.",
    ("GET", "/projects/{project_id}/profile"): "Active profile for a project. M13.",
    ("PUT", "/projects/{project_id}/profile"): "Activate a profile for a project. M13.",
    ("DELETE", "/projects/{project_id}/profile"): "Deactivate the profile. M13.",
}

def normalize(path):
    # Pydantic generates paths like /projects/{project_id}; the table above uses the same
    return path

rows = []
for route in app.routes:
    if not hasattr(route, "methods"):
        continue
    methods = sorted(route.methods - {"HEAD", "OPTIONS"})
    for m in methods:
        rows.append((m, route.path))

rows.sort(key=lambda r: (r[1], r[0]))

seen = set()
for method, path in rows:
    if (method, path) in seen:
        continue
    seen.add((method, path))
    purpose = purposes.get((method, path), "")
    lines.append(f"| `{method}` | `{path}` | {purpose} |")

lines.append("")
lines.append("## Authentication")
lines.append("")
lines.append("Send `Authorization: Bearer <token>` on every request except `POST /auth/login`.")
lines.append("The token comes from the `access_token` field of the login response.")
lines.append("")
lines.append("## Errors")
lines.append("")
lines.append("- `401` - missing or invalid token")
lines.append("- `403` - authenticated but not permitted")
lines.append("- `404` - resource not found")
lines.append("- `409` - conflict (duplicate, archived project, already acknowledged)")
lines.append("- `422` - validation error (body shape, field values)")
lines.append("")
lines.append("## Stability")
lines.append("")
lines.append("Everything in this list is stable. Additions are allowed; removals and")
lines.append("renames are not. If a breaking change is ever needed it gets a new path.")
lines.append("")
lines.append("Generated by `scripts/generate_api_contract.py` from `app.main.app.routes`.")
lines.append("The purpose column is maintained by hand. Regenerate whenever endpoints")
lines.append("change; add a purpose for new ones.")

out = "\n".join(lines) + "\n"
with open(r"C:\dev\bimguard\docs\api\contract.md", "w", encoding="utf-8", newline="\n") as fh:
    fh.write(out)
print(f"wrote {len(rows)} endpoints")