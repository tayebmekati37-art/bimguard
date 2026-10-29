import logging
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, oauth2
from app.core.security import create_access_token, decode_access_token, verify_password
from app.db.session import get_db
from app.models.revoked_token import RevokedToken
from app.models.user import User
from app.schemas.auth import TokenOut, UserOut
from app.services import audit
from app.services.rate_limit import get_client_ip, get_limiter

log = logging.getLogger("bimguard.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenOut:
    email = form.username.lower()
    ip = get_client_ip(request)
    limiter = get_limiter(db)

    try:
        limited = limiter.is_limited(email, ip)
    except Exception as exc:  # noqa: BLE001 - fail closed
        log.exception("rate limit check failed for %s", email)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Authentication service unavailable. Please try again.",
        ) from exc

    if limited:
        retry_after = limiter.retry_after_seconds(email, ip)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many login attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        # Record the failure and commit before raising, so the row is
        # visible to the next request.
        limiter.record_failure(email, ip)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")

    # Successful login: a user's own typos should not accumulate.
    limiter.clear_email_failures(email)
    audit.record(db, user=user, action="auth.login", entity_type="user", entity_id=user.id)
    db.commit()
    return TokenOut(access_token=create_access_token(user.id, user.role.value))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/logout", status_code=204)
def logout(
    token: str = Depends(oauth2),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Revoke the calling token's jti until its natural expiry.

    Idempotent: revoking an already-revoked token is a no-op. Only the
    caller's own session is revoked; other sessions of the same user are
    unaffected.
    """
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token.")
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not isinstance(jti, str) or not jti or not isinstance(exp, (int, float)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token is missing required claims.")
    if db.get(RevokedToken, jti) is None:
        db.add(
            RevokedToken(
                jti=jti,
                expires_at=datetime.fromtimestamp(exp, tz=UTC),
            )
        )
        audit.record(db, user=user, action="auth.logout", entity_type="user", entity_id=user.id)
        db.commit()
    return Response(status_code=204)