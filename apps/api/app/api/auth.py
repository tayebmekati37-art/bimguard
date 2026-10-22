from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, status
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

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
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
        # get_current_user already validated the token; this branch should
        # never fire. Fail closed anyway.
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