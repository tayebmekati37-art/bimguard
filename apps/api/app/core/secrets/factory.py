"""Secret provider factory (M30).

Cached by backend name so tests that change SECRET_PROVIDER between cases
do not leak state. Change SECRET_PROVIDER and restart in production; there
is no hot reload.
"""
from __future__ import annotations

import logging

from app.core.secrets.base import SecretProvider, SecretProviderError

log = logging.getLogger("bimguard.secrets")

_provider_cache: tuple[str, SecretProvider] | None = None


def get_secret_provider() -> SecretProvider:
    global _provider_cache
    from app.core.config import get_settings
    name = (get_settings().secret_provider or "env").lower().strip()

    if _provider_cache is not None and _provider_cache[0] == name:
        return _provider_cache[1]

    if name in ("", "env"):
        from app.core.secrets.env_provider import EnvSecretProvider
        provider: SecretProvider = EnvSecretProvider()
    elif name == "aws_secrets_manager":
        from app.core.secrets.aws_provider import AWSSecretsManagerProvider
        provider = AWSSecretsManagerProvider()
    elif name == "azure_key_vault":
        from app.core.secrets.azure_provider import AzureKeyVaultProvider
        provider = AzureKeyVaultProvider()
    else:
        raise SecretProviderError(
            f"Unknown SECRET_PROVIDER={name!r}. "
            "Valid values: env, aws_secrets_manager, azure_key_vault"
        )

    log.info("Secret provider initialised: %s (backend=%s)", provider.name, name)
    _provider_cache = (name, provider)
    return provider


def reset_secret_provider() -> None:
    """Forget the cached provider. Used by tests."""
    global _provider_cache
    _provider_cache = None