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
    return jwt.encode(payload, s.jwt_secret, s.jwt_algorithm)


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

_VALID_ENCRYPTION_MODES = frozenset({"none", "infrastructure"})


def ensure_encryption_declared() -> None:
    """Verify the operator has made an explicit encryption decision.

    Does not encrypt anything. Ensures that in production the operator
    has acknowledged responsibility for at-rest encryption by setting
    ENCRYPTION_MODE=infrastructure. Fails hard in production if the mode
    is left at the development default.
    """
    s = get_settings()
    env = s.environment.lower().strip()
    mode = (s.encryption_mode or "").lower().strip()

    if mode not in _VALID_ENCRYPTION_MODES:
        raise RuntimeError(
            f"ENCRYPTION_MODE='{s.encryption_mode}' is not a recognised value. "
            f"Set to one of: {', '.join(sorted(_VALID_ENCRYPTION_MODES))}. "
            "See docs/architecture/encryption.md."
        )

    is_prod = env in ("production", "prod", "staging")

    if is_prod and mode == "none":
        raise RuntimeError(
            "ENCRYPTION_MODE is 'none' but ENVIRONMENT is production/staging. "
            "Configure disk-level or database-level encryption, then set "
            "ENCRYPTION_MODE=infrastructure. See docs/architecture/encryption.md."
        )

    if mode == "infrastructure":
        log.info(
            "ENCRYPTION_MODE=infrastructure (operator has declared at-rest encryption). "
            "The application does not verify this. See docs/architecture/encryption.md."
        )
    elif not is_prod:
        log.warning(
            "ENCRYPTION_MODE is 'none' (development default). "
            "Data on disk is not encrypted. Set ENCRYPTION_MODE=infrastructure "
            "and configure disk-level encryption before deploying."
        )