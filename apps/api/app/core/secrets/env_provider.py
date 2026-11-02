"""Environment-variable secret provider (M30 default)."""
from __future__ import annotations

import os

from app.core.secrets.base import SecretNotFound, SecretProvider


class EnvSecretProvider(SecretProvider):
    """Reads secrets from environment variables.

    JWT_SECRET falls back to Settings.jwt_secret (which pydantic-settings
    reads from the same .env file). This preserves the exact pre-M30
    behavior where get_settings().jwt_secret was the source of truth.

    Other secret names require an environment variable of that exact name.
    """

    def get(self, name: str) -> str:
        value = os.environ.get(name)
        if value:
            return value
        if name == "JWT_SECRET":
            from app.core.config import get_settings
            return get_settings().jwt_secret
        raise SecretNotFound(f"Secret {name} is not set in the environment")