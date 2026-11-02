"""Tests for the AWS Secrets Manager provider (M30), using moto."""
import json

import pytest

try:
    from moto import mock_aws
except ImportError:
    pytest.skip("moto not installed; run pip install -e '.[dev]'", allow_module_level=True)


@pytest.fixture
def aws_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def aws_secret(aws_credentials):
    with mock_aws():
        import boto3
        client = boto3.client("secretsmanager", region_name="us-east-1")
        client.create_secret(
            Name="bimguard/test",
            SecretString=json.dumps({
                "JWT_SECRET": "aws-test-secret-value",
                "OTHER_KEY": "other-value",
            }),
        )
        yield client


def test_aws_provider_reads_json_field(aws_secret):
    from app.core.secrets.aws_provider import AWSSecretsManagerProvider
    p = AWSSecretsManagerProvider(region="us-east-1", secret_arn="bimguard/test")
    assert p.get("JWT_SECRET") == "aws-test-secret-value"
    assert p.get("OTHER_KEY") == "other-value"


def test_aws_provider_raises_on_missing_field(aws_secret):
    from app.core.secrets.aws_provider import AWSSecretsManagerProvider
    from app.core.secrets.base import SecretNotFound
    p = AWSSecretsManagerProvider(region="us-east-1", secret_arn="bimguard/test")
    with pytest.raises(SecretNotFound):
        p.get("NOT_IN_SECRET")


def test_aws_provider_raises_without_secret_arn(monkeypatch):
    from app.core.config import get_settings
    from app.core.secrets.aws_provider import AWSSecretsManagerProvider
    from app.core.secrets.base import SecretProviderError
    monkeypatch.setattr(get_settings(), "aws_secret_name", "")
    p = AWSSecretsManagerProvider(region="us-east-1", secret_arn="")
    with pytest.raises(SecretProviderError, match="AWS Secret ARN not configured"):
        p.get("JWT_SECRET")


def test_aws_provider_accepts_plain_string_for_jwt(aws_credentials):
    with mock_aws():
        import boto3
        client = boto3.client("secretsmanager", region_name="us-east-1")
        client.create_secret(Name="bimguard/plain", SecretString="plain-secret-value")
        from app.core.secrets.aws_provider import AWSSecretsManagerProvider
        p = AWSSecretsManagerProvider(region="us-east-1", secret_arn="bimguard/plain")
        assert p.get("JWT_SECRET") == "plain-secret-value"


def test_aws_provider_end_to_end_via_factory(aws_secret, monkeypatch):
    """Setting SECRET_PROVIDER=aws_secrets_manager routes JWT_SECRET through AWS."""
    from app.core import security
    from app.core.config import get_settings
    from app.core.secrets import reset_secret_provider

    monkeypatch.setattr(get_settings(), "secret_provider", "aws_secrets_manager")
    monkeypatch.setattr(get_settings(), "aws_secret_name", "bimguard/test")
    monkeypatch.setattr(get_settings(), "aws_region", "us-east-1")
    reset_secret_provider()
    security.reset_secret_cache()

    assert security._jwt_secret() == "aws-test-secret-value"