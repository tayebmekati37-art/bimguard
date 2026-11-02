"""Tests for the secret provider abstraction (M30)."""
import pytest

from app.core import security
from app.core.config import get_settings
from app.core.secrets import (
    SecretNotFound,
    SecretProviderError,
    get_secret_provider,
    reset_secret_provider,
)
from app.core.secrets.azure_provider import AzureKeyVaultProvider
from app.core.secrets.env_provider import EnvSecretProvider


@pytest.fixture(autouse=True)
def _reset_state():
    reset_secret_provider()
    security.reset_secret_cache()
    yield
    reset_secret_provider()
    security.reset_secret_cache()


# ------------------------------------------------------------------ env provider

def test_env_provider_reads_environment(monkeypatch):
    monkeypatch.setenv("MY_SECRET", "hello")
    assert EnvSecretProvider().get("MY_SECRET") == "hello"


def test_env_provider_falls_back_to_settings_for_jwt_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    assert EnvSecretProvider().get("JWT_SECRET") == get_settings().jwt_secret


def test_env_provider_raises_for_missing_secret():
    with pytest.raises(SecretNotFound):
        EnvSecretProvider().get("NOT_SET_ANYWHERE_xyz_12345")


# ------------------------------------------------------------------ factory

def test_factory_defaults_to_env():
    assert isinstance(get_secret_provider(), EnvSecretProvider)


def test_factory_rejects_unknown_backend(monkeypatch):
    monkeypatch.setattr(get_settings(), "secret_provider", "vault")
    with pytest.raises(SecretProviderError, match="Unknown SECRET_PROVIDER"):
        get_secret_provider()


def test_factory_recreates_when_backend_changes(monkeypatch):
    assert isinstance(get_secret_provider(), EnvSecretProvider)
    monkeypatch.setattr(get_settings(), "secret_provider", "aws_secrets_manager")
    # aws provider will init but may not function without config; type is what matters
    from app.core.secrets.aws_provider import AWSSecretsManagerProvider
    assert isinstance(get_secret_provider(), AWSSecretsManagerProvider)
    monkeypatch.setattr(get_settings(), "secret_provider", "env")
    assert isinstance(get_secret_provider(), EnvSecretProvider)


# ------------------------------------------------------------------ cache

def test_jwt_secret_is_cached_after_first_call(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "cached-test-value")
    assert security._jwt_secret() == "cached-test-value"
    # Change env; cache should still return the old value
    monkeypatch.setenv("JWT_SECRET", "different-value")
    assert security._jwt_secret() == "cached-test-value"


def test_reset_secret_cache_clears_cache(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "value-1")
    assert security._jwt_secret() == "value-1"
    security.reset_secret_cache()
    monkeypatch.setenv("JWT_SECRET", "value-2")
    assert security._jwt_secret() == "value-2"


def test_cache_ttl_zero_disables_caching(monkeypatch):
    """With SECRET_CACHE_SECONDS=0, every call goes to the provider."""
    monkeypatch.setattr(get_settings(), "secret_cache_seconds", 0)
    monkeypatch.setenv("JWT_SECRET", "value-a")
    assert security._jwt_secret() == "value-a"
    monkeypatch.setenv("JWT_SECRET", "value-b")
    assert security._jwt_secret() == "value-b"


# ------------------------------------------------------------------ ensure_secret_is_safe with provider

def test_ensure_secret_fails_clearly_when_provider_unavailable(monkeypatch):
    """If the configured provider cannot deliver JWT_SECRET at startup,
    ensure_secret_is_safe raises RuntimeError with a clear message."""
    monkeypatch.setattr(get_settings(), "secret_provider", "aws_secrets_manager")
    monkeypatch.setattr(get_settings(), "aws_secret_name", "")  # no secret ARN
    reset_secret_provider()
    security.reset_secret_cache()
    with pytest.raises(RuntimeError, match="Could not load JWT_SECRET"):
        security.ensure_secret_is_safe()


# ------------------------------------------------------------------ azure (config-only, no real vault)

def test_azure_provider_raises_without_azure_sdk():
    """Without azure-identity/azure-keyvault-secrets installed (the default),
    the provider raises a clear message telling the user to install '.[azure]'."""
    p = AzureKeyVaultProvider(vault_url="https://example.vault.azure.net/")
    with pytest.raises(SecretProviderError, match="azure"):
        p.get("JWT_SECRET")


@pytest.mark.skip(reason="Azure Key Vault integration requires a real vault; verified manually in deployment")
def test_azure_provider_reads_real_secret():
    pass