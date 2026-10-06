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


@lru_cache
def get_settings() -> Settings:
    return Settings()
