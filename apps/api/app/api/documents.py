from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import PageParams, get_current_user, get_session_factory, page_params, require_roles
from app.api.projects import get_project_or_404
from app.core.clock import utcnow
from app.db.session import get_db
from app.models.document import Discipline, Document, DocumentRevision, RevisionStatus
from app.models.project import ProjectStatus
from app.models.user import Role, User
from app.schemas.common import Page
from app.schemas.document import (
    DocumentCreate, DocumentOut, DocumentUpdate, RevisionOut, RevisionStatusUpdate,
)
from app.schemas.interop import RoundTripReportOut, SourceVerificationReportOut
from app.services import audit, extraction, revisions, storage
from app.services import interop

router = APIRouter(tags=["documents"])
can_edit = require_roles(Role.ADMIN, Role.BIM_COORDINATOR, Role.ENGINEER)
can_change_status = require_roles(Role.ADMIN, Role.BIM_COORDINATOR, Role.REVIEWER, Role.ENGINEER)


def _document_or_404(db: Session, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "Document not found. It may have been deleted.")
    return document


@router.post("/projects/{project_id}/documents", response_model=DocumentOut, status_code=201)
def create_document(
    project_id: str, body: DocumentCreate, db: Session = Depends(get_db), user: User = Depends(can_edit)
) -> Document:
    project = get_project_or_404(db, project_id)
    if project.status == ProjectStatus.ARCHIVED:
        raise HTTPException(409, f"Project '{project.name}' is archived. Restore it before adding documents.")
    data = body.model_dump(exclude={"metadata"})
    document = Document(project_id=project.id, meta=body.metadata, **data)
    document.author = document.author or user.full_name
    db.add(document)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"Document {body.document_number} already exists in this project.")
    audit.record(db, user=user, action="document.created", entity_type="document", entity_id=document.id,
                 project_id=project.id, detail={"document_number": document.document_number,
                                                "discipline": document.discipline})
    db.commit()
    return document


