from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    database_url: str
    redis_url: str
    session_secret: str
    app_password_hash: str
    anthropic_api_key: str = ""
    llm_model: str = ""
    google_service_account_json_path: str = "/run/secrets/service-account.json"
    data_dir: str = "/data"
    app_timezone: str = "Asia/Kolkata"
    next_public_api_url: str = "http://localhost:8000/api"
    playwright_browsers_path: str = "/ms-playwright"

    @field_validator("session_secret")
    @classmethod
    def validate_secret(cls, value: str) -> str:
        if len(value) < 32 or value.startswith("replace-"):
            raise ValueError("SESSION_SECRET must be a random secret of at least 32 characters")
        return value

    @field_validator("app_password_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        from app.security import valid_password_hash
        if not valid_password_hash(value):
            raise ValueError("APP_PASSWORD_HASH must be a generated PBKDF2 hash; see README")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
