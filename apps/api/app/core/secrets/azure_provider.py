"""Azure Key Vault secret provider (M30).

Shipped but unverified: there is no good in-process mock for the Azure SDK.
Verified manually per deployment. See docs/architecture/secrets.md.
"""
from __future__ import annotations

import logging
import os

from app.core.secrets.base import SecretNotFound, SecretProvider, SecretProviderError

log = logging.getLogger("bimguard.secrets.azure")


class AzureKeyVaultProvider(SecretProvider):
    """Reads secrets from Azure Key Vault.

    Key Vault secret names allow only alphanumerics and dashes. The provider
    converts underscores to dashes: JWT_SECRET in the app becomes JWT-SECRET
    in the vault.

    Authentication uses DefaultAzureCredential, which works with:
      - Managed identity (production: assign one to the app)
      - Azure CLI (`az login` on local dev)
      - AZURE_CLIENT_ID / AZURE_TENANT_ID / AZURE_CLIENT_SECRET env vars

    Set AZURE_VAULT_URL, e.g. https://myvault.vault.azure.net/

    Requires: pip install '.[azure]'
    """

    def __init__(self, vault_url: str | None = None) -> None:
        from app.core.config import get_settings
        s = get_settings()
        self._vault_url = vault_url or s.azure_vault_url or os.environ.get("AZURE_VAULT_URL")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from azure.identity import DefaultAzureCredential
                from azure.keyvault.secrets import SecretClient
            except ImportError as exc:
                raise SecretProviderError(
                    "Azure Key Vault provider requires azure-identity and "
                    "azure-keyvault-secrets. Install with: pip install '.[azure]'"
                ) from exc
            if not self._vault_url:
                raise SecretProviderError(
                    "AZURE_VAULT_URL is not set, e.g. "
                    "AZURE_VAULT_URL=https://myvault.vault.azure.net/"
                )
            self._client = SecretClient(
                vault_url=self._vault_url,
                credential=DefaultAzureCredential(),
            )
        return self._client

    def get(self, name: str) -> str:
        client = self._get_client()
        vault_name = name.replace("_", "-")
        try:
            secret = client.get_secret(vault_name)
        except Exception as exc:  # noqa: BLE001
            raise SecretProviderError(f"Azure Key Vault: {exc}") from exc
        if not secret.value:
            raise SecretNotFound(f"Secret {vault_name} has no value")
        return secret.value