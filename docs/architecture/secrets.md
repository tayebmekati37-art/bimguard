# Secret provider abstraction (M30)

## KMS vs Secrets Manager vs Key Vault

The milestone is called "KMS integration" in the roadmap, but that name is
imprecise. KMS is the wrong service for a JWT signing secret:

- AWS KMS manages encryption keys. You cannot extract the key material.
  It is the backing store for secrets, not a place to fetch a JWT signing key.
- AWS Secrets Manager stores secrets (like JWT_SECRET) as strings. Encryption
  at rest is done by KMS under the hood. This is what a JWT app fetches.
- Azure Key Vault combines both: it stores secrets AND manages keys.
- Azure Managed HSM is key management only, closer to AWS KMS.

So the honest abstraction is a secret provider, not a KMS provider. This
milestone ships that.

## What ships

- SecretProvider interface: shipped, tested
- EnvSecretProvider (default): shipped, tested
- AWSSecretsManagerProvider: shipped, tested via moto
- AzureKeyVaultProvider: shipped but unverified (no in-process Azure SDK mock)
- Factory with backend switch: shipped, tested
- security.py uses provider via cache: shipped, tested

Default behavior is unchanged. SECRET_PROVIDER=env keeps reading from
environment variables (or Settings.jwt_secret for JWT_SECRET specifically),
which is exactly what pydantic-settings populated from .env before M30.

## Configuration

    # env (default) | aws_secrets_manager | azure_key_vault
    SECRET_PROVIDER=env

    # Cache duration in seconds. Rotating a secret requires waiting this
    # long (or restarting) for the new value to be used.
    SECRET_CACHE_SECONDS=3600

    # AWS Secrets Manager (when SECRET_PROVIDER=aws_secrets_manager)
    AWS_SECRET_NAME=bimguard/prod
    AWS_REGION=us-east-1

    # Azure Key Vault (when SECRET_PROVIDER=azure_key_vault)
    AZURE_VAULT_URL=https://myvault.vault.azure.net/

Install the provider you need:

    pip install -e ".[aws]"

    pip install -e ".[azure]"

Both extras are optional so a deployment that only needs env carries no
cloud SDKs.

## Secret format per provider

EnvSecretProvider: JWT_SECRET is a single environment variable, or falls
back to Settings.jwt_secret. Other secret names must match the exact env
var name.

AWSSecretsManagerProvider: the secret is a JSON object with the secret
fields at the top level.

    {"JWT_SECRET": "...", "OTHER_KEY": "..."}

A single non-JSON string is accepted if the requested name is one of
JWT_SECRET, value, or secret. This supports one-secret-per-value setups.
Get the JSON from the AWS console or:

    aws secretsmanager get-secret-value --secret-id bimguard/prod \
        --query SecretString --output text

AzureKeyVaultProvider: one Key Vault secret per app secret. Key Vault
secret names allow only alphanumerics and dashes; the provider converts
underscores to dashes. JWT_SECRET in the app is JWT-SECRET in the vault.

    az keyvault secret set --vault-name myvault \
        --name JWT-SECRET --value "..."

## Authentication

AWS: standard boto3 credential chain, in order.

1. Instance profile / ECS task role / Lambda role (production)
2. AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY env vars (local dev)
3. AWS_PROFILE + ~/.aws/credentials (local dev)

For production, assign an IAM role to the container or EC2 instance with
secretsmanager:GetSecretValue on the specific secret ARN. Do not store
long-lived AWS credentials in .env.

Azure: DefaultAzureCredential from azure-identity, which tries in order.

1. Environment variables (AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_SECRET)
2. Managed identity (production: assign one to the app)
3. Azure CLI credentials (az login on local dev)
4. Azure PowerShell / Developer CLI

For production, assign a managed identity and grant it Key Vault Secrets
User on the vault.

## Caching

Every secret is fetched through security._get_secret(), which caches the
value for SECRET_CACHE_SECONDS (default 3600). Without the cache, every
JWT sign and verify would call AWS or Azure, and login latency would be
unusable.

Consequence: rotating a secret requires either waiting SECRET_CACHE_SECONDS
or restarting the app. In practice rotating a JWT secret invalidates every
issued token anyway (old tokens fail signature verification), so rotation
is disruptive by design.

Setting SECRET_CACHE_SECONDS=0 disables caching. Only use this with the
env provider; with a remote provider, 0 means every request calls AWS or
Azure.

## Startup behavior

ensure_secret_is_safe() runs at startup and:

1. Fetches JWT_SECRET through the configured provider. If the provider
   fails (AWS unreachable, no ARN configured, boto3 not installed), the
   app refuses to start with a clear error. Without a signing key, the
   app is useless.
2. Checks the value against known defaults. If the secret is the dev
   default and ENVIRONMENT is production or staging, refuse to start.
3. Warns in dev if the secret is still the default.

## Testing

- tests/test_secret_providers.py — env provider, factory dispatch, cache,
  TTL=0 bypass, ensure_secret_is_safe error path, Azure config-only error
- tests/test_aws_secrets_manager.py — AWS provider via moto: JSON field
  extraction, missing field, missing ARN, plain-string fallback, end-to-end
  through _jwt_secret()

moto mocks boto3 in-process. No network, no credentials, deterministic.
Every AWS code path is exercised except a real IAM role assumption, which
only a live deployment can prove.

Azure Key Vault has no test coverage beyond the config-error path. There
is no reliable in-process Azure SDK mock. The provider is shipped, its
error handling is explicit, and it must be verified against a real vault
before any customer-facing deployment.

## What this milestone does NOT provide

- Key rotation tooling. Rotation requires updating the provider store and
  restarting. A graceful JWT rotation with a grace window is out of scope.
- Per-request secret selection. Every JWT uses the same secret.
- Envelope encryption (KMS data-key workflow). See encryption.md.
- AWS KMS Sign/Verify for JWTs. Wrong tool; Secrets Manager is correct.
- Azure Managed HSM. Different service; not implemented.
- Verified Azure integration. Documented above.

## Migration from .env-only

Existing deployments are unaffected. SECRET_PROVIDER=env is the default.
No action required.

To migrate to AWS Secrets Manager:

1. Create the secret:

       aws secretsmanager create-secret --name bimguard/prod \
           --secret-string '{"JWT_SECRET": "<current value>"}'

2. Install the extra:

       pip install -e ".[aws]"

3. Set in .env:

       SECRET_PROVIDER=aws_secrets_manager
       AWS_SECRET_NAME=bimguard/prod
       AWS_REGION=us-east-1

4. Grant the instance or container role secretsmanager:GetSecretValue on
   that ARN.
5. Remove JWT_SECRET from .env, or leave it as a fallback. The provider
   wins.
6. Restart the app.
7. Verify: curl http://localhost:8000/health returns 200 and login works.

To migrate to Azure Key Vault, same steps with az keyvault secret set and
SECRET_PROVIDER=azure_key_vault / AZURE_VAULT_URL=... Verify against a
real vault before relying on it.