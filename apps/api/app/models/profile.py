from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.db.session import Base


class ProfileActivation(Base):
    """Which profile is active for a project. At most one row per project."""

    __tablename__ = "profile_activations"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    profile_id: Mapped[str] = mapped_column(String(64))
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    activated_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    activated_by_name: Mapped[str] = mapped_column(String(255), default="system")