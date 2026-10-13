import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.projects import get_project_or_404
from app.db.session import get_db
from app.engines.graph import is_stale
from app.models.bim import BimElement
from app.models.comparison import RevisionComparison
from app.models.dependency import Dependency
from app.models.document import Document, DocumentRevision
from app.models.impact import ImpactEvent
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.models.validation import ValidationIssue, ValidationRun
from app.schemas.insights import (
    DashboardOut, DashboardProject, DocumentOverview, OverviewComparison, OverviewDocument, OverviewImpact,
    OverviewLink, ProjectHealthOut, SearchHit, SearchOut,
)
from app.services import dependencies as dependency_service
from app.services import health as health_service
from app.services import impact as impact_service

router = APIRouter(tags=["insights"])
_REVISION_QUERY = re.compile(r"^[vVrR]?(\d{1,6})$")


@router.get("/projects/{project_id}/health", response_model=ProjectHealthOut)
def project_health(project_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> dict:
    """What is the current health of this project? Computed from live data on every request."""
    return health_service.project_health(db, get_project_or_404(db, project_id))


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(include_archived: bool = False, limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db),
              _user: User = Depends(get_current_user)) -> DashboardOut:
    stmt = select(Project).order_by(Project.updated_at.desc()).limit(limit)
    if not include_archived:
        stmt = stmt.where(Project.status == ProjectStatus.ACTIVE)
    rows = [health_service.project_health(db, p) for p in db.scalars(stmt)]
    projects = [DashboardProject(**{k: r[k] for k in DashboardProject.model_fields}) for r in rows]
    totals = {
        "projects": len(rows), "documents": sum(r["documents"] for r in rows),
        "stale_dependencies": sum(r["stale_dependencies"] for r in rows),
        "open_impacts": sum(r["open_impacts"]["total"] for r in rows),
        "blocked": sum(1 for r in rows if r["validation"] and r["validation"]["status"] == "BLOCKED"),
        "ready": sum(1 for r in rows if r["validation"] and r["validation"]["status"] in ("READY", "READY_WITH_WARNINGS")),
        "not_validated": sum(1 for r in rows if r["validation"] is None),
        "critical_documents": sum(r["document_health"]["critical"] for r in rows),
    }
    return DashboardOut(totals=totals, projects=projects)


