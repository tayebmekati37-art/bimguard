"""Tests for the Redis-backed rate limiter (M31)."""
import fakeredis
import pytest

from app.core.config import get_settings
from app.services import rate_limit_redis
from app.services.rate_limit import RateLimiter, get_limiter
from app.services.rate_limit_redis import RedisRateLimiter


@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def redis_limiter(fake_redis):
    return RedisRateLimiter(fake_redis, get_settings())


# ------------------------------------------------------------------ interface

def test_redis_limiter_has_same_interface_as_db(redis_limiter):
    for method in ("is_limited", "retry_after_seconds", "record_failure", "clear_email_failures"):
        assert hasattr(redis_limiter, method), f"missing method: {method}"


# ------------------------------------------------------------------ email limit

def test_email_limit_blocks_after_max(redis_limiter, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "login_rate_limit_email_max", 2)
    monkeypatch.setattr(s, "login_rate_limit_ip_max", 1000)

    assert not redis_limiter.is_limited("a@test.local", "1.1.1.1")
    redis_limiter.record_failure("a@test.local", "1.1.1.1")
    assert not redis_limiter.is_limited("a@test.local", "1.1.1.1")
    redis_limiter.record_failure("a@test.local", "1.1.1.1")
    assert redis_limiter.is_limited("a@test.local", "1.1.1.1")


def test_ip_limit_blocks_after_max(redis_limiter, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "login_rate_limit_email_max", 1000)
    monkeypatch.setattr(s, "login_rate_limit_ip_max", 2)

    redis_limiter.record_failure("a@test.local", "1.1.1.1")
    redis_limiter.record_failure("b@test.local", "1.1.1.1")
    assert redis_limiter.is_limited("c@test.local", "1.1.1.1")


def test_clear_email_failures_resets_email_count(redis_limiter, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "login_rate_limit_email_max", 2)
    monkeypatch.setattr(s, "login_rate_limit_ip_max", 1000)

    redis_limiter.record_failure("a@test.local", "1.1.1.1")
    redis_limiter.record_failure("a@test.local", "1.1.1.1")
    assert redis_limiter.is_limited("a@test.local", "1.1.1.1")

    redis_limiter.clear_email_failures("a@test.local")
    assert not redis_limiter.is_limited("a@test.local", "1.1.1.1")


# ------------------------------------------------------------------ retry_after

def test_retry_after_zero_when_not_limited(redis_limiter, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "login_rate_limit_email_max", 5)
    monkeypatch.setattr(s, "login_rate_limit_ip_max", 100)
    redis_limiter.record_failure("a@test.local", "1.1.1.1")
    assert redis_limiter.retry_after_seconds("a@test.local", "1.1.1.1") == 0


def test_retry_after_returns_positive_ttl_when_limited(redis_limiter, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "login_rate_limit_email_max", 1)
    monkeypatch.setattr(s, "login_rate_limit_ip_max", 1000)
    monkeypatch.setattr(s, "login_rate_limit_email_window_minutes", 15)

    redis_limiter.record_failure("a@test.local", "1.1.1.1")
    redis_limiter.record_failure("a@test.local", "1.1.1.1")
    assert redis_limiter.is_limited("a@test.local", "1.1.1.1")
    retry = redis_limiter.retry_after_seconds("a@test.local", "1.1.1.1")
    assert 0 < retry <= 900


# ------------------------------------------------------------------ TTL behavior

def test_expire_set_only_on_first_increment(redis_limiter, fake_redis, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "login_rate_limit_email_window_minutes", 15)

    redis_limiter.record_failure("a@test.local", "1.1.1.1")
    ttl1 = fake_redis.ttl("bimguard:login:email:a@test.local")
    assert 0 < ttl1 <= 900

    # Record a second failure; TTL must NOT reset (fixed window, not sliding)
    redis_limiter.record_failure("a@test.local", "1.1.1.1")
    ttl2 = fake_redis.ttl("bimguard:login:email:a@test.local")
    # Allow 1-2 second drift from the test itself
    assert abs(ttl1 - ttl2) <= 2


# ------------------------------------------------------------------ factory

def test_get_limiter_defaults_to_db(session_factory, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "rate_limit_backend", "db")
    with session_factory() as db:
        limiter = get_limiter(db)
    assert isinstance(limiter, RateLimiter)


def test_get_limiter_returns_redis_when_configured(fake_redis, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "rate_limit_backend", "redis")
    monkeypatch.setattr(rate_limit_redis, "_redis_client", fake_redis)
    with _dummy_session() as db:
        limiter = get_limiter(db)
    assert isinstance(limiter, RedisRateLimiter)


def test_get_limiter_unknown_backend_falls_back_to_db(session_factory, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "rate_limit_backend", "memcached")
    with session_factory() as db:
        limiter = get_limiter(db)
    assert isinstance(limiter, RateLimiter)


def test_redis_client_raises_without_url(monkeypatch):
    rate_limit_redis.reset_redis_client()
    s = get_settings()
    monkeypatch.setattr(s, "redis_url", "")
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        rate_limit_redis.get_redis_client()


# ------------------------------------------------------------------ end-to-end via API

def test_api_login_uses_redis_limiter_when_configured(client, fake_redis, monkeypatch):
    """When RATE_LIMIT_BACKEND=redis, the login endpoint rate-limits via Redis."""
    s = get_settings()
    monkeypatch.setattr(s, "rate_limit_backend", "redis")
    monkeypatch.setattr(s, "login_rate_limit_email_max", 2)
    monkeypatch.setattr(s, "login_rate_limit_ip_max", 1000)
    monkeypatch.setattr(rate_limit_redis, "_redis_client", fake_redis)

    # Two failed logins are ok (401)
    r1 = client.post("/auth/login", data={"username": "x@test.local", "password": "wrong"})
    assert r1.status_code == 401
    r2 = client.post("/auth/login", data={"username": "x@test.local", "password": "wrong"})
    assert r2.status_code == 401
    # Third is rate limited
    r3 = client.post("/auth/login", data={"username": "x@test.local", "password": "wrong"})
    assert r3.status_code == 429
    assert "Retry-After" in r3.headers


# ------------------------------------------------------------------ helpers

class _dummy_session:
    """Minimal session stub for factory tests (the factory does not use db for redis backend)."""
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False