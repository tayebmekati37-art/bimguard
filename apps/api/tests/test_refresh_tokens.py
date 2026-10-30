"""Tests for refresh-token service (M32)."""
from datetime import UTC, datetime, timedelta

import pytest

from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.refresh_tokens import (
    RefreshTokenError,
    hash_token,
    issue_refresh_token,
    revoke_family_of,
    rotate,
)


def _user(session_factory, email="engineer@test.local"):
    with session_factory() as db:
        return db.query(User).filter(User.email == email).one()


# ------------------------------------------------------------------ issue

def test_issue_returns_raw_and_row(session_factory):
    user = _user(session_factory)
    with session_factory() as db:
        raw, row = issue_refresh_token(db, user)
        db.commit()
        assert isinstance(raw, str)
        assert len(raw) >= 64
        assert row.token_hash == hash_token(raw)
        assert row.revoked_at is None
        assert row.family_id


def test_issue_two_tokens_get_different_families(session_factory):
    user = _user(session_factory)
    with session_factory() as db:
        _, r1 = issue_refresh_token(db, user)
        _, r2 = issue_refresh_token(db, user)
        db.commit()
        assert r1.family_id != r2.family_id


def test_issue_with_explicit_family_reuses_it(session_factory):
    user = _user(session_factory)
    with session_factory() as db:
        _, r1 = issue_refresh_token(db, user)
        _, r2 = issue_refresh_token(db, user, family_id=r1.family_id)
        db.commit()
        assert r1.family_id == r2.family_id


# ------------------------------------------------------------------ rotate

def test_rotate_creates_new_token_in_same_family(session_factory):
    user = _user(session_factory)
    with session_factory() as db:
        raw, old_row = issue_refresh_token(db, user)
        db.commit()
        family = old_row.family_id

        u, new_raw, new_row = rotate(db, raw)
        db.commit()

        assert u.id == user.id
        assert new_raw != raw
        assert new_row.family_id == family
        assert new_row.revoked_at is None


def test_rotate_revokes_old_token(session_factory):
    user = _user(session_factory)
    with session_factory() as db:
        raw, old_row = issue_refresh_token(db, user)
        db.commit()
        old_id = old_row.id

        rotate(db, raw)
        db.commit()

        refreshed = db.get(RefreshToken, old_id)
        assert refreshed.revoked_at is not None
        assert refreshed.replaced_by_id is not None


def test_rotate_fails_on_unknown_token(session_factory):
    with session_factory() as db:
        with pytest.raises(RefreshTokenError, match="not recognised"):
            rotate(db, "not-a-real-token")


def test_rotate_fails_on_empty_token(session_factory):
    with session_factory() as db:
        with pytest.raises(RefreshTokenError):
            rotate(db, "")


def test_rotate_fails_on_expired_token(session_factory):
    user = _user(session_factory)
    with session_factory() as db:
        raw, row = issue_refresh_token(db, user)
        # Backdate expiry
        row.expires_at = datetime.now(UTC) - timedelta(days=1)
        db.commit()

        with pytest.raises(RefreshTokenError, match="expired"):
            rotate(db, raw)


def test_rotate_reuse_revokes_family(session_factory):
    """After rotation, presenting the old token triggers family-wide revocation."""
    user = _user(session_factory)
    with session_factory() as db:
        raw1, _ = issue_refresh_token(db, user)
        db.commit()
        _, raw2, row2 = rotate(db, raw1)
        db.commit()
        family = row2.family_id

        # Old token presented again -> reuse detected
        with pytest.raises(RefreshTokenError, match="already been used"):
            rotate(db, raw1)
        db.commit()

        # All rows in family now revoked, including raw2's row
        remaining = list(db.query(RefreshToken).filter(RefreshToken.family_id == family))
        assert all(r.revoked_at is not None for r in remaining), \
            f"some tokens still active: {[(r.id, r.revoked_at) for r in remaining]}"

        # Attempting to use raw2 now also fails (family dead)
        with pytest.raises(RefreshTokenError):
            rotate(db, raw2)


# ------------------------------------------------------------------ logout / revoke

def test_revoke_family_of_revokes_all_in_family(session_factory):
    user = _user(session_factory)
    with session_factory() as db:
        raw1, _ = issue_refresh_token(db, user)
        db.commit()
        _, _, row2 = rotate(db, raw1)
        db.commit()
        family = row2.family_id

        n = revoke_family_of(db, raw1)
        db.commit()
        assert n >= 1

        remaining = list(db.query(RefreshToken).filter(RefreshToken.family_id == family))
        assert all(r.revoked_at is not None for r in remaining)


def test_revoke_family_of_unknown_token_is_noop(session_factory):
    with session_factory() as db:
        assert revoke_family_of(db, "nonexistent") == 0
        assert revoke_family_of(db, "") == 0


# ------------------------------------------------------------------ hash

def test_hash_is_deterministic_sha256():
    import hashlib
    raw = "hello"
    expected = hashlib.sha256(b"hello").hexdigest()
    assert hash_token(raw) == expected
    assert len(hash_token(raw)) == 64