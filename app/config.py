from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    anthropic_api_key: str = "sk-ant-xxx"
    claude_model: str = "claude-sonnet-4-6"
    gaps_model: str = "claude-sonnet-4-6"
    test_cases_model: str = "claude-sonnet-4-6"
    bugs_model: str = "claude-sonnet-4-6"
    data_dir: str = "./data/projects"
    confluence_base_url: str = ""
    confluence_pat: str = ""
    cors_origins: str = ""

    model_config = SettingsConfigDict(env_file=".env")

    def parsed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def get_settings() -> Settings:
    """Create Settings instance. Useful for testing with dependency override."""
    return Settings()


settings = get_settings()
