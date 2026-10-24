from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate repository root (.env) regardless of current working directory
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DOTENV_PATH = REPO_ROOT / ".env"


class Settings(BaseSettings):
    app_name: str = "AI Voice Platform"
    app_env: str = "development"
    log_level: str = "INFO"
    frontend_url: str = "http://localhost:3000"
    gemini_api_key: str = "placeholder-local-dev-key"
    gemini_model: str = "gemini-2.5-flash"
    database_url: str = (
        "postgresql+psycopg://voice_app:change-me-local-only@localhost:5432/voice_platform"
    )
    redis_url: str | None = None
    external_request_timeout_seconds: float = 15.0
    llm_request_timeout_seconds: float = 30.0

    model_config = SettingsConfigDict(
        env_file=(str(DOTENV_PATH), ".env", "../.env"),
        extra="ignore",
    )


settings = Settings()

