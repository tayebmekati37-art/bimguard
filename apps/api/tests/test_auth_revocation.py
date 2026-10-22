from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, decode_access_token
from app.models.revoked_token import RevokedToken
from app.models.user import User


PASSWORD = "pw-test-123"


def _login(client, email="engineer@test.local") -> str:
    r = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _jti(token: str) -> str:
    return decode_access_token(token)["jti"]


def _user_id(session_factory, email="engineer@test.local") -> str:
    with session_factory() as db:
        return db.query(User).filter(User.email == email).one().id


def test_new_token_contains_unique_jti(client):
    t1 = _login(client)
    t2 = _login(client)
    j1, j2 = _jti(t1), _jti(t2)
    assert isinstance(j1, str) and len(j1) == 32
    assert j1 != j2


def test_valid_token_authenticates(client):
    token = _login(client)
    r = client.get("/auth/me", headers=_bearer(token))
    assert r.status_code == 200


def test_logout_revokes_current_token(client):
    token = _login(client)
    r = client.post("/auth/logout", headers=_bearer(token))
    assert r.status_code == 204

    r = client.get("/auth/me", headers=_bearer(token))
    assert r.status_code == 401
    assert "revoked" in r.json()["detail"].lower()


def test_revoked_token_persists_across_requests(client):
    token = _login(client)
    client.post("/auth/logout", headers=_bearer(token))

    for _ in range(3):
        r = client.get("/auth/me", headers=_bearer(token))
        assert r.status_code == 401


def test_logout_does_not_affect_other_sessions(client):
    token1 = _login(client)
    token2 = _login(client)
    assert _jti(token1) != _jti(token2)

    r = client.post("/auth/logout", headers=_bearer(token1))
    assert r.status_code == 204

    assert client.get("/auth/me", headers=_bearer(token1)).status_code == 401
    assert client.get("/auth/me", headers=_bearer(token2)).status_code == 200


def test_repeated_logout_is_idempotent(client):
    token = _login(client)
    r1 = client.post("/auth/logout", headers=_bearer(token))
    r2 = client.post("/auth/logout", headers=_bearer(token))
    assert r1.status_code == 204
    assert r2.status_code in (204, 401)


def test_unauthenticated_logout_rejected(client):
    r = client.post("/auth/logout")
    assert r.status_code == 401


def test_revocation_row_is_persisted(client, session_factory):
    token = _login(client)
    jti = _jti(token)
    client.post("/auth/logout", headers=_bearer(token))

    with session_factory() as db:
        row = db.get(RevokedToken, jti)
        assert row is not None
        # SQLite drops tzinfo on DateTime(timezone=True) columns; normalize
        # before comparing so this test works on both SQLite and Postgres.
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        assert expires > datetime.now(UTC)


def test_token_without_jti_is_rejected(client, session_factory):
    s = get_settings()
    uid = _user_id(session_factory)
    legacy = jwt.encode(
        {"sub": uid, "role": "engineer", "exp": datetime.now(UTC) + timedelta(hours=1)},
        s.jwt_secret, s.jwt_algorithm,
    )
    r = client.get("/auth/me", headers=_bearer(legacy))
    assert r.status_code == 401
    assert "session identifier" in r.json()["detail"].lower()


def test_invalid_signature_rejected(client):
    s = get_settings()
    forged = jwt.encode(
        {"sub": "any", "role": "admin", "exp": datetime.now(UTC) + timedelta(hours=1), "jti": "x" * 32},
        "wrong-secret", s.jwt_algorithm,
    )
    r = client.get("/auth/me", headers=_bearer(forged))
    assert r.status_code == 401


def test_expired_token_rejected(client, session_factory):
    s = get_settings()
    uid = _user_id(session_factory)
    expired = jwt.encode(
        {"sub": uid, "role": "engineer",
         "exp": datetime.now(UTC) - timedelta(minutes=1),
         "jti": "a" * 32},
        s.jwt_secret, s.jwt_algorithm,
    )
    r = client.get("/auth/me", headers=_bearer(expired))
    assert r.status_code == 401


def test_revocation_db_failure_fails_closed(client, monkeypatch):
    token = _login(client)

    def boom(db: Session, jti: str) -> bool:
        raise RuntimeError("simulated database outage")

    monkeypatch.setattr("app.api.deps._is_revoked", boom)
    r = client.get("/auth/me", headers=_bearer(token))
    assert r.status_code == 503
    assert "unavailable" in r.json()["detail"].lower()


def test_existing_workflows_still_work(client):
    token = _login(client)
    assert client.get("/auth/me", headers=_bearer(token)).status_code == 200
    assert client.post("/auth/logout", headers=_bearer(token)).status_code == 204
    assert client.get("/auth/me", headers=_bearer(token)).status_code == 401