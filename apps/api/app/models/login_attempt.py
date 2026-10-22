import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class LoginAttempt(Base):
    """A failed login attempt.

    Rows exist only for rate limiting. Successful logins clear recent
    rows for the same email, so a typo followed by the correct password
    does not lock the user out. Rows outside the rate-limit window have
    no effect and are removed by scripts/cleanup_login_attempts.py.
    """

    __tablename__ = "login_attempts"
    __table_args__ = (
        Index("ix_login_attempts_email_time", "email", "attempted_at"),
        Index("ix_login_attempts_ip_time", "ip", "attempted_at"),
        Index("ix_login_attempts_attempted_at", "attempted_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255))
    ip: Mapped[str] = mapped_column(String(64))
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )