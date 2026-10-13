"""Project and document health, derived on read from dependencies, impacts, statuses and the latest validation.
Nothing here is stored, so it can never disagree with the data it summarises."""
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines.graph import is_stale
from app.models.audit import AuditLog
from app.models.dependency import Dependency
from app.models.document import Document, DocumentRevision
from app.models.impact import ImpactEvent
from app.models.project import Project
from app.models.validation import Rule, ValidationRun
from app.services import dependencies as dependency_service
from app.services import impact as impact_service

_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
_APPROVED = {"approved", "issued"}


def aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


@dataclass
class DocHealth:
    state: str = "healthy"
    reasons: list[str] = field(default_factory=list)


def document_health(db: Session, project_id: str) -> dict[str, DocHealth]:
    """healthy, warning, stale or critical for every document of a project.

    stale: it depends on a document that has moved on since it was reviewed.
    critical: stale or directly hit by a significant (High or Critical) change nobody has reviewed yet.
    warning: an open impact, a revision that is not approved, or no revision at all."""
    _, documents, dependencies = dependency_service.load_graph(db, project_id)
    result = {d.id: DocHealth() for d in documents.values()}
    stale: dict[str, list[str]] = {}
    for dep in dependencies:
        edge = dependency_service.to_edge(dep)
        provider = documents.get(edge.provider) if edge.provider else None
        if provider is not None and is_stale(edge, provider.current_revision_number):
            seen = f"v{dep.validated_against_revision}" if dep.validated_against_revision else "no revision"
            stale.setdefault(edge.consumer, []).append(
                f"Depends on {provider.document_number}, now v{provider.current_revision_number} (reviewed against {seen})")

    analyses = {a.id: a for a in impact_service.latest_analyses(db, project_id)}
    by_dependency = {d.id: d for d in dependencies}
    open_impacts: dict[str, list[tuple[str, str]]] = {}
    for event in db.scalars(select(ImpactEvent).where(ImpactEvent.analysis_id.in_(list(analyses) or [""]))):
        analysis = analyses[event.analysis_id]
        if impact_service.event_state(event, analysis.changed_revision_number, by_dependency) == "open":
            changed = documents[event.changed_document_id]
            open_impacts.setdefault(event.impacted_document_id, []).append((
                event.severity, f"Open impact from {changed.document_number} v{analysis.changed_revision_number}: "
                                f"{event.severity.lower()} ({event.score:.1f})"))

    for doc_id, document in documents.items():
        health = result[doc_id]
        impacts = open_impacts.get(doc_id, [])
        worst = max((_RANK[s] for s, _ in impacts), default=-1)
        health.reasons = list(stale.get(doc_id, [])) + [text for _, text in sorted(impacts, key=lambda t: -_RANK[t[0]])]
        if document.current_revision_number is None:
            health.reasons.append("No revision uploaded")
        elif document.status.value not in _APPROVED:
            health.reasons.append(f"Current revision v{document.current_revision_number} is {document.status.value.replace('_', ' ')}")
        if worst == _RANK["CRITICAL"] or (doc_id in stale and worst >= _RANK["HIGH"]):
            health.state = "critical"
        elif doc_id in stale:
            health.state = "stale"
        elif health.reasons:
            health.state = "warning"
    return result


_ACTIVITY = {
    "revision.created": lambda d: f"{d.get('document_number')} v{d.get('revision')} uploaded",
    "revision.compared": lambda d: f"{d.get('document_number')} v{d.get('to')}: {d.get('changes')} changes detected since v{d.get('from')}",
    "impact.analyzed": lambda d: f"{d.get('document_number')} v{d.get('revision')}: impact reaches {d.get('total')} documents",
    "revision.status_changed": lambda d: f"{d.get('document_number')} v{d.get('revision')}: {str(d.get('old')).replace('_', ' ')} to {str(d.get('new')).replace('_', ' ')}",
    "dependency.validated": lambda d: f"Dependency on {d.get('provider')} reviewed against v{d.get('new_revision')}",
    "dependency.created": lambda d: f"Dependency added: {d.get('source')} and {d.get('target')} ({str(d.get('type')).replace('_', ' ')})",
    "dependency.deleted": lambda d: f"Dependency removed: {d.get('source')} and {d.get('target')}",
    "validation.run": lambda d: f"Validation: {str(d.get('status')).replace('_', ' ').lower()} ({d.get('open')} open issues)",
    "issue.acknowledged": lambda d: f"Issue acknowledged on {d.get('document') or 'project'} ({d.get('rule')})",
}


