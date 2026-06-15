from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = Field(default="sqlite:///./platform.db")

    OPENAI_API_KEY: str | None = Field(default=None)
    ANTHROPIC_API_KEY: str | None = Field(default=None)
    GEMINI_API_KEY: str | None = Field(default=None)

    GITHUB_WEBHOOK_SECRET: str | None = Field(default=None)

    APP_NAME: str = Field(default="Multi-Agent Orchestration Platform")
    APP_VERSION: str = Field(default="0.1.0")
    ENVIRONMENT: str = Field(default="development")


settings = Settings()
