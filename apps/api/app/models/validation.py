import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.db.session import Base


class Rule(Base):
    """Current configuration of a validation rule. Rows are created from the factory defaults on first use."""

    __tablename__ = "rules"

    rule_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    severity: Mapped[str] = mapped_column(String(16))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_by_name: Mapped[str] = mapped_column(String(255), default="system")


class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(255), default="system")
    status: Mapped[str] = mapped_column(String(24))
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    rules_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)


class ValidationIssue(Base):
    __tablename__ = "validation_issues"
    __table_args__ = (
        Index("ix_issues_run_severity", "run_id", "severity"),
        Index("ix_issues_run_rule", "run_id", "rule_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("validation_runs.id", ondelete="CASCADE"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    rule_id: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    document_number: Mapped[str] = mapped_column(String(64), default="")
    element_tag: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    fingerprint: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="open")
    acknowledged_by_name: Mapped[str] = mapped_column(String(255), default="")
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledgement_note: Mapped[str] = mapped_column(Text, default="")


class IssueAcknowledgement(Base):
    """An accepted risk, remembered across runs. It only matches the exact evidence it was given for."""

    __tablename__ = "issue_acknowledgements"
    __table_args__ = (UniqueConstraint("project_id", "fingerprint", name="uq_ack_project_fingerprint"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    fingerprint: Mapped[str] = mapped_column(String(32))
    rule_id: Mapped[str] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(Text)
    acknowledged_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    acknowledged_by_name: Mapped[str] = mapped_column(String(255))
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
