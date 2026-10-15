import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.db.session import Base


class AIQuery(Base):
    """One logged AI explanation request.

    Records every call to the orchestrator, whether the answer came from
    the template path or the AI path, so the hourly limit can be enforced
    and the audit trail is complete.
    """

    __tablename__ = "ai_queries"
    __table_args__ = (
        Index("ix_ai_queries_project_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(String(32))
    answer: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(String(16))  # "template" or "ai"
    facts: Mapped[list] = mapped_column(JSON, default=list)
    violations: Mapped[list] = mapped_column(JSON, default=list)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)