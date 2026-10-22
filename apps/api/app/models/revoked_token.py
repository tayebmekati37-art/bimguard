from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RevokedToken(Base):
    """JWT IDs that have been explicitly revoked via logout.

    Rows persist until the token's natural expiry. Expired rows can be
    removed by scripts/cleanup_revoked_tokens.py; there is no automatic
    per-request cleanup, because that would make every authenticated
    request do extra write work.
    """

    __tablename__ = "revoked_tokens"
    __table_args__ = (
        Index("ix_revoked_tokens_expires_at", "expires_at"),
    )

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )