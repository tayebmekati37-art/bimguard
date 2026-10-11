from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import PageParams, get_current_user, page_params, require_roles
from app.api.projects import get_project_or_404
from app.db.session import get_db
from app.engines.validation import BY_ID
from app.models.user import Role, User
from app.models.validation import ValidationIssue, ValidationRun
from app.schemas.common import Page
from app.schemas.validation import AcknowledgeRequest, IssueOut, RunOut
from app.services import validation as service

router = APIRouter(tags=["validation"])
can_validate = require_roles(Role.ADMIN, Role.BIM_COORDINATOR, Role.ENGINEER, Role.REVIEWER)
can_acknowledge = require_roles(Role.ADMIN, Role.BIM_COORDINATOR, Role.REVIEWER)
_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _run_or_404(db: Session, run_id: str) -> ValidationRun:
    run = db.get(ValidationRun, run_id)
    if run is None:
        raise HTTPException(404, "Validation run not found.")
    return run


def _issue_or_404(db: Session, issue_id: str) -> ValidationIssue:
    issue = db.get(ValidationIssue, issue_id)
    if issue is None:
        raise HTTPException(404, "Issue not found. It belongs to a validation run that no longer exists.")
    return issue


def _issue_out(issue: ValidationIssue) -> IssueOut:
    definition = BY_ID.get(issue.rule_id)
    return IssueOut(
        id=issue.id, run_id=issue.run_id, rule_id=issue.rule_id, rule_name=definition.name if definition else issue.rule_id,
        category=definition.category if definition else "", severity=issue.severity, document_id=issue.document_id,
        document_number=issue.document_number, element_tag=issue.element_tag, title=issue.title, message=issue.message,
        recommended_action=issue.recommended_action, details=issue.details or {}, status=issue.status,
        acknowledged_by_name=issue.acknowledged_by_name, acknowledged_at=issue.acknowledged_at,
        acknowledgement_note=issue.acknowledgement_note)


@router.post("/projects/{project_id}/validate", response_model=RunOut, status_code=201)
def validate_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(can_validate)) -> ValidationRun:
    """Runs every enabled rule against the project and decides whether it is ready for issue."""
    get_project_or_404(db, project_id)
    return service.run_validation(db, project_id, user)


@router.get("/projects/{project_id}/validation-runs", response_model=Page[RunOut])
def list_runs(project_id: str, page: PageParams = Depends(page_params), db: Session = Depends(get_db),
              _user: User = Depends(get_current_user)) -> Page[RunOut]:
    get_project_or_404(db, project_id)
    stmt = select(ValidationRun).where(ValidationRun.project_id == project_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(ValidationRun.created_at.desc(), ValidationRun.id).limit(page.limit).offset(page.offset)).all()
    return Page[RunOut](items=[RunOut.model_validate(r) for r in rows], total=total, limit=page.limit, offset=page.offset)


@router.get("/projects/{project_id}/validation-runs/latest", response_model=RunOut)
def latest_run(project_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> ValidationRun:
    get_project_or_404(db, project_id)
    run = db.scalar(select(ValidationRun).where(ValidationRun.project_id == project_id)
                    .order_by(ValidationRun.created_at.desc(), ValidationRun.id).limit(1))
    if run is None:
        raise HTTPException(404, "This project has not been validated yet.")
    return run


@router.get("/validation-runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> ValidationRun:
    return _run_or_404(db, run_id)


@router.get("/validation-runs/{run_id}/issues", response_model=Page[IssueOut])
def list_issues(
    run_id: str,
    severity: str | None = Query(None, pattern="^(?i)(low|medium|high|critical)$"),
    status: str | None = Query(None, pattern="^(open|acknowledged)$"),
    rule_id: str | None = Query(None, max_length=64),
    document_id: str | None = None,
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db), _user: User = Depends(get_current_user),
) -> Page[IssueOut]:
    _run_or_404(db, run_id)
    stmt = select(ValidationIssue).where(ValidationIssue.run_id == run_id)
    if severity:
        stmt = stmt.where(ValidationIssue.severity == severity.upper())
    if status:
        stmt = stmt.where(ValidationIssue.status == status)
    if rule_id:
        stmt = stmt.where(ValidationIssue.rule_id == rule_id)
    if document_id:
        stmt = stmt.where(ValidationIssue.document_id == document_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rank = case(_RANK, value=ValidationIssue.severity, else_=4)
    rows = db.scalars(stmt.order_by(rank, ValidationIssue.document_number, ValidationIssue.rule_id,
                                    ValidationIssue.element_tag, ValidationIssue.id).limit(page.limit).offset(page.offset)).all()
    return Page[IssueOut](items=[_issue_out(i) for i in rows], total=total, limit=page.limit, offset=page.offset)


@router.post("/issues/{issue_id}/acknowledge", response_model=IssueOut)
def acknowledge_issue(issue_id: str, body: AcknowledgeRequest, db: Session = Depends(get_db),
                      user: User = Depends(can_acknowledge)) -> IssueOut:
    """Accepts the risk of an issue, with a written reason. Critical issues cannot be acknowledged."""
    return _issue_out(service.acknowledge(db, _issue_or_404(db, issue_id), user, body.note.strip()))


@router.delete("/issues/{issue_id}/acknowledge", response_model=IssueOut)
def revoke_acknowledgement(issue_id: str, db: Session = Depends(get_db), user: User = Depends(can_acknowledge)) -> IssueOut:
    return _issue_out(service.revoke(db, _issue_or_404(db, issue_id), user))
