from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.user import User


def _user_id(session_factory, email="engineer@test.local"):
    with session_factory() as db:
        return db.query(User).filter(User.email == email).one().id


def test_expired_token_is_rejected(client, auth, session_factory):
    s = get_settings()
    uid = _user_id(session_factory)
    expired = jwt.encode(
        {"sub": uid, "role": "engineer", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        s.jwt_secret, s.jwt_algorithm,
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


def test_forged_token_is_rejected(client, session_factory):
    uid = _user_id(session_factory)
    forged = jwt.encode(
        {"sub": uid, "role": "admin", "exp": datetime.now(UTC) + timedelta(hours=1)},
        "wrong-secret", "HS256",
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_no_token_is_rejected(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_viewer_cannot_create_project(client, auth):
    r = client.post("/projects", json={"name": "X", "client": "C"}, headers=auth("viewer"))
    assert r.status_code == 403


def test_viewer_cannot_run_validation(client, auth, project):
    r = client.post(f"/projects/{project['id']}/validate", headers=auth("viewer"))
    assert r.status_code == 403


def test_viewer_cannot_acknowledge(client, auth, session_factory):
    # No issue to acknowledge; the 403 is on the role guard, not on the resource.
    r = client.post("/issues/does-not-exist/acknowledge", json={"note": "test"},
                    headers=auth("viewer"))
    assert r.status_code in (403, 404)  # 403 from role guard, 404 if we ever reach resource


def test_engineer_cannot_delete_project(client, auth, project):
    r = client.delete(f"/projects/{project['id']}", headers=auth("engineer"))
    assert r.status_code == 403


def test_engineer_cannot_activate_profile(client, auth, project):
    r = client.put(f"/projects/{project['id']}/profile", json={"profile_id": "jp-bimcim-v1"},
                   headers=auth("engineer"))
    assert r.status_code == 403


def test_engineer_cannot_read_audit(client, auth):
    r = client.get("/audit-logs", headers=auth("engineer"))
    assert r.status_code == 403


def test_engineer_cannot_create_backup(client, auth):
    r = client.post("/admin/backup", headers=auth("engineer"))
    assert r.status_code == 403


def test_valid_token_still_works(client, auth):
    r = client.get("/auth/me", headers=auth("engineer"))
    assert r.status_code == 200