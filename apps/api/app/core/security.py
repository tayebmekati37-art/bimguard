import logging
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

log = logging.getLogger("bimguard.security")

# Secrets shipped as defaults in config.py. Refuse to start in production
# with one of these; warn loudly everywhere else.
_KNOWN_DEFAULT_SECRETS = {
    "dev-only-secret-change-me-use-at-least-32-bytes",
}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(subject: str, role: str) -> str:
    s = get_settings()
    exp = datetime.now(UTC) + timedelta(minutes=s.jwt_expire_minutes)
    return jwt.encode(
        {
            "sub": subject,
            "role": role,
            "exp": exp,
            "jti": uuid.uuid4().hex,
        },
        s.jwt_secret,
        s.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])


def ensure_secret_is_safe() -> None:
    """Fail fast if a default JWT secret reaches production.

    Called once at app startup. In development the default is fine and we log
    a single warning. In production it is a hard error: a known secret means
    anyone can forge tokens.
    """
    s = get_settings()
    uses_default = s.jwt_secret in _KNOWN_DEFAULT_SECRETS
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