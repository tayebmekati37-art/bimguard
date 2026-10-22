from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import decode_access_token
from app.db.session import SessionLocal, get_db
from app.models.revoked_token import RevokedToken
from app.models.user import Role, User

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _is_revoked(db: Session, jti: str) -> bool:
    """Return True if the jti has been revoked. Raises on database failure.

    Extracted so tests can replace it with a broken implementation to
    confirm the fail-closed behaviour.
    """
    return db.get(RevokedToken, jti) is not None


def get_current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token. Please sign in again.")

    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        # Tokens issued before M19a lack a jti. Reject them rather than
        # accept unrevocable tokens indefinitely. Users sign in once more.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token is missing a session identifier. Please sign in again.",
        )

    try:
        revoked = _is_revoked(db, jti)
    except Exception as exc:  # noqa: BLE001 - fail closed on any DB error
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Authentication service unavailable. Please try again.",
        ) from exc
    if revoked:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Session has been revoked. Please sign in again.",
        )

    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User account not found or disabled.")
    return user


def require_roles(*roles: Role):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            allowed = ", ".join(r.value for r in roles)
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"This action requires one of: {allowed}.")
        return user

    return checker


@dataclass
class PageParams:
    limit: int
    offset: int


def page_params(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> PageParams:
    return PageParams(limit=limit, offset=offset)


def get_session_factory() -> sessionmaker:
    """Background tasks open their own sessions; tests override this to use the test database."""
    return SessionLocal