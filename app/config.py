from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    anthropic_api_key: str = "sk-ant-xxx"
    claude_model: str = "claude-sonnet-5"
    gaps_model: str = "claude-sonnet-5"
    test_cases_model: str = "claude-sonnet-5"
    bugs_model: str = "claude-sonnet-5"
    # Feature detection of a large spec easily emits >16K output tokens; a truncated
    # tool_use block arrives as an empty/partial input and looks like "Claude found
    # nothing". Sonnet allows far larger outputs, so keep a generous ceiling.
    extraction_max_tokens: int = 32000
    database_url: str = "postgresql+asyncpg://extract:extract@localhost:5432/extract_agent"
    # Test stand DB for executing SQL artifacts from test cases (empty = feature off).
    # Artifacts are generated with explicit schema prefixes (schema == service name),
    # so no search_path is needed.
    test_db_url: str = ""
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
