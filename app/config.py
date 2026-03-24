from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    anthropic_api_key: str = "sk-ant-xxx"
    claude_model: str = "claude-sonnet-4-6"
    database_url: str = "sqlite+aiosqlite:///./extract_agent.db"
    max_pdf_size_mb: int = 32

    model_config = SettingsConfigDict(env_file=".env")


def get_settings() -> Settings:
    """Create Settings instance. Useful for testing with dependency override."""
    return Settings()


settings = get_settings()
