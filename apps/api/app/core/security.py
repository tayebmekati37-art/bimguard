import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from threading import Lock

import bcrypt
import jwt

from app.core.config import get_settings

log = logging.getLogger("bimguard.security")

# Secrets shipped as defaults in config.py. Refuse to start in production
# with one of these; warn loudly everywhere else.
_KNOWN_DEFAULT_SECRETS = {
    "dev-only-secret-change-me-use-at-least-32-bytes",
}

# In-process cache for secrets fetched from the configured provider. Only
# the configured provider matters; get_settings() is lru_cached so the
# backend does not change at runtime.
_SECRET_CACHE: dict[str, tuple[str, float]] = {}
_SECRET_CACHE_LOCK = Lock()


def reset_secret_cache() -> None:
    """Forget all cached secrets. Used by tests and rotation tooling."""
    with _SECRET_CACHE_LOCK:
        _SECRET_CACHE.clear()


def _get_secret(name: str) -> str:
    """Fetch a secret through the configured provider, with TTL cache.

    Env provider reads are cheap; AWS/Azure reads are not. Caching here means
    JWT sign/verify does not call AWS or Azure on the hot path.
    """
    from app.core.secrets import SecretProviderError, get_secret_provider

    with _SECRET_CACHE_LOCK:
        cached = _SECRET_CACHE.get(name)
        now = time.monotonic()
        if cached is not None and now < cached[1]:
            return cached[0]

    provider = get_secret_provider()
    value = provider.get(name)

    ttl = max(0, get_settings().secret_cache_seconds)
    with _SECRET_CACHE_LOCK:
        _SECRET_CACHE[name] = (value, time.monotonic() + ttl if ttl > 0 else 0.0)
    return value


def _jwt_secret() -> str:
    return _get_secret("JWT_SECRET")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(subject: str, role: str, family_id: str | None = None) -> str:
    s = get_settings()
    exp = datetime.now(UTC) + timedelta(minutes=s.jwt_expire_minutes)
    payload = {
        "sub": subject,
        "role": role,
        "exp": exp,
        "jti": uuid.uuid4().hex,
    }
    if family_id:
        # M33: ties the access token to its refresh family so /auth/sessions
        # can mark this device as the current one. Optional for backward
        # compatibility with callers that only need the jti.
        payload["fam"] = family_id
    return jwt.encode(payload, _jwt_secret(), s.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, _jwt_secret(), algorithms=[s.jwt_algorithm])


def ensure_secret_is_safe() -> None:
    """Fail fast if a default JWT secret reaches production.

    Called once at app startup. In development the default is fine and we log
    a single warning. In production it is a hard error: a known secret means
    anyone can forge tokens.

    Also fails if the configured secret provider cannot deliver JWT_SECRET
    at startup. Without a signing key, the app is useless; failing to start
    with a clear error is better than starting and then rejecting every
    request.
    """
    from app.core.secrets import SecretProviderError

    s = get_settings()

    try:
        secret = _jwt_secret()
    except SecretProviderError as exc:
        raise RuntimeError(
            f"Could not load JWT_SECRET from "
            f"SECRET_PROVIDER={s.secret_provider!r}: {exc}"
        ) from exc

    uses_default = secret in _KNOWN_DEFAULT_SECRETS
    if not uses_default:
        return
    env = s.environment.lower()
    if env in ("production", "prod", "staging"):
        raise RuntimeError(
            "JWT_SECRET is set to a known default value. "
            f"Refusing to start with environment='{s.environment}'. "
            "Set JWT_SECRET to a random 32+ byte value before deploying."
        )
    log.warning(
        "JWT_SECRET is the development default. This is fine locally; "
        "set JWT_SECRET before deploying to any shared environment."
    )

_VALID_ENCRYPTION_MODES = frozenset({"none", "infrastructure"})


def ensure_encryption_declared() -> None:
    """Verify the operator made an explicit encryption decision (M24).

    Does not encrypt. In production/staging, refuses to start unless
    ENCRYPTION_MODE=infrastructure is set. See docs/architecture/encryption.md.
    """
    s = get_settings()
    env = s.environment.lower().strip()
    mode = (s.encryption_mode or "").lower().strip()
    if mode not in _VALID_ENCRYPTION_MODES:
        raise RuntimeError(
            f"ENCRYPTION_MODE='{s.encryption_mode}' not recognised. "
            f"Set one of: {', '.join(sorted(_VALID_ENCRYPTION_MODES))}. "
            "See docs/architecture/encryption.md."
        )
    is_prod = env in ("production", "prod", "staging")
    if is_prod and mode == "none":
        raise RuntimeError(
            "ENCRYPTION_MODE is 'none' but ENVIRONMENT is production/staging. "
            "Configure disk or database encryption, then set "
            "ENCRYPTION_MODE=infrastructure."
        )
    if mode == "infrastructure":
        log.info("ENCRYPTION_MODE=infrastructure (operator declaration). See docs/architecture/encryption.md.")
    elif not is_prod:
        log.warning("ENCRYPTION_MODE='none' (development default). Data on disk is not encrypted.")
