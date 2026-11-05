import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_token_payload
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.refresh_token import RefreshToken
from app.models.revoked_token import RevokedToken
from app.models.user import User
from app.schemas.auth import RefreshRequest, SessionOut, TokenOut, UserOut
from app.services import audit
from app.services.rate_limit import get_client_ip, get_limiter
from app.services.refresh_tokens import (
    RefreshTokenError,
    issue_refresh_token,
    list_sessions_for_user,
    revoke_family_by_id,
    revoke_family_of,
    rotate,
)

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
        limiter.record_failure(email, ip)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")

    limiter.clear_email_failures(email)
    raw_refresh, refresh_row = issue_refresh_token(db, user)
    audit.record(db, user=user, action="auth.login", entity_type="user", entity_id=user.id)
    db.commit()
    return TokenOut(
        access_token=create_access_token(
            user.id, user.role.value, family_id=refresh_row.family_id,
        ),
        refresh_token=raw_refresh,
        token_type="bearer",
        expires_in=get_settings().jwt_expire_minutes * 60,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/logout", status_code=204)
def logout(
    body: RefreshRequest | None = Body(default=None),
    payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    if body and body.refresh_token:
        n = revoke_family_of(db, body.refresh_token)
        if n > 0:
            log.info("logout: revoked %d refresh token(s) for user %s", n, user.id)

    jti = payload.get("jti")
    exp = payload.get("exp")
    if isinstance(jti, str) and jti and isinstance(exp, (int, float)):
        if db.get(RevokedToken, jti) is None:
            db.add(RevokedToken(
                jti=jti,
                expires_at=datetime.fromtimestamp(exp, tz=UTC),
            ))
            audit.record(db, user=user, action="auth.logout", entity_type="user", entity_id=user.id)
    db.commit()
    return Response(status_code=204)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> TokenOut:
    try:
        user, raw_new, new_row = rotate(db, body.refresh_token)
    except RefreshTokenError as exc:
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    audit.record(db, user=user, action="auth.refresh", entity_type="user", entity_id=user.id)
    db.commit()
    return TokenOut(
        access_token=create_access_token(
            user.id, user.role.value, family_id=new_row.family_id,
        ),
        refresh_token=raw_new,
        token_type="bearer",
        expires_in=get_settings().jwt_expire_minutes * 60,
    )


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    payload: dict = Depends(get_token_payload),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    current_family = payload.get("fam")
    if not isinstance(current_family, str):
        current_family = None
    return list_sessions_for_user(db, user, current_family)


@router.delete("/sessions/{family_id}", status_code=204)
def revoke_session(
    family_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    exists = db.scalar(
        select(RefreshToken.id)
        .where(
            RefreshToken.family_id == family_id,
            RefreshToken.user_id == user.id,
        )
        .limit(1)
    )
    if exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")

    n = revoke_family_by_id(db, family_id)
    audit.record(
        db, user=user, action="auth.session_revoked", entity_type="refresh_family",
        entity_id=family_id, detail={"tokens_revoked": n},
    )
    db.commit()
    return Response(status_code=204)


@router.delete("/sessions", status_code=204)
def revoke_all_sessions(
    keep_current: bool = Query(True),
    payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    current_family = payload.get("fam")
    if not isinstance(current_family, str):
        current_family = None

    if keep_current and current_family is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Cannot identify the current session (token issued before session tracking "
            "was enabled). Sign in again, or set keep_current=false to revoke every session.",
        )

    families = list(db.scalars(
        select(RefreshToken.family_id)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .distinct()
    ))
    revoked_tokens = 0
    revoked_families = 0
    for fid in families:
        if keep_current and fid == current_family:
            continue
        revoked_tokens += revoke_family_by_id(db, fid)
        revoked_families += 1

    if not keep_current:
        jti = payload.get("jti")
        exp = payload.get("exp")
        if isinstance(jti, str) and jti and isinstance(exp, (int, float)):
            if db.get(RevokedToken, jti) is None:
                db.add(RevokedToken(
                    jti=jti,
                    expires_at=datetime.fromtimestamp(exp, tz=UTC),
                ))

    audit.record(
        db, user=user, action="auth.sessions_revoked_all", entity_type="user",
        entity_id=user.id,
        detail={
            "families_revoked": revoked_families,
            "tokens_revoked": revoked_tokens,
            "keep_current": keep_current,
        },
    )
    db.commit()
    return Response(status_code=204)