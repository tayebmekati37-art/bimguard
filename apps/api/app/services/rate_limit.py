"""Login rate limiting.

Failed login attempts are stored in the login_attempts table. Two limits
apply: per email (brute force against one account) and per IP (credential
stuffing across many accounts). Either can trigger a 429.

Design choices:

- DB-backed so it works across multiple workers and survives restarts.
  An in-memory store would not.
- Only failed attempts count. Successful login clears recent failures
  for the email so a typo does not lock out the legitimate owner.
- All time comparisons happen in SQL, not Python. SQLite does not
  preserve tzinfo on DateTime(timezone=True) columns, so a Python-side
  comparison of a stored row against an aware datetime raises TypeError.
  Query-level comparisons work because SQLAlchemy serializes both sides
  consistently for each dialect.
- Fail-closed: if the check itself raises, the login is rejected with
  503, not allowed through.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.login_attempt import LoginAttempt

log = logging.getLogger("bimguard.rate_limit")


class RateLimiter:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    # ------------------------------------------------------------------ windows

    def _email_since(self) -> datetime:
        return datetime.now(UTC) - timedelta(
            minutes=self.settings.login_rate_limit_email_window_minutes
        )

    def _ip_since(self) -> datetime:
        return datetime.now(UTC) - timedelta(
            minutes=self.settings.login_rate_limit_ip_window_minutes
        )

    # ------------------------------------------------------------------ counts

    def _email_count(self, email: str) -> int:
        return int(
            self.db.scalar(
                select(func.count(LoginAttempt.id)).where(
                    LoginAttempt.email == email,
                    LoginAttempt.attempted_at >= self._email_since(),
                )
            )
            or 0
        )

    def _ip_count(self, ip: str) -> int:
        return int(
            self.db.scalar(
                select(func.count(LoginAttempt.id)).where(
                    LoginAttempt.ip == ip,
                    LoginAttempt.attempted_at >= self._ip_since(),
                )
            )
            or 0
        )

    # ------------------------------------------------------------------ public

    def is_limited(self, email: str, ip: str) -> bool:
        if self._email_count(email) >= self.settings.login_rate_limit_email_max:
            return True
        if self._ip_count(ip) >= self.settings.login_rate_limit_ip_max:
            return True
        return False

    def retry_after_seconds(self, email: str, ip: str) -> int:
        """Seconds until the longest still-blocking window frees up.

        Only considers the constraint(s) that are actually blocking. If
        both are blocking, returns the longer wait.
        """
        now = datetime.now(UTC)
        wait = 0

        if self._email_count(email) >= self.settings.login_rate_limit_email_max:
            oldest = self.db.scalar(
                select(func.min(LoginAttempt.attempted_at)).where(
                    LoginAttempt.email == email,
                    LoginAttempt.attempted_at >= self._email_since(),
                )
            )
            if oldest is not None:
                if oldest.tzinfo is None:
                    oldest = oldest.replace(tzinfo=UTC)
                email_wait = int(
                    (
                        oldest
                        + timedelta(minutes=self.settings.login_rate_limit_email_window_minutes)
                        - now
                    ).total_seconds()
                )
                wait = max(wait, email_wait)

        if self._ip_count(ip) >= self.settings.login_rate_limit_ip_max:
            oldest = self.db.scalar(
                select(func.min(LoginAttempt.attempted_at)).where(
                    LoginAttempt.ip == ip,
                    LoginAttempt.attempted_at >= self._ip_since(),
                )
            )
            if oldest is not None:
                if oldest.tzinfo is None:
                    oldest = oldest.replace(tzinfo=UTC)
                ip_wait = int(
                    (
                        oldest
                        + timedelta(minutes=self.settings.login_rate_limit_ip_window_minutes)
                        - now
                    ).total_seconds()
                )
                wait = max(wait, ip_wait)

        return max(0, wait)

    def record_failure(self, email: str, ip: str) -> None:
        self.db.add(LoginAttempt(email=email, ip=ip))

    def clear_email_failures(self, email: str) -> None:
        self.db.execute(delete(LoginAttempt).where(LoginAttempt.email == email))


def get_client_ip(request: Request) -> str:
    """Return the client IP, honouring X-Forwarded-For only when configured.

    Trusting X-Forwarded-For without an actual proxy in front of the API
    is a vulnerability: the header is client-controlled.
    """
    s = get_settings()
    if s.trust_proxy_headers:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def cleanup_expired(db: Session, older_than_minutes: int = 60) -> int:
    """Delete login_attempt rows older than the given age. Returns count.

    Callers should pass an age larger than the longest rate-limit window,
    so removing a row never reduces the effective limit for any user.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
    result = db.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at < cutoff))
    db.commit()
    return result.rowcount or 0