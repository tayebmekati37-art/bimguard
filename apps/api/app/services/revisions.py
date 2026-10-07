from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models.document import Document, DocumentRevision, RevisionStatus
from app.models.user import Role, User
from app.services import audit, storage

ALLOWED_TRANSITIONS: dict[RevisionStatus, set[RevisionStatus]] = {
    RevisionStatus.DRAFT: {RevisionStatus.IN_REVIEW},
    RevisionStatus.IN_REVIEW: {RevisionStatus.APPROVED, RevisionStatus.REJECTED, RevisionStatus.DRAFT},
    RevisionStatus.APPROVED: {RevisionStatus.ISSUED, RevisionStatus.IN_REVIEW},
    RevisionStatus.ISSUED: set(),
    RevisionStatus.REJECTED: {RevisionStatus.DRAFT},
    RevisionStatus.SUPERSEDED: set(),
}


def create_revision(
    db: Session, user: User, document: Document, upload: UploadFile, *,
    change_summary: str, status: RevisionStatus, revision_number: int | None,
) -> DocumentRevision:
    current = document.current_revision_number
    number = revision_number if revision_number is not None else (current or 0) + 1
    if current is not None and number <= current:
        raise HTTPException(
            409,
            f"Revision v{number} is not newer than the current revision v{current} of {document.document_number}. "
            "Revision numbers must increase.",
        )

    stored = storage.save_upload(upload, document.project_id, document.id)

    duplicate = db.scalar(
        select(DocumentRevision).where(
            DocumentRevision.document_id == document.id, DocumentRevision.checksum == stored.checksum
        )
    )
    if duplicate is not None:
        storage.delete_stored(stored.relative_path)
        raise HTTPException(
            409,
            f"This file is identical to revision v{duplicate.revision_number} of {document.document_number} "
            "(same SHA-256 checksum). Nothing was uploaded.",
        )

    previous = db.scalar(
        select(DocumentRevision).where(DocumentRevision.document_id == document.id)
        .order_by(DocumentRevision.revision_number.desc()).limit(1)
    )
    revision = DocumentRevision(
        document_id=document.id, revision_number=number, file_path=stored.relative_path,
        original_filename=stored.original_name, file_size=stored.size, checksum=stored.checksum,
        created_by_id=user.id, created_by_name=user.full_name, status=status,
        change_summary=change_summary.strip(), previous_revision_id=previous.id if previous else None,
    )
    db.add(revision)
    if previous is not None and previous.status != RevisionStatus.REJECTED:
        previous.status = RevisionStatus.SUPERSEDED

    document.current_revision_number = number
    document.checksum = stored.checksum
    document.file_type = stored.extension.lstrip(".")
    document.status = status
    document.modified_at = utcnow()
    if status == RevisionStatus.ISSUED:
        document.issue_date = utcnow()

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        storage.delete_stored(stored.relative_path)
        raise HTTPException(409, f"Revision v{number} of {document.document_number} already exists.")

    audit.record(
        db, user=user, action="revision.created", entity_type="revision", entity_id=revision.id,
        project_id=document.project_id,
        detail={"document_number": document.document_number, "revision": number,
                "checksum": stored.checksum, "filename": stored.original_name},
    )
    db.commit()
    return revision


def change_status(db: Session, user: User, revision: DocumentRevision, new_status: RevisionStatus) -> DocumentRevision:
    document = revision.document
    if revision.revision_number != document.current_revision_number:
        raise HTTPException(409, f"Only the current revision (v{document.current_revision_number}) can change status.")
    if new_status not in ALLOWED_TRANSITIONS[revision.status]:
        raise HTTPException(
            409, f"A {revision.status.value.replace('_', ' ')} revision cannot move to "
                 f"{new_status.value.replace('_', ' ')}.",
        )
    if user.role == Role.ENGINEER and new_status != RevisionStatus.IN_REVIEW:
        raise HTTPException(403, "Engineers can submit a revision for review. Approval is done by a reviewer.")

    old = revision.status
    revision.status = new_status
    document.status = new_status
    document.modified_at = utcnow()
    if new_status == RevisionStatus.ISSUED:
        document.issue_date = utcnow()
    audit.record(
        db, user=user, action="revision.status_changed", entity_type="revision", entity_id=revision.id,
        project_id=document.project_id,
        detail={"document_number": document.document_number, "revision": revision.revision_number,
                "old": old, "new": new_status},
    )
    db.commit()
    return revision