def recent_activity(db: Session, project_id: str, limit: int = 10) -> list[dict]:
    rows = db.scalars(select(AuditLog).where(AuditLog.project_id == project_id, AuditLog.action.in_(list(_ACTIVITY)))
                      .order_by(AuditLog.id.desc()).limit(limit))
    return [{"at": r.created_at, "user": r.user_email, "action": r.action, "text": _ACTIVITY[r.action](r.detail or {})}
            for r in rows]


def last_change_at(db: Session, project_id: str) -> datetime | None:
    """When the data a validation looks at last changed: documents, revisions, dependencies or rules."""
    candidates = [
        db.scalar(select(func.max(Document.modified_at)).where(Document.project_id == project_id)),
        db.scalar(select(func.max(DocumentRevision.uploaded_at)).join(Document).where(Document.project_id == project_id)),
        db.scalar(select(func.max(Dependency.created_at)).where(Dependency.project_id == project_id)),
        db.scalar(select(func.max(Dependency.validated_at)).where(Dependency.project_id == project_id)),
        db.scalar(select(func.max(Rule.updated_at))),
    ]
    values = [aware(c) for c in candidates if c is not None]
    return max(values) if values else None


def project_health(db: Session, project: Project) -> dict:
    graph_docs = db.scalars(select(Document).where(Document.project_id == project.id).order_by(Document.document_number)).all()
    health = document_health(db, project.id)
    _, documents, dependencies = dependency_service.load_graph(db, project.id)
    stale_count = 0
    for dep in dependencies:
        edge = dependency_service.to_edge(dep)
        provider = documents.get(edge.provider) if edge.provider else None
        stale_count += bool(provider and is_stale(edge, provider.current_revision_number))

    open_by_severity: dict[str, int] = {}
    open_total = 0
    analyses = {a.id: a for a in impact_service.latest_analyses(db, project.id)}
    by_dependency = {d.id: d for d in dependencies}
    for event in db.scalars(select(ImpactEvent).where(ImpactEvent.analysis_id.in_(list(analyses) or [""]))):
        if impact_service.event_state(event, analyses[event.analysis_id].changed_revision_number, by_dependency) == "open":
            open_total += 1
            open_by_severity[event.severity] = open_by_severity.get(event.severity, 0) + 1

    run = db.scalar(select(ValidationRun).where(ValidationRun.project_id == project.id)
                    .order_by(ValidationRun.created_at.desc(), ValidationRun.id).limit(1))
    changed_at = last_change_at(db, project.id)
    validation = None
    if run is not None:
        summary = run.summary or {}
        validation = {
            "run_id": run.id, "status": run.status, "created_at": run.created_at, "open": summary.get("open", 0),
            "blocking": summary.get("blocking", 0), "acknowledged": summary.get("acknowledged", 0),
            "open_by_severity": summary.get("open_by_severity", {}),
            "outdated": bool(changed_at and changed_at > aware(run.created_at))}
    disciplines: dict[str, int] = {}
    for d in graph_docs:
        disciplines[d.discipline.value] = disciplines.get(d.discipline.value, 0) + 1
    counts = {s: 0 for s in ("critical", "stale", "warning", "healthy")}
    for h in health.values():
        counts[h.state] += 1
    return {
        "project_id": project.id, "project_name": project.name, "project_status": project.status.value,
        "client": project.client, "documents": len(graph_docs),
        "documents_with_revision": sum(d.current_revision_number is not None for d in graph_docs),
        "disciplines": disciplines, "dependencies": len(dependencies), "stale_dependencies": stale_count,
        "open_impacts": {"total": open_total, "by_severity": open_by_severity},
        "document_health": counts,
        "documents_health": [{"document_id": d.id, "document_number": d.document_number, "name": d.name,
                              "state": health[d.id].state, "reasons": health[d.id].reasons} for d in graph_docs],
        "validation": validation, "recent_activity": recent_activity(db, project.id),
        "last_change_at": changed_at,
    }
