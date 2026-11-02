"""AWS Secrets Manager secret provider (M30)."""
from __future__ import annotations

import json
import logging
import os

from app.core.secrets.base import SecretNotFound, SecretProvider, SecretProviderError

log = logging.getLogger("bimguard.secrets.aws")


class AWSSecretsManagerProvider(SecretProvider):
    """Reads secrets from AWS Secrets Manager.

    The secret is expected to be a JSON object with the secret fields at the
    top level:
        {"JWT_SECRET": "...", "OTHER_KEY": "..."}
    Get it with the AWS CLI:
        aws secretsmanager get-secret-value --secret-id bimguard/prod \\
            --query SecretString --output text

    A single non-JSON string is accepted for names JWT_SECRET, "value", or
    "secret" so a one-secret-per-value setup works too.

    Authentication uses the standard boto3 credential chain:
      - Instance profile / ECS task role / Lambda role (production)
      - AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY (local dev)
      - AWS_PROFILE + ~/.aws/credentials (local dev)

    Requires: pip install '.[aws]'
    """

    def __init__(self, region: str | None = None, secret_arn: str | None = None) -> None:
        from app.core.config import get_settings
        s = get_settings()
        self._region = region or s.aws_region or os.environ.get("AWS_REGION", "us-east-1")
        self._secret_arn = secret_arn or s.aws_secret_name
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:
                raise SecretProviderError(
                    "AWS Secrets Manager provider requires boto3. "
                    "Install with: pip install '.[aws]'"
                ) from exc
            self._client = boto3.client("secretsmanager", region_name=self._region)
        return self._client

    def get(self, name: str) -> str:
        if not self._secret_arn:
            raise SecretProviderError(
                "AWS Secret ARN not configured. Set AWS_SECRET_NAME in .env, "
                "e.g. AWS_SECRET_NAME=bimguard/prod"
            )
        client = self._get_client()
        try:
            resp = client.get_secret_value(SecretId=self._secret_arn)
        except Exception as exc:  # noqa: BLE001 - aws raises many error types
            raise SecretProviderError(f"AWS Secrets Manager: {exc}") from exc
        raw = resp.get("SecretString")
        if not raw:
            raise SecretNotFound(f"Secret {self._secret_arn} has no SecretString")
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
        except (json.JSONDecodeError, ValueError):
            if name in ("JWT_SECRET", "value", "secret"):
                return raw
            raise SecretProviderError(
                f"Secret {self._secret_arn} is not a JSON object; "
                f"cannot extract field {name}"
            )
        if name not in data:
            raise SecretNotFound(f"Secret {self._secret_arn} has no field {name}")
        return str(data[name])