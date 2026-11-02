"""Secret provider abstraction (M30).

The application loads secrets (JWT_SECRET, and any future secret) through
a SecretProvider rather than reading environment variables directly. This
lets a deployment source secrets from AWS Secrets Manager or Azure Key
Vault without changing application code.

Default: EnvSecretProvider reads os.environ (or Settings.jwt_secret for
JWT_SECRET specifically), preserving pre-M30 behavior exactly.

See docs/architecture/secrets.md for the full design and the KMS vs
Secrets Manager vs Key Vault distinction.
"""
from app.core.secrets.base import SecretNotFound, SecretProvider, SecretProviderError
from app.core.secrets.factory import get_secret_provider, reset_secret_provider

__all__ = [
    "SecretProvider",
    "SecretProviderError",
    "SecretNotFound",
    "get_secret_provider",
    "reset_secret_provider",
]