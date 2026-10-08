from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import PageParams, get_current_user, get_session_factory, page_params
from app.api.documents import can_edit
from app.db.session import get_db
from app.models.bim import BimElement
from app.models.document import DocumentRevision, ExtractionStatus
from app.models.user import User
from app.schemas.bim import CountItem, ElementOut, ModelSummary
from app.schemas.common import Page
from app.schemas.document import RevisionOut
from app.services import extraction

router = APIRouter(tags=["bim"])


def _revision_or_404(db: Session, revision_id: str) -> DocumentRevision:
    revision = db.get(DocumentRevision, revision_id)
    if revision is None:
        raise HTTPException(404, "Revision not found.")
    return revision


@router.get("/revisions/{revision_id}/elements", response_model=Page[ElementOut])
def list_elements(
    revision_id: str,
    ifc_class: str | None = Query(None, max_length=64),
    level: str | None = Query(None, max_length=64),
    room: str | None = Query(None, max_length=64),
    q: str | None = Query(None, max_length=100),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db), _user: User = Depends(get_current_user),
) -> Page[ElementOut]:
    _revision_or_404(db, revision_id)
    stmt = select(BimElement).where(BimElement.revision_id == revision_id)
    if ifc_class:
        stmt = stmt.where(BimElement.ifc_class == ifc_class)
    if level:
        stmt = stmt.where(BimElement.level == level)
    if room:
        stmt = stmt.where(BimElement.room == room)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(BimElement.name.ilike(like) | BimElement.tag.ilike(like) | BimElement.guid.ilike(like))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(BimElement.ifc_class, BimElement.tag, BimElement.name).limit(page.limit).offset(page.offset)
    ).all()
    return Page[ElementOut](items=[ElementOut.model_validate(r) for r in rows], total=total,
                            limit=page.limit, offset=page.offset)


@router.get("/revisions/{revision_id}/elements/{guid}", response_model=ElementOut)
def get_element(
    revision_id: str, guid: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> BimElement:
    _revision_or_404(db, revision_id)
    element = db.scalar(select(BimElement).where(BimElement.revision_id == revision_id, BimElement.guid == guid))
    if element is None:
        raise HTTPException(404, f"Element {guid} is not part of this revision.")
    return element


@router.get("/revisions/{revision_id}/summary", response_model=ModelSummary)
def model_summary(
    revision_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> ModelSummary:
    _revision_or_404(db, revision_id)

    def grouped(column) -> list[CountItem]:
        rows = db.execute(
            select(column, func.count()).where(BimElement.revision_id == revision_id)
            .group_by(column).order_by(column)
        ).all()
        return [CountItem(key=key if key is not None else "(none)", count=n) for key, n in rows]

    by_class = grouped(BimElement.ifc_class)
    return ModelSummary(total=sum(i.count for i in by_class), by_class=by_class, by_level=grouped(BimElement.level))


@router.post("/revisions/{revision_id}/extract", response_model=RevisionOut, status_code=202)
def reextract(
    revision_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
    session_factory: sessionmaker = Depends(get_session_factory), _user: User = Depends(can_edit),
) -> DocumentRevision:
    revision = _revision_or_404(db, revision_id)
    revision.extraction_status = ExtractionStatus.PENDING.value
    revision.extraction_message = ""
    db.commit()
    background_tasks.add_task(extraction.extract_revision, session_factory, revision.id)
    return revision
