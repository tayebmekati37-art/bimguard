import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.db.session import Base


class Dependency(Base):
    """A relationship between two documents of one project. `validated_against_revision` is the revision number
    of the document that supplies the information (the provider) that the other document was last checked against."""

    __tablename__ = "dependencies"
    __table_args__ = (
        UniqueConstraint("source_document_id", "target_document_id", "relationship_type", name="uq_dependency_pair_type"),
        CheckConstraint("source_document_id != target_document_id", name="ck_dependency_not_self"),
        Index("ix_dependencies_project", "project_id"),
        Index("ix_dependencies_target", "target_document_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    source_document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    target_document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    relationship_type: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    reason: Mapped[str] = mapped_column(Text)
    validated_against_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validated_by_name: Mapped[str] = mapped_column(String(255), default="")
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(255), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
