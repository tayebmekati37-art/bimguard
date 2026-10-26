from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./bimguard_dev.db"
    jwt_secret: str = "dev-only-secret-change-me-use-at-least-32-bytes"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    environment: str = "development"
    log_level: str = "INFO"
    ai_enabled: bool = False
    storage_dir: str = "./storage"
    max_upload_mb: int = 50

    # Login rate limiting (M19b). Only failed attempts are counted.
    # Successful login clears recent failures for that email.
    login_rate_limit_email_max: int = 5
    login_rate_limit_email_window_minutes: int = 15
    login_rate_limit_ip_max: int = 20
    login_rate_limit_ip_window_minutes: int = 15

    # Trust X-Forwarded-For only when running behind a trusted reverse proxy.
    # Do not enable this if the API is directly reachable from the internet,
    # because the header can be forged by the client.
    trust_proxy_headers: bool = False

    # Encryption at rest (M24). The application does NOT encrypt data itself.
    # This setting records the operator's explicit decision so the app can
    # refuse to start in production when the operator has not made one.
    #
    #   none             dev-only default. No encryption guaranteed.
    #   infrastructure   operator certifies disk-level or database-level
    #                    encryption is configured (BitLocker, LUKS, RDS
    #                    encryption, encrypted Docker volume, etc).
    #
    # In production/staging, ENCRYPTION_MODE must be set to "infrastructure";
    # "none" causes a hard startup failure. See docs/architecture/encryption.md.
    encryption_mode: str = "none"
    # Backup (M20). Operations, not guarantees.
    # backup_dir defaults to <storage_dir>/backups when None.
    backup_dir: str | None = None
    # Retention: documented for operators. Not enforced by code; deleting
    # backups is a policy decision, not an application action.
    backup_retention_days: int = 30
    # Where to find pg_dump when POST /admin/backup/native runs against
    # Postgres. Empty by default: the API container does not ship
    # postgresql-client, so the endpoint returns 501 with the correct
    # docker command instead.
    pg_dump_path: str = "pg_dump"


@lru_cache
def get_settings() -> Settings:
    return Settings()
