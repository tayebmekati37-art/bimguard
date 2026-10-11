from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import PageParams, get_current_user, page_params, require_roles
from app.api.projects import get_project_or_404
from app.db.session import get_db
from app.models.dependency import Dependency
from app.models.document import Document
from app.models.impact import ImpactEvent
from app.models.user import Role, User
from app.schemas.common import Page
from app.schemas.impact import AnalysisOut, ImpactCounts, ImpactEventOut, ProjectImpactOut
from app.services import impact as service

router = APIRouter(tags=["impact"])
can_run = require_roles(Role.ADMIN, Role.BIM_COORDINATOR, Role.ENGINEER, Role.REVIEWER)


def _build(db: Session, project_id: str, severity: str | None, state: str | None, document_id: str | None,
           page: PageParams) -> ProjectImpactOut:
    analyses = service.latest_analyses(db, project_id)
    documents = {d.id: d for d in db.scalars(select(Document).where(Document.project_id == project_id))}
    dependencies: dict[str, Dependency] = {d.id: d for d in db.scalars(
        select(Dependency).where(Dependency.project_id == project_id))}
    by_analysis = {a.id: a for a in analyses}
    events = list(db.scalars(select(ImpactEvent).where(ImpactEvent.analysis_id.in_(list(by_analysis) or [""]))))

    rows: list[ImpactEventOut] = []
    for event in events:
        analysis = by_analysis[event.analysis_id]
        current = service.event_state(event, analysis.changed_revision_number, dependencies)
        edge = service.first_hop_dependency(event, dependencies)
        target, source = documents[event.impacted_document_id], documents[event.changed_document_id]
        rows.append(ImpactEventOut(
            id=event.id, analysis_id=event.analysis_id, changed_document_id=source.id,
            changed_document_number=source.document_number, changed_revision_number=analysis.changed_revision_number,
            impacted_document_id=target.id, impacted_document_number=target.document_number,
            impacted_name=target.name, impacted_discipline=target.discipline.value, impacted_status=target.status.value,
            distance=event.distance, direct=event.direct, score=event.score, severity=event.severity,
            confidence=event.confidence, state=current, reason=event.reason, formula=event.formula,
            factors=event.factors, path=event.path, affected_elements=event.affected_elements,
            affected_element_count=event.affected_element_count, note=event.note, first_edge_id=event.first_edge_id,
            dependency_validated_against=edge.validated_against_revision if edge else None,
            validated_by_name=edge.validated_by_name if edge else "", validated_at=edge.validated_at if edge else None,
            created_at=event.created_at))

    counts = ImpactCounts(
        total=len(rows), open=sum(r.state == "open" for r in rows), reviewed=sum(r.state == "reviewed" for r in rows),
        advisory=sum(r.state == "advisory" for r in rows),
        open_by_severity={s: n for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
                          if (n := sum(r.state == "open" and r.severity == s for r in rows))})
    if severity:
        rows = [r for r in rows if r.severity == severity.upper()]
    if state:
        rows = [r for r in rows if r.state == state]
    if document_id:
        rows = [r for r in rows if document_id in (r.impacted_document_id, r.changed_document_id)]
    rows.sort(key=lambda r: (-r.score, r.distance, r.impacted_document_number))
    return ProjectImpactOut(
        analyses=[AnalysisOut(id=a.id, changed_document_id=a.changed_document_id,
                              changed_document_number=documents[a.changed_document_id].document_number,
                              changed_revision_number=a.changed_revision_number, created_at=a.created_at,
                              summary=a.summary, config=a.config) for a in analyses],
        counts=counts,
        events=Page[ImpactEventOut](items=rows[page.offset:page.offset + page.limit], total=len(rows),
                                    limit=page.limit, offset=page.offset))


@router.get("/projects/{project_id}/impact-analysis", response_model=ProjectImpactOut)
def get_impact_analysis(
    project_id: str,
    severity: str | None = Query(None, pattern="^(?i)(low|medium|high|critical)$"),
    state: str | None = Query(None, pattern="^(open|reviewed|advisory)$"),
    document_id: str | None = None,
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db), _user: User = Depends(get_current_user),
) -> ProjectImpactOut:
    """The latest impact of each changed document on the rest of the project, strongest first."""
    get_project_or_404(db, project_id)
    return _build(db, project_id, severity, state, document_id, page)


@router.post("/projects/{project_id}/impact-analysis", response_model=ProjectImpactOut)
def run_impact_analysis(project_id: str, db: Session = Depends(get_db), user: User = Depends(can_run)) -> ProjectImpactOut:
    """Recomputes the analysis from each document's latest comparison and the current dependency graph."""
    get_project_or_404(db, project_id)
    service.reanalyze_project(db, project_id, user)
    return _build(db, project_id, None, None, None, PageParams(limit=50, offset=0))


@router.get("/impact-events/{event_id}", response_model=ImpactEventOut)
def get_impact_event(event_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    event = db.get(ImpactEvent, event_id)
    if event is None:
        raise HTTPException(404, "Impact event not found. The analysis may have been refreshed.")
    result = _build(db, event.project_id, None, None, None, PageParams(limit=200, offset=0))
    found = next((e for e in result.events.items if e.id == event_id), None)
    if found is None:
        raise HTTPException(404, "Impact event not found. It belongs to a superseded analysis.")
    return found