@router.get("/projects/{project_id}/documents", response_model=Page[DocumentOut])
def list_documents(
    project_id: str,
    discipline: Discipline | None = None,
    status_filter: RevisionStatus | None = Query(None, alias="status"),
    q: str | None = Query(None, max_length=100),
    file_type: str | None = Query(None, max_length=16),
    revision: int | None = Query(None, ge=1),
    modified_since: datetime | None = None,
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db), _user: User = Depends(get_current_user),
) -> Page[DocumentOut]:
    get_project_or_404(db, project_id)
    stmt = select(Document).where(Document.project_id == project_id)
    if discipline:
        stmt = stmt.where(Document.discipline == discipline)
    if status_filter:
        stmt = stmt.where(Document.status == status_filter)
    if file_type:
        stmt = stmt.where(Document.file_type == file_type.lower().lstrip("."))
    if revision is not None:
        stmt = stmt.where(Document.current_revision_number == revision)
    if modified_since is not None:
        stmt = stmt.where(Document.modified_at >= modified_since)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Document.document_number.ilike(like) | Document.name.ilike(like))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Document.document_number).limit(page.limit).offset(page.offset)).all()
    items = [DocumentOut.model_validate(r) for r in rows]
    return Page[DocumentOut](items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> Document:
    return _document_or_404(db, document_id)


@router.patch("/documents/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: str, body: DocumentUpdate, db: Session = Depends(get_db), user: User = Depends(can_edit)
) -> Document:
    document = _document_or_404(db, document_id)
    changes: dict = {}
    for field, value in body.model_dump(exclude_unset=True).items():
        attr = "meta" if field == "metadata" else field
        if value is None or getattr(document, attr) == value:
            continue
        changes[field] = {"old": audit.plain(getattr(document, attr)), "new": audit.plain(value)}
        setattr(document, attr, value)
    if changes:
        document.modified_at = utcnow()
        audit.record(db, user=user, action="document.updated", entity_type="document", entity_id=document.id,
                     project_id=document.project_id, detail=changes)
        db.commit()
    return document


@router.post("/documents/{document_id}/revisions", response_model=RevisionOut, status_code=201)
def upload_revision(
    document_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    change_summary: str = Form("", max_length=4000),
    status: RevisionStatus = Form(RevisionStatus.DRAFT),
    revision_number: int | None = Form(None, ge=1),
    session_factory: sessionmaker = Depends(get_session_factory),
    db: Session = Depends(get_db), user: User = Depends(can_edit),
) -> DocumentRevision:
    document = _document_or_404(db, document_id)
    if document.project.status == ProjectStatus.ARCHIVED:
        raise HTTPException(409, "This project is archived. Restore it before uploading revisions.")
    revision = revisions.create_revision(
        db, user, document, file, change_summary=change_summary, status=status, revision_number=revision_number
    )
    background_tasks.add_task(extraction.extract_revision, session_factory, revision.id)
    return revision


@router.get("/documents/{document_id}/revisions", response_model=list[RevisionOut])
def list_revisions(
    document_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> list[DocumentRevision]:
    _document_or_404(db, document_id)
    return list(db.scalars(
        select(DocumentRevision).where(DocumentRevision.document_id == document_id)
        .order_by(DocumentRevision.revision_number.desc())
    ))


def _revision_or_404(db: Session, revision_id: str) -> DocumentRevision:
    revision = db.get(DocumentRevision, revision_id)
    if revision is None:
        raise HTTPException(404, "Revision not found.")
    return revision


@router.patch("/revisions/{revision_id}/status", response_model=RevisionOut)
def update_revision_status(
    revision_id: str, body: RevisionStatusUpdate, db: Session = Depends(get_db),
    user: User = Depends(can_change_status),
) -> DocumentRevision:
    return revisions.change_status(db, user, _revision_or_404(db, revision_id), body.status)


@router.get("/revisions/{revision_id}/download")
def download_revision(
    revision_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> FileResponse:
    revision = _revision_or_404(db, revision_id)
    return FileResponse(storage.resolve_stored(revision.file_path), filename=revision.original_filename)


# ------------------------------------------------------------------ interoperability

@router.get("/revisions/{revision_id}/elements.json")
def export_revision_elements(
    revision_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> JSONResponse:
    """Download the extracted elements of this revision as bimguard.elements/1."""
    revision = _revision_or_404(db, revision_id)
    payload = interop.export_revision(db, revision)
    filename = f"elements-{revision.id}-v{revision.revision_number}.json"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/revisions/{revision_id}/verify-round-trip", response_model=RoundTripReportOut)
def verify_round_trip(
    revision_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> RoundTripReportOut:
    """Export -> re-parse through JsonProvider -> diff. Proves the canonical format is lossless."""
    revision = _revision_or_404(db, revision_id)
    report = interop.verify_round_trip(db, revision)
    return RoundTripReportOut(
        revision_id=report.revision_id,
        element_count=report.element_count,
        matches=report.matches,
        missing=report.missing,
        extra=report.extra,
        mismatches=report.mismatches,
        ok=report.ok,
    )


@router.post("/revisions/{revision_id}/verify-source", response_model=SourceVerificationReportOut)
def verify_source(
    revision_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> SourceVerificationReportOut:
    """Re-read the uploaded file with the appropriate provider and compare GUIDs with the database."""
    revision = _revision_or_404(db, revision_id)
    report = interop.verify_source(db, revision)
    return SourceVerificationReportOut(
        revision_id=report.revision_id,
        source_format=report.source_format,
        ok=report.ok,
        reason=report.reason,
        parsed_element_count=report.parsed_element_count,
        stored_element_count=report.stored_element_count,
        missing=report.missing,
        extra=report.extra,
    )

# ------------------------------------------------------------------ interoperability

@router.get("/revisions/{revision_id}/elements.json")
def export_revision_elements(
    revision_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> JSONResponse:
    """Download the extracted elements of this revision as bimguard.elements/1."""
    revision = _revision_or_404(db, revision_id)
    payload = interop.export_revision(db, revision)
    filename = f"elements-{revision.id}-v{revision.revision_number}.json"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/revisions/{revision_id}/verify-round-trip", response_model=RoundTripReportOut)
def verify_round_trip(
    revision_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> RoundTripReportOut:
    """Export -> re-parse through JsonProvider -> diff. Proves the canonical format is lossless."""
    revision = _revision_or_404(db, revision_id)
    report = interop.verify_round_trip(db, revision)
    return RoundTripReportOut(
        revision_id=report.revision_id,
        element_count=report.element_count,
        matches=report.matches,
        missing=report.missing,
        extra=report.extra,
        mismatches=report.mismatches,
        ok=report.ok,
    )


@router.post("/revisions/{revision_id}/verify-source", response_model=SourceVerificationReportOut)
def verify_source(
    revision_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> SourceVerificationReportOut:
    """Re-read the uploaded file with the appropriate provider and compare GUIDs with the database."""
    revision = _revision_or_404(db, revision_id)
    report = interop.verify_source(db, revision)
    return SourceVerificationReportOut(
        revision_id=report.revision_id,
        source_format=report.source_format,
        ok=report.ok,
        reason=report.reason,
        parsed_element_count=report.parsed_element_count,
        stored_element_count=report.stored_element_count,
        missing=report.missing,
        extra=report.extra,
    )