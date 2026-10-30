"""Tests for session management endpoints (M33)."""
import jwt
import pytest

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.models.refresh_token import RefreshToken
from app.services.refresh_tokens import hash_token


def _login(client, email="engineer@test.local"):
    r = client.post("/auth/login", data={"username": email, "password": "pw-test-123"})
    assert r.status_code == 200, r.text
    return r.json()


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------ token claim

def test_access_token_carries_fam_claim(client):
    body = _login(client)
    payload = decode_access_token(body["access_token"])
    assert "fam" in payload, "access token must carry fam claim (M33)"
    assert isinstance(payload["fam"], str)
    # Should match the refresh token's family
    with_family = None
    # decode refresh and look up its family
    from app.services.refresh_tokens import hash_token as ht
    # We cannot decode the refresh token (opaque), but we can just verify
    # the claim looks like a UUID.
    assert len(payload["fam"]) == 36


# ------------------------------------------------------------------ list

def test_sessions_requires_auth(client):
    assert client.get("/auth/sessions").status_code == 401


def test_sessions_lists_one_for_fresh_login(client):
    body = _login(client)
    r = client.get("/auth/sessions", headers=_bearer(body["access_token"]))
    assert r.status_code == 200, r.text
    sessions = r.json()
    assert len(sessions) == 1
    s = sessions[0]
    assert s["is_current"] is True
    assert s["rotation_count"] == 1
    assert "started_at" in s
    assert "last_active_at" in s
    assert "expires_at" in s


def test_sessions_shows_two_after_two_logins(client):
    body1 = _login(client)
    body2 = _login(client)
    r = client.get("/auth/sessions", headers=_bearer(body1["access_token"]))
    sessions = r.json()
    assert len(sessions) == 2
    currents = [s for s in sessions if s["is_current"]]
    assert len(currents) == 1
    # The current one should be body1's family (that token is being used)
    body1_payload = decode_access_token(body1["access_token"])
    assert currents[0]["family_id"] == body1_payload["fam"]


def test_sessions_reflects_rotation_count(client):
    body = _login(client)
    # Refresh twice
    for _ in range(2):
        r = client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]})
        assert r.status_code == 200
        body = r.json()
    r = client.get("/auth/sessions", headers=_bearer(body["access_token"]))
    sessions = r.json()
    assert len(sessions) == 1
    assert sessions[0]["rotation_count"] == 3  # login + 2 refreshes


# ------------------------------------------------------------------ revoke one

def test_revoke_one_session(client):
    body1 = _login(client)
    body2 = _login(client)
    sessions = client.get("/auth/sessions", headers=_bearer(body1["access_token"])).json()
    other = next(s for s in sessions if not s["is_current"])
    other_family = other["family_id"]

    r = client.request("DELETE", f"/auth/sessions/{other_family}", headers=_bearer(body1["access_token"]))
    assert r.status_code == 204

    # Only current remains
    sessions = client.get("/auth/sessions", headers=_bearer(body1["access_token"])).json()
    assert len(sessions) == 1
    assert sessions[0]["is_current"] is True

    # Revoked session's refresh token no longer works
    r = client.post("/auth/refresh", json={"refresh_token": body2["refresh_token"]})
    assert r.status_code == 401


def test_revoke_unknown_session_404(client):
    body = _login(client)
    r = client.request(
        "DELETE", "/auth/sessions/does-not-exist",
        headers=_bearer(body["access_token"]),
    )
    assert r.status_code == 404


def test_revoke_session_requires_auth(client):
    assert client.request("DELETE", "/auth/sessions/whatever").status_code == 401


def test_cannot_revoke_other_users_session(client, auth, session_factory):
    """User A cannot revoke a family belonging to User B (404, not 403, to avoid
    confirming existence)."""
    # User A logs in
    a = _login(client, email="engineer@test.local")
    # User B (admin) logs in
    r = client.post("/auth/login", data={"username": "admin@test.local", "password": "pw-test-123"})
    assert r.status_code == 200
    b = r.json()
    b_family = decode_access_token(b["access_token"])["fam"]

    # A tries to revoke B's family using A's token
    r = client.request(
        "DELETE", f"/auth/sessions/{b_family}",
        headers=_bearer(a["access_token"]),
    )
    assert r.status_code == 404

    # B's session still works
    r = client.get("/auth/sessions", headers=_bearer(b["access_token"]))
    assert r.status_code == 200


# ------------------------------------------------------------------ revoke all

def test_revoke_all_keeps_current_by_default(client):
    body1 = _login(client)
    body2 = _login(client)
    body3 = _login(client)
    # Confirm 3 sessions
    sessions = client.get("/auth/sessions", headers=_bearer(body1["access_token"])).json()
    assert len(sessions) == 3

    r = client.request("DELETE", "/auth/sessions", headers=_bearer(body1["access_token"]))
    assert r.status_code == 204

    # Only current remains
    sessions = client.get("/auth/sessions", headers=_bearer(body1["access_token"])).json()
    assert len(sessions) == 1
    assert sessions[0]["is_current"] is True

    # body2 and body3 are dead; body1 still works
    assert client.post("/auth/refresh", json={"refresh_token": body2["refresh_token"]}).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": body3["refresh_token"]}).status_code == 401
    assert client.get("/auth/me", headers=_bearer(body1["access_token"])).status_code == 200


def test_revoke_all_including_current(client):
    body = _login(client)
    r = client.request(
        "DELETE", "/auth/sessions?keep_current=false",
        headers=_bearer(body["access_token"]),
    )
    assert r.status_code == 204

    # Current access token now revoked
    assert client.get("/auth/me", headers=_bearer(body["access_token"])).status_code == 401
    # Current refresh token also dead
    assert client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401


def test_revoke_all_requires_auth(client):
    assert client.request("DELETE", "/auth/sessions").status_code == 401


def test_revoke_all_with_legacy_token_returns_400(client, session_factory):
    """A token issued before M33 has no fam claim; keep_current=true should 400
    rather than silently revoke the current session."""
    import uuid
    from datetime import UTC, datetime, timedelta

    s = get_settings()
    uid = session_factory and None  # placeholder
    # Get engineer user id via auth fixture path
    # Simplest: log in normally, then swap in a legacy token
    body = _login(client)
    with session_factory() as db:
        from app.models.user import User
        user = db.query(User).filter(User.email == "engineer@test.local").one()
        uid = user.id
    legacy = jwt.encode(
        {
            "sub": uid,
            "role": "engineer",
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "jti": uuid.uuid4().hex,
            # deliberately NO fam claim
        },
        s.jwt_secret, s.jwt_algorithm,
    )
    r = client.request("DELETE", "/auth/sessions", headers=_bearer(legacy))
    assert r.status_code == 400
    assert "fam" in r.text.lower() or "session tracking" in r.text.lower() or "keep_current" in r.text.lower()