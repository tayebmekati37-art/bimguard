"""Refresh-token service (M32).

Rotation policy: each refresh revokes the presented token and creates a new
one in the same family. Reuse of a revoked token is treated as compromise:
the entire family is revoked. Logout also revokes the entire family of the
presented token.

Raw token values are generated with secrets.token_urlsafe(48) (64 chars of
base64url; ~288 bits of entropy) and returned exactly once. Only the SHA-256
hex digest is stored (64 chars). SHA-256 without salt is sufficient because
the input is already high entropy; a slow hash (bcrypt/argon2) would only
add latency to every refresh with no security benefit.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.refresh_token import RefreshToken
from app.models.user import User

log = logging.getLogger("bimguard.refresh")


class RefreshTokenError(Exception):
    """Presented refresh token is invalid, expired, or detected as reused."""


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_refresh_token(
    db: Session, user: User, family_id: str | None = None
) -> tuple[str, RefreshToken]:
    """Create a new refresh token. Returns (raw, row). Caller commits."""
    raw = secrets.token_urlsafe(48)
    days = get_settings().refresh_token_expire_days
    row = RefreshToken(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=hash_token(raw),
        family_id=family_id or str(uuid.uuid4()),
        expires_at=datetime.now(UTC) + timedelta(days=days),
    )
    db.add(row)
    db.flush()
    return raw, row


def _revoke_family(db: Session, family_id: str) -> int:
    """Revoke every currently-valid token in the family. Returns count."""
    now = datetime.now(UTC)
    rows = list(db.scalars(
        select(RefreshToken).where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
    ))
    for r in rows:
        r.revoked_at = now
    return len(rows)


def rotate(db: Session, raw: str) -> tuple[User, str, RefreshToken]:
    """Validate a refresh token, rotate it, and return (user, new_raw, new_row).

    Raises RefreshTokenError for:
      - token not found
      - token already revoked (reuse detected; family gets revoked)
      - token expired
      - user missing or inactive
    """
    if not raw or not isinstance(raw, str):
        raise RefreshTokenError("Refresh token is required.")

    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)))
    if row is None:
        raise RefreshTokenError("Refresh token not recognised.")

    if row.revoked_at is not None:
        # Reuse: revoke entire family as a defensive measure.
        n = _revoke_family(db, row.family_id)
        log.warning(
            "Refresh token reuse detected (family=%s, additionally revoked=%d)",
            row.family_id, n,
        )
        raise RefreshTokenError(
            "Refresh token has already been used. All sessions in this family have been revoked."
        )

    if row.expires_at < datetime.now(UTC):
        raise RefreshTokenError("Refresh token has expired.")

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise RefreshTokenError("User account not found or disabled.")

    # Rotate: revoke current, create successor in same family, link them.
    row.revoked_at = datetime.now(UTC)
    raw_new, new_row = issue_refresh_token(db, user, family_id=row.family_id)
    row.replaced_by_id = new_row.id
    return user, raw_new, new_row


def revoke_family_of(db: Session, raw: str) -> int:
    """Logout: revoke the entire family of the presented refresh token.

    Idempotent: if the token is not found (already deleted, never existed),
    returns 0 without raising. Idempotence matters because a client that
    has been offline can still present a stale token at logout time.
    """
    if not raw or not isinstance(raw, str):
        return 0
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)))
    if row is None:
        return 0
    return _revoke_family(db, row.family_id)
# ------------------------------------------------------------------ session management (M33)

def _aware(dt: datetime | None) -> datetime | None:
    """Normalise a datetime to UTC-aware for comparisons and JSON output.

    SQLite returns naive datetimes from DateTime(timezone=True) columns,
    Postgres returns aware. The session list needs consistent comparisons
    and consistent ISO output.
    """
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def revoke_family_by_id(db: Session, family_id: str) -> int:
    """Revoke every currently-valid token in the family. Returns count.

    Used by the /auth/sessions endpoints (M33) to revoke a family without
    requiring its raw refresh token. Caller must verify the family belongs
    to the acting user before calling this.
    """
    return _revoke_family(db, family_id)


def list_sessions_for_user(
    db: Session, user: User, current_family_id: str | None,
) -> list[dict]:
    """Return one entry per live family for this user.

    A family is "live" if it has at least one non-revoked, non-expired token.
    Rotated tokens contribute to rotation_count and started_at but are ignored
    for liveness.

    Sorted by last_active_at descending.
    """
    tokens = list(db.scalars(
        select(RefreshToken)
        .where(RefreshToken.user_id == user.id)
        .order_by(RefreshToken.created_at)
    ))
    families: dict[str, list[RefreshToken]] = {}
    for t in tokens:
        families.setdefault(t.family_id, []).append(t)

    now = datetime.now(UTC)
    out: list[dict] = []
    for fid, toks in families.items():
        live = [t for t in toks
                if t.revoked_at is None and (_aware(t.expires_at) or now) > now]
        if not live:
            continue
        started = min(t.created_at for t in toks)
        last_active = max(t.created_at for t in toks)
        expires = max(_aware(t.expires_at) for t in live)
        out.append({
            "family_id": fid,
            "started_at": _aware(started),
            "last_active_at": _aware(last_active),
            "expires_at": expires,
            "rotation_count": len(toks),
            "is_current": fid == current_family_id,
        })
    out.sort(key=lambda s: s["last_active_at"], reverse=True)
    return out