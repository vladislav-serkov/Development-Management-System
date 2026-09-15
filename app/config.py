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
    # Test stand base URL for executing curl artifacts (empty = feature off).
    # Requests go to {test_stand_url}/{service_name}{path} — service name comes
    # from the feature's source document.
    test_stand_url: str = ""
    confluence_base_url: str = ""
    confluence_pat: str = ""
    # Jira DC integration for exporting bug reports as issues (empty = feature off).
    # The PAT is a *Jira* personal access token — a Confluence PAT is not accepted.
    jira_base_url: str = ""
    jira_pat: str = ""
    jira_project_key: str = "MTSPAY"
    jira_issue_type: str = "Bug"
    # Required MTSPAY custom fields (empty = omit the field on create):
    jira_bug_type: str = "Feature testing"  # customfield_10519 (radio)
    jira_system: str = "UMP"  # customfield_10523 (multiselect)
    jira_team: str = "Flex core"  # customfield_20600 (multiselect)
    # Optional fields the team fills on every bug (empty = omit):
    jira_developer: str = ""  # ОР, customfield_10402 (multiuserpicker) — Jira login
    jira_fix_version: str = ""  # Fix Version/s — current release name, update per release
    jira_board_id: int = 1880  # agile board whose active sprint lands in Спринт (0 = off)
    # Bug fixer: headless Claude Code runs that fix exported bugs in the service repos.
    # Auth is a subscription OAuth token from `claude setup-token` (empty = feature off).
    claude_code_oauth_token: str = ""
    claude_cli: str = "claude"
    # Anthropic API is reached through a local SSH tunnel (same as the user's shell wrapper)
    claude_proxy: str = "http://127.0.0.1:8888"
    claude_proxy_ssh_host: str = "claude-proxy"
    # Roots where service repos live; a service name must match a directory name
    repos_dirs: str = "~/IdeaProjects:~/IdeaProjects/flp"
    bug_fixer_auto: bool = True  # enqueue a fix as soon as a bug is exported to Jira
    bug_fix_timeout_seconds: int = 3600
    bug_fix_log_dir: str = "logs/bug-fixer"
    # Autotest generator: headless Claude Code runs that turn accepted test cases
    # into Java autotests in the flp-autotests repo (empty dir = feature off).
    # Shares the Claude Code auth/proxy/timeout settings with the bug fixer.
    autotests_repo_dir: str = ""
    autotest_auto: bool = True  # queue generation as soon as a test case is approved
    autotest_log_dir: str = "logs/autotest-gen"
    cors_origins: str = ""

    model_config = SettingsConfigDict(env_file=".env")

    def parsed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def get_settings() -> Settings:
    """Create Settings instance. Useful for testing with dependency override."""
    return Settings()


settings = get_settings()
