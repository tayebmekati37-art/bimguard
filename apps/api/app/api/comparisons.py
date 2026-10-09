from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import PageParams, get_current_user, page_params, require_roles
from app.db.session import get_db
from app.models.bim import BimElement
from app.models.comparison import DetectedChange, RevisionComparison
from app.models.document import DocumentRevision
from app.models.user import Role, User
from app.schemas.common import Page
from app.schemas.comparison import ChangeOut, CompareRequest, ComparisonOut, PlanElement, PlanOut
from app.services import comparison as service

router = APIRouter(tags=["comparison"])
can_compare = require_roles(Role.ADMIN, Role.BIM_COORDINATOR, Role.ENGINEER, Role.REVIEWER)
PLAN_CONTEXT_LIMIT = 300
_SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _revision_or_404(db: Session, revision_id: str) -> DocumentRevision:
    revision = db.get(DocumentRevision, revision_id)
    if revision is None:
        raise HTTPException(404, "Revision not found.")
    return revision


def _comparison_or_404(db: Session, comparison_id: str) -> RevisionComparison:
    comparison = db.get(RevisionComparison, comparison_id)
    if comparison is None:
        raise HTTPException(404, "Comparison not found. Run the comparison again.")
    return comparison


def _out(db: Session, comparison: RevisionComparison) -> ComparisonOut:
    old, new = db.get(DocumentRevision, comparison.from_revision_id), db.get(DocumentRevision, comparison.to_revision_id)
    return ComparisonOut(
        id=comparison.id, project_id=new.document.project_id, document_id=comparison.document_id,
        document_number=new.document.document_number, from_revision_id=old.id, to_revision_id=new.id,
        from_revision_number=old.revision_number, to_revision_number=new.revision_number,
        created_at=comparison.created_at, created_by_name=comparison.created_by_name,
        total_changes=comparison.total_changes, counts=comparison.counts, config=comparison.config)


@router.post("/revisions/{revision_id}/compare", response_model=ComparisonOut, status_code=201)
def run_comparison(
    revision_id: str, body: CompareRequest | None = None,
    db: Session = Depends(get_db), user: User = Depends(can_compare),
) -> ComparisonOut:
    new = _revision_or_404(db, revision_id)
    old_id = body.against_revision_id if body and body.against_revision_id else new.previous_revision_id
    if old_id is None:
        raise HTTPException(409, f"{new.document.document_number} v{new.revision_number} has no earlier revision "
                                 "to compare against.")
    old = _revision_or_404(db, old_id)
    try:
        comparison = service.compare_revisions(db, old, new, user)
    except service.ComparisonError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _out(db, comparison)


@router.get("/revisions/{revision_id}/comparison", response_model=ComparisonOut)
def get_revision_comparison(
    revision_id: str, against: str | None = None,
    db: Session = Depends(get_db), _user: User = Depends(get_current_user),
) -> ComparisonOut:
    revision = _revision_or_404(db, revision_id)
    stmt = select(RevisionComparison).where(RevisionComparison.to_revision_id == revision_id)
    if against:
        stmt = stmt.where(RevisionComparison.from_revision_id == against)
    elif revision.previous_revision_id:
        preferred = db.scalar(stmt.where(RevisionComparison.from_revision_id == revision.previous_revision_id))
        if preferred:
            return _out(db, preferred)
    comparison = db.scalar(stmt.order_by(RevisionComparison.created_at.desc()).limit(1))
    if comparison is None:
        raise HTTPException(404, "No comparison has been run for this revision yet.")
    return _out(db, comparison)


@router.get("/comparisons/{comparison_id}", response_model=ComparisonOut)
def get_comparison(comparison_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return _out(db, _comparison_or_404(db, comparison_id))


@router.get("/comparisons/{comparison_id}/changes", response_model=Page[ChangeOut])
def list_changes(
    comparison_id: str,
    change_type: str | None = Query(None, max_length=32),
    severity: str | None = Query(None, max_length=16),
    q: str | None = Query(None, max_length=100),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db), _user: User = Depends(get_current_user),
) -> Page[ChangeOut]:
    _comparison_or_404(db, comparison_id)
    stmt = select(DetectedChange).where(DetectedChange.comparison_id == comparison_id)
    if change_type:
        stmt = stmt.where(DetectedChange.change_type == change_type.upper())
    if severity:
        stmt = stmt.where(DetectedChange.severity == severity.upper())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(DetectedChange.element_tag.ilike(like) | DetectedChange.element_name.ilike(like)
                          | DetectedChange.field.ilike(like) | DetectedChange.summary.ilike(like))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rank = case(_SEVERITY_RANK, value=DetectedChange.severity, else_=4)
    rows = db.scalars(stmt.order_by(rank, DetectedChange.element_tag, DetectedChange.field, DetectedChange.id)
                      .limit(page.limit).offset(page.offset)).all()
    return Page[ChangeOut](items=[ChangeOut.model_validate(r) for r in rows], total=total,
                           limit=page.limit, offset=page.offset)


@router.get("/comparisons/{comparison_id}/footprints", response_model=PlanOut)
def plan_data(comparison_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> PlanOut:
    """Geometry of changed elements (old and new) plus unchanged elements as context, for the 2D plan view."""
    comparison = _comparison_or_404(db, comparison_id)
    rows = db.scalars(select(DetectedChange).where(
        DetectedChange.comparison_id == comparison_id, DetectedChange.element_guid.is_not(None))).all()

    grouped: dict[str, dict] = {}
    for row in rows:
        entry = grouped.setdefault(row.element_guid, {"types": set(), "old_guid": row.element_guid, "row": row})
        entry["types"].add(row.change_type)
        entry["old_guid"] = row.detail.get("old_guid", entry["old_guid"])

    def geometry(revision_id: str, guid: str) -> dict | None:
        element = db.scalar(select(BimElement).where(BimElement.revision_id == revision_id,
                                                     BimElement.guid == guid))
        return element.geometry if element else None

    changed: list[PlanElement] = []
    for guid, entry in sorted(grouped.items(), key=lambda kv: (kv[1]["row"].element_tag, kv[0])):
        types, row = entry["types"], entry["row"]
        status = "added" if "ELEMENT_ADDED" in types else "removed" if "ELEMENT_REMOVED" in types else "modified"
        changed.append(PlanElement(
            guid=guid, tag=row.element_tag, name=row.element_name, ifc_class=row.ifc_class, status=status,
            change_types=sorted(types),
            old=None if status == "added" else geometry(comparison.from_revision_id, entry["old_guid"]),
            new=None if status == "removed" else geometry(comparison.to_revision_id, guid)))

    context_rows = db.scalars(
        select(BimElement).where(BimElement.revision_id == comparison.to_revision_id,
                                 BimElement.guid.not_in(list(grouped) or [""]))
        .order_by(BimElement.ifc_class, BimElement.tag).limit(PLAN_CONTEXT_LIMIT)).all()
    context = [PlanElement(guid=e.guid, tag=e.tag, name=e.name, ifc_class=e.ifc_class, status="unchanged",
                           change_types=[], old=None, new=e.geometry) for e in context_rows]
    return PlanOut(changed=changed, context=context)
