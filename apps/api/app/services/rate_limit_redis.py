"""Redis-backed login rate limiter (M31).

Drop-in replacement for app.services.rate_limit.RateLimiter. Same public
interface, same fail-closed contract, same semantics.

Semantics: fixed 15-minute (configurable) window per (email) and per (IP).
  - record_failure(email, ip): INCR both keys, set EXPIRE on first INCR
  - is_limited(email, ip): GET both keys, compare against configured maxima
  - retry_after_seconds: TTL of the limiting key(s), whichever is longer
  - clear_email_failures(email): DEL the email key

Difference from DB backend: the DB backend uses a rolling window based on
attempted_at, so a failed attempt leaves the window at t + 15m. Redis uses
a fixed window starting at the first failure. In practice this means the
Redis window can close slightly earlier if failures are spread out, and
slightly later if the first failure is followed by a burst. Both are
standard rate-limiting behaviours; neither is more correct.

Failure modes:
  - Redis unreachable: any exception from the client propagates. The login
    endpoint catches it and returns 503 (fail closed, matching DB behaviour).
  - Redis slow: the underlying redis-py client has its own timeout (default
    20s). Set REDIS_SOCKET_TIMEOUT_SECONDS to override if needed.

What this does NOT do:
  - Sliding windows. Fixed windows are simpler and adequate; the DB
    backend is available for anyone who needs precise sliding behaviour.
  - Distributed lock coordination. INCR is atomic; nothing else needs to be.
  - Persistence. Rate limit state is intentionally ephemeral. Redis can be
    configured as a cache (no RDB/AOF) or as a queue (with RDB/AOF); for
    rate limiting, cache-only is correct — losing counters on restart is
    safer than blocking users because Redis restored stale state.
"""
from __future__ import annotations

import logging
import os

from app.core.config import get_settings

log = logging.getLogger("bimguard.rate_limit.redis")

_redis_client = None


class RedisRateLimiter:
    def __init__(self, client, settings) -> None:
        self.client = client
        self.settings = settings

    def _email_key(self, email: str) -> str:
        return f"bimguard:login:email:{email}"

    def _ip_key(self, ip: str) -> str:
        return f"bimguard:login:ip:{ip}"

    def _email_window_seconds(self) -> int:
        return int(self.settings.login_rate_limit_email_window_minutes * 60)

    def _ip_window_seconds(self) -> int:
        return int(self.settings.login_rate_limit_ip_window_minutes * 60)

    def _count(self, key: str) -> int:
        value = self.client.get(key)
        return int(value) if value is not None else 0

    def is_limited(self, email: str, ip: str) -> bool:
        if self._count(self._email_key(email)) >= self.settings.login_rate_limit_email_max:
            return True
        if self._count(self._ip_key(ip)) >= self.settings.login_rate_limit_ip_max:
            return True
        return False

    def retry_after_seconds(self, email: str, ip: str) -> int:
        wait = 0
        if self._count(self._email_key(email)) >= self.settings.login_rate_limit_email_max:
            ttl = self.client.ttl(self._email_key(email))
            if ttl and ttl > 0:
                wait = max(wait, int(ttl))
        if self._count(self._ip_key(ip)) >= self.settings.login_rate_limit_ip_max:
            ttl = self.client.ttl(self._ip_key(ip))
            if ttl and ttl > 0:
                wait = max(wait, int(ttl))
        return wait

    def record_failure(self, email: str, ip: str) -> None:
        for key, window in (
            (self._email_key(email), self._email_window_seconds()),
            (self._ip_key(ip), self._ip_window_seconds()),
        ):
            count = self.client.incr(key)
            if count == 1:
                self.client.expire(key, window)

    def clear_email_failures(self, email: str) -> None:
        self.client.delete(self._email_key(email))


def get_redis_client():
    """Return a process-wide redis client, creating it on first call.

    Created lazily so importing this module does not require REDIS_URL to be
    set (a process that never uses the Redis backend should not care).
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    import redis

    url = os.environ.get("REDIS_URL") or get_settings().redis_url
    if not url:
        raise RuntimeError(
            "RATE_LIMIT_BACKEND=redis requires REDIS_URL to be set. "
            "Example: redis://localhost:6379/0"
        )

    timeout = float(os.environ.get("REDIS_SOCKET_TIMEOUT_SECONDS", "5.0"))
    _redis_client = redis.Redis.from_url(
        url, decode_responses=True, socket_timeout=timeout, socket_connect_timeout=timeout
    )
    log.info("Redis rate limiter initialised (url=%s)", url.rsplit("@", 1)[-1])
    return _redis_client


def reset_redis_client() -> None:
    """Close and forget the cached client. Tests use this between cases."""
    global _redis_client
    if _redis_client is not None:
        try:
            _redis_client.close()
        except Exception:
            pass
    _redis_client = None