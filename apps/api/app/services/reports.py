"""Readiness report data builder.

Builds one plain dict from the project's current health and its latest
validation run. The dict is the single source of truth for the JSON, CSV
and PDF exporters, so all three formats agree.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models.project import Project
from app.models.validation import ValidationIssue, ValidationRun
from app.services import health as health_service


def _issue_row(issue: ValidationIssue) -> dict:
    return {
        "id": issue.id,
        "rule_id": issue.rule_id,
        "severity": issue.severity,
        "category": (issue.details or {}).get("category", ""),
        "document_id": issue.document_id,
        "document_number": issue.document_number,
        "element_tag": issue.element_tag,
        "title": issue.title,
        "message": issue.message,
        "recommended_action": issue.recommended_action,
        "status": issue.status,
        "acknowledged_by_name": issue.acknowledged_by_name,
        "acknowledgement_note": issue.acknowledgement_note,
    }


def build_readiness_report(db: Session, project: Project) -> dict:
    """Assemble the readiness report as a plain dict."""
    health = health_service.project_health(db, project)
    validation_summary = health.get("validation")
    issues: list[dict] = []
    run_meta: dict | None = None

    if validation_summary:
        run = db.get(ValidationRun, validation_summary["run_id"])
        if run is not None:
            run_meta = {
                "id": run.id,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "created_by_name": run.created_by_name,
                "status": run.status,
                "duration_ms": run.duration_ms,
                "summary": run.summary or {},
            }
            rows = db.scalars(
                select(ValidationIssue)
                .where(ValidationIssue.run_id == run.id)
                .order_by(ValidationIssue.severity, ValidationIssue.document_number, ValidationIssue.rule_id)
            ).all()
            issues = [_issue_row(i) for i in rows]

    project_status = project.status.value if hasattr(project.status, "value") else str(project.status)
    readiness_status = validation_summary["status"] if validation_summary else "NOT_VALIDATED"

    return {
        "generated_at": utcnow().isoformat(),
        "schema_version": 1,
        "project": {
            "id": project.id,
            "name": project.name,
            "client": project.client,
            "status": project_status,
        },
        "summary": {
            "readiness_status": readiness_status,
            "documents": health.get("documents", 0),
            "documents_with_revision": health.get("documents_with_revision", 0),
            "disciplines": health.get("disciplines", {}),
            "dependencies": health.get("dependencies", 0),
            "stale_dependencies": health.get("stale_dependencies", 0),
            "open_impacts": health.get("open_impacts", {"total": 0, "by_severity": {}}),
            "document_health": health.get("document_health", {}),
            "issue_counts": {
                "total": len(issues),
                "open": sum(1 for i in issues if i["status"] == "open"),
                "acknowledged": sum(1 for i in issues if i["status"] == "acknowledged"),
            },
        },
        "validation": run_meta,
        "issues": issues,
        "documents": health.get("documents_health", []),
    }