import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON, BigInteger, DateTime, Enum, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, event, inspect,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.session import Base
from app.models.project import Project


def _enum(cls: type[enum.Enum], length: int = 20) -> Enum:
    return Enum(cls, native_enum=False, length=length, values_callable=lambda e: [m.value for m in e])


class Discipline(str, enum.Enum):
    ARCHITECTURE = "architecture"
    STRUCTURE = "structure"
    MEP = "mep"
    EQUIPMENT = "equipment"
    QUANTITY = "quantity"
    GENERAL = "general"


class RevisionStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    ISSUED = "issued"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("project_id", "document_number", name="uq_document_project_number"),
        Index("ix_documents_project_discipline", "project_id", "discipline"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_number: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    discipline: Mapped[Discipline] = mapped_column(_enum(Discipline))
    file_type: Mapped[str] = mapped_column(String(16), default="")
    status: Mapped[RevisionStatus] = mapped_column(_enum(RevisionStatus), default=RevisionStatus.DRAFT)
    current_revision_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    author: Mapped[str] = mapped_column(String(120), default="")
    source_system: Mapped[str] = mapped_column(String(80), default="BIMGuard upload")
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    checksum: Mapped[str] = mapped_column(String(64), default="")
    issue_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="documents")
    revisions: Mapped[list["DocumentRevision"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True,
        order_by="DocumentRevision.revision_number",
    )


class DocumentRevision(Base):
    """Immutable history: only `status` may change after creation."""

    __tablename__ = "document_revisions"
    __table_args__ = (
        UniqueConstraint("document_id", "revision_number", name="uq_revision_document_number"),
        Index("ix_revisions_document_checksum", "document_id", "checksum"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(64))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[RevisionStatus] = mapped_column(_enum(RevisionStatus), default=RevisionStatus.DRAFT)
    change_summary: Mapped[str] = mapped_column(Text, default="")
    previous_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_revisions.id", ondelete="SET NULL"), nullable=True
    )

    document: Mapped[Document] = relationship(back_populates="revisions")


class ImmutableRevisionError(Exception):
    """Raised when code tries to rewrite revision history."""


_IMMUTABLE_FIELDS = (
    "document_id", "revision_number", "file_path", "original_filename", "file_size", "checksum",
    "uploaded_at", "created_by_id", "created_by_name", "change_summary", "previous_revision_id",
)


@event.listens_for(DocumentRevision, "before_update")
def _guard_revision_history(_mapper, _connection, target: DocumentRevision) -> None:
    state = inspect(target)
    for name in _IMMUTABLE_FIELDS:
        if state.attrs[name].history.has_changes():
            raise ImmutableRevisionError(
                f"Revision history is immutable: '{name}' cannot be changed. Upload a new revision instead."
            )
