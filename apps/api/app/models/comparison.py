import uuid
from datetime import datetime

from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.db.session import Base


class RevisionComparison(Base):
    """One run of change detection between two revisions of a document. Re-running replaces it."""

    __tablename__ = "revision_comparisons"
    __table_args__ = (UniqueConstraint("from_revision_id", "to_revision_id", name="uq_comparison_pair"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    from_revision_id: Mapped[str] = mapped_column(ForeignKey("document_revisions.id", ondelete="CASCADE"))
    to_revision_id: Mapped[str] = mapped_column(ForeignKey("document_revisions.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(255), default="system")
    total_changes: Mapped[int] = mapped_column(Integer, default=0)
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class DetectedChange(Base):
    __tablename__ = "detected_changes"
    __table_args__ = (
        Index("ix_changes_comparison_type", "comparison_id", "change_type"),
        Index("ix_changes_comparison_severity", "comparison_id", "severity"),
        Index("ix_changes_comparison_tag", "comparison_id", "element_tag"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    comparison_id: Mapped[str] = mapped_column(ForeignKey("revision_comparisons.id", ondelete="CASCADE"))
    element_guid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    element_tag: Mapped[str] = mapped_column(String(64), default="")
    element_name: Mapped[str] = mapped_column(String(255), default="")
    ifc_class: Mapped[str] = mapped_column(String(64), default="")
    change_type: Mapped[str] = mapped_column(String(32))
    field: Mapped[str] = mapped_column(String(255))
    old_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    new_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    severity: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float] = mapped_column(Float)
    summary: Mapped[str] = mapped_column(Text)
    match_method: Mapped[str] = mapped_column(String(8), default="guid")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