@router.get("/search", response_model=SearchOut)
def search(q: str = Query(min_length=2, max_length=100), limit: int = Query(6, ge=1, le=20),
           db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> SearchOut:
    """Finds projects, documents (by number, name, discipline, status or revision), elements of current
    revisions (by tag, name or id) and issues of each project's latest validation."""
    term = q.strip()
    like = f"%{term}%"
    names = {p.id: p.name for p in db.scalars(select(Project))}

    projects = [SearchHit(kind="project", id=p.id, title=p.name, subtitle=p.client or "No client",
                          project_id=p.id, project_name=p.name)
                for p in db.scalars(select(Project).where(or_(Project.name.ilike(like), Project.client.ilike(like)))
                                    .order_by(Project.name).limit(limit))]

    conditions = [Document.document_number.ilike(like), Document.name.ilike(like), Document.author.ilike(like),
                  cast(Document.status, String).ilike(f"%{term.replace(' ', '_')}%")]
    match = _REVISION_QUERY.match(term)
    if match:
        conditions.append(Document.current_revision_number == int(match.group(1)))
    documents = db.scalars(select(Document).where(or_(*conditions)).order_by(Document.document_number).limit(limit))
    document_hits = [SearchHit(
        kind="document", id=d.id, title=f"{d.document_number} {d.name}", document_number=d.document_number,
        subtitle=f"{d.discipline.value.title()} · {'v' + str(d.current_revision_number) if d.current_revision_number else 'no revision'} · "
                 f"{d.status.value.replace('_', ' ')} · {names[d.project_id]}", project_id=d.project_id,
        project_name=names[d.project_id]) for d in documents]
    if not document_hits and term.lower() in {"architecture", "structure", "mep", "equipment", "quantity", "general"}:
        for d in db.scalars(select(Document).where(Document.discipline == term.lower()).order_by(Document.document_number).limit(limit)):
            document_hits.append(SearchHit(kind="document", id=d.id, title=f"{d.document_number} {d.name}",
                                           document_number=d.document_number,
                                           subtitle=f"{d.discipline.value.title()} · {names[d.project_id]}",
                                           project_id=d.project_id, project_name=names[d.project_id]))

    element_rows = db.execute(
        select(BimElement, Document).join(DocumentRevision, DocumentRevision.id == BimElement.revision_id)
        .join(Document, Document.id == DocumentRevision.document_id)
        .where(DocumentRevision.revision_number == Document.current_revision_number,
               or_(BimElement.tag.ilike(like), BimElement.name.ilike(like), BimElement.guid.ilike(like)))
        .order_by(BimElement.tag).limit(limit)).all()
    elements = [SearchHit(
        kind="element", id=e.id, title=f"{e.tag or e.guid} {e.name}".strip(), document_number=d.document_number,
        subtitle=f"{e.ifc_class.replace('Ifc', '')} · in {d.document_number} v{d.current_revision_number} · {names[d.project_id]}",
        project_id=d.project_id, project_name=names[d.project_id]) for e, d in element_rows]

    latest = (select(ValidationRun.project_id, func.max(ValidationRun.created_at).label("latest"))
              .group_by(ValidationRun.project_id).subquery())
    run_ids = select(ValidationRun.id).join(latest, (ValidationRun.project_id == latest.c.project_id)
                                            & (ValidationRun.created_at == latest.c.latest))
    issues = [SearchHit(
        kind="issue", id=i.id, title=f"{i.document_number + ': ' if i.document_number else ''}{i.title}", document_number=i.document_number,
        subtitle=f"{i.severity.title()} · {i.rule_id.replace('_', ' ').title()} · {names.get(i.project_id, '')}",
        project_id=i.project_id, project_name=names.get(i.project_id, ""))
        for i in db.scalars(select(ValidationIssue).where(
            ValidationIssue.run_id.in_(run_ids), or_(ValidationIssue.title.ilike(like), ValidationIssue.message.ilike(like),
                                                      ValidationIssue.rule_id.ilike(f"%{term.replace(' ', '_')}%")))
            .order_by(ValidationIssue.severity, ValidationIssue.document_number).limit(limit))]
    return SearchOut(query=term, projects=projects, documents=document_hits, elements=elements, issues=issues)


@router.get("/documents/{document_id}/overview", response_model=DocumentOverview)
def document_overview(document_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> DocumentOverview:
    """Everything a person wants to know about one document at a glance (used by the graph's side panel)."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "Document not found. It may have been deleted.")
    graph, documents, dependencies = dependency_service.load_graph(db, document.project_id)
    health = health_service.document_health(db, document.project_id)[document.id]

    providers, dependents = [], []
    for dep in dependencies:
        edge = dependency_service.to_edge(dep)
        if document.id not in (edge.source, edge.target):
            continue
        other_id = edge.target if edge.source == document.id else edge.source
        other = documents[other_id]
        provider = documents.get(edge.provider) if edge.provider else None
        link = OverviewLink(
            document_id=other.id, document_number=other.document_number, relationship_type=dep.relationship_type,
            current_revision=other.current_revision_number, validated_against_revision=dep.validated_against_revision,
            stale=bool(provider and edge.consumer == document.id and is_stale(edge, provider.current_revision_number)))
        if edge.provider is None:
            providers.append(link)
            dependents.append(link)
        elif edge.consumer == document.id:
            providers.append(link)
        else:
            dependents.append(link)

    downstream = graph.impact_from(document.id)
    comparison = db.scalar(select(RevisionComparison).join(DocumentRevision, DocumentRevision.id == RevisionComparison.to_revision_id)
                           .where(RevisionComparison.document_id == document.id)
                           .order_by(DocumentRevision.revision_number.desc(), RevisionComparison.created_at.desc()).limit(1))
    latest_comparison = None
    if comparison is not None:
        old, new = db.get(DocumentRevision, comparison.from_revision_id), db.get(DocumentRevision, comparison.to_revision_id)
        latest_comparison = OverviewComparison(
            id=comparison.id, revision_id=new.id, from_revision_number=old.revision_number, to_revision_number=new.revision_number,
            total_changes=comparison.total_changes, by_severity=comparison.counts.get("by_severity", {}),
            by_type=comparison.counts.get("by_type", {}))

    analyses = {a.id: a for a in impact_service.latest_analyses(db, document.project_id)}
    by_dependency = {d.id: d for d in dependencies}
    open_impacts = []
    for event in db.scalars(select(ImpactEvent).where(ImpactEvent.analysis_id.in_(list(analyses) or [""]),
                                                      ImpactEvent.impacted_document_id == document.id)):
        analysis = analyses[event.analysis_id]
        if impact_service.event_state(event, analysis.changed_revision_number, by_dependency) == "open":
            open_impacts.append(OverviewImpact(
                changed_document_number=documents[event.changed_document_id].document_number,
                changed_revision_number=analysis.changed_revision_number, score=event.score, severity=event.severity,
                direct=event.direct))
    open_impacts.sort(key=lambda i: -i.score)
    return DocumentOverview(
        document=OverviewDocument(
            id=document.id, project_id=document.project_id, document_number=document.document_number, name=document.name,
            discipline=document.discipline.value, status=document.status.value,
            current_revision_number=document.current_revision_number, author=document.author,
            file_type=document.file_type, modified_at=document.modified_at),
        health_state=health.state, health_reasons=health.reasons, providers=providers, dependents=dependents,
        downstream_count=len(downstream), radius=max((i.distance for i in downstream), default=0),
        latest_comparison=latest_comparison, open_impacts=open_impacts)
