"""API tests for refresh-token flow (M32)."""
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.models.refresh_token import RefreshToken


def _login(client, email="engineer@test.local"):
    r = client.post("/auth/login", data={"username": email, "password": "pw-test-123"})
    assert r.status_code == 200, r.text
    return r.json()


def test_login_returns_refresh_token(client):
    body = _login(client)
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert isinstance(body["expires_in"], int)


def test_refresh_rotates_and_returns_new_pair(client):
    first = _login(client)
    r = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 200, r.text
    second = r.json()
    assert second["access_token"] != first["access_token"]
    assert second["refresh_token"] != first["refresh_token"]


def test_refresh_new_access_token_works(client):
    first = _login(client)
    r = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    new_access = r.json()["access_token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert r.status_code == 200


def test_refresh_rejects_unknown_token(client):
    r = client.post("/auth/refresh", json={"refresh_token": "does-not-exist"})
    assert r.status_code == 401


def test_refresh_reuse_triggers_family_revocation(client, session_factory):
    first = _login(client)
    raw1 = first["refresh_token"]
    r2 = client.post("/auth/refresh", json={"refresh_token": raw1})
    assert r2.status_code == 200
    raw2 = r2.json()["refresh_token"]

    # Reuse the old one — should 401 AND kill the family
    r3 = client.post("/auth/refresh", json={"refresh_token": raw1})
    assert r3.status_code == 401

    # The newer token is also dead (family-wide revocation)
    r4 = client.post("/auth/refresh", json={"refresh_token": raw2})
    assert r4.status_code == 401


def test_refresh_expired_token(client, session_factory):
    first = _login(client)
    raw = first["refresh_token"]
    # Backdate the row's expiry
    with session_factory() as db:
        from app.services.refresh_tokens import hash_token
        row = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(raw)).one()
        row.expires_at = datetime.now(UTC) - timedelta(days=1)
        db.commit()

    r = client.post("/auth/refresh", json={"refresh_token": raw})
    assert r.status_code == 401


def test_logout_with_refresh_token_revokes_family(client):
    first = _login(client)
    access = first["access_token"]
    raw = first["refresh_token"]

    r = client.post(
        "/auth/logout",
        json={"refresh_token": raw},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 204

    # Old refresh token cannot be used
    r = client.post("/auth/refresh", json={"refresh_token": raw})
    assert r.status_code == 401


def test_logout_without_body_still_works(client):
    """Backward compat: existing callers do not send a body."""
    first = _login(client)
    access = first["access_token"]
    r = client.post("/auth/logout", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 204


def test_old_access_token_dead_after_logout_with_refresh(client):
    first = _login(client)
    r = client.post(
        "/auth/logout",
        json={"refresh_token": first["refresh_token"]},
        headers={"Authorization": f"Bearer {first['access_token']}"},
    )
    assert r.status_code == 204
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {first['access_token']}"})
    assert r.status_code == 401