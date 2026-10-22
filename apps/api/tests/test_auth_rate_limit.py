"""Rate limiting tests for POST /auth/login."""
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.models.login_attempt import LoginAttempt
from app.services.rate_limit import cleanup_expired


GOOD_PASSWORD = "pw-test-123"


def _failed_login(client, email="engineer@test.local"):
    return client.post("/auth/login", data={"username": email, "password": "wrong"})


def _successful_login(client, email="engineer@test.local"):
    return client.post("/auth/login", data={"username": email, "password": GOOD_PASSWORD})


# ------------------------------------------------------------------ email limit

def test_email_limit_blocks_after_n_failures(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "login_rate_limit_email_max", 2)
    monkeypatch.setattr(s, "login_rate_limit_ip_max", 1000)

    assert _failed_login(client).status_code == 401
    assert _failed_login(client).status_code == 401
    r = _failed_login(client)
    assert r.status_code == 429
    assert "Too many login attempts" in r.json()["detail"]


def test_ip_limit_blocks_after_n_failures(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "login_rate_limit_email_max", 1000)
    monkeypatch.setattr(s, "login_rate_limit_ip_max", 2)

    assert _failed_login(client, "a@test.local").status_code == 401
    assert _failed_login(client, "b@test.local").status_code == 401
    r = _failed_login(client, "c@test.local")
    assert r.status_code == 429


def test_successful_login_clears_email_failures(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "login_rate_limit_email_max", 3)
    monkeypatch.setattr(s, "login_rate_limit_ip_max", 1000)

    for _ in range(2):
        assert _failed_login(client).status_code == 401
    assert _successful_login(client).status_code == 200
    for _ in range(2):
        assert _failed_login(client).status_code == 401


def test_rate_limit_returns_retry_after(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "login_rate_limit_email_max", 1)
    monkeypatch.setattr(s, "login_rate_limit_ip_max", 1000)
    monkeypatch.setattr(s, "login_rate_limit_email_window_minutes", 15)

    _failed_login(client)
    r = _failed_login(client)
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    retry = int(r.headers["Retry-After"])
    assert 0 < retry <= 900


def test_rate_limit_message_same_for_real_and_fake_accounts(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "login_rate_limit_email_max", 1)
    monkeypatch.setattr(s, "login_rate_limit_ip_max", 1000)

    _failed_login(client, "nonexistent@test.local")
    r_fake = _failed_login(client, "nonexistent@test.local")
    assert r_fake.status_code == 429

    _failed_login(client, "engineer@test.local")
    r_real = _failed_login(client, "engineer@test.local")
    assert r_real.status_code == 429

    assert r_fake.json()["detail"] == r_real.json()["detail"]


def test_expired_attempts_do_not_count(client, monkeypatch, session_factory):
    s = get_settings()
    monkeypatch.setattr(s, "login_rate_limit_email_max", 2)
    monkeypatch.setattr(s, "login_rate_limit_ip_max", 1000)
    monkeypatch.setattr(s, "login_rate_limit_email_window_minutes", 15)

    with session_factory() as db:
        old = datetime.now(UTC) - timedelta(minutes=20)
        for _ in range(5):
            db.add(LoginAttempt(email="engineer@test.local", ip="127.0.0.1", attempted_at=old))
        db.commit()

    assert _failed_login(client).status_code == 401


def test_cleanup_removes_old_rows(client, session_factory):
    with session_factory() as db:
        old = datetime.now(UTC) - timedelta(hours=2)
        recent = datetime.now(UTC) - timedelta(minutes=5)
        db.add(LoginAttempt(email="a@test.local", ip="1.1.1.1", attempted_at=old))
        db.add(LoginAttempt(email="b@test.local", ip="2.2.2.2", attempted_at=recent))
        db.commit()

    with session_factory() as db:
        deleted = cleanup_expired(db, older_than_minutes=60)
        assert deleted == 1

    with session_factory() as db:
        rows = list(db.query(LoginAttempt))
        assert len(rows) == 1
        assert rows[0].email == "b@test.local"


def test_rate_limit_persists_across_sessions(client, monkeypatch, session_factory):
    s = get_settings()
    monkeypatch.setattr(s, "login_rate_limit_email_max", 1)
    monkeypatch.setattr(s, "login_rate_limit_ip_max", 1000)

    _failed_login(client)

    with session_factory() as db:
        rows = list(db.query(LoginAttempt).filter(LoginAttempt.email == "engineer@test.local"))
        assert len(rows) == 1

    assert _failed_login(client).status_code == 429


def test_legitimate_login_still_works(client):
    r = _successful_login(client)
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_logout_still_works_after_rate_limit_change(client):
    """Sanity: M19a logout is not broken by the new login flow."""
    login = _successful_login(client)
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 204
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401