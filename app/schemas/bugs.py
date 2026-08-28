from typing import Literal

from pydantic import BaseModel, Field


class BugStep(BaseModel):
    """A single reproduction step with optional technical artifacts."""
    action: str
    result: str
    curl_command: str | None = None
    sql_query: str | None = None
    kafka_message: str | None = None


class BugReportResult(BaseModel):
    """Claude tool output schema for bug report generation."""
    title: str
    severity: Literal["critical", "major", "minor", "trivial"]
    steps: list[BugStep]
    expected_result: str
    actual_result: str


class BugItem(BaseModel):
    """Single bug report stored in features/{name}/bugs.json."""
    title: str
    test_case_name: str
    severity: Literal["critical", "major", "minor", "trivial"]
    steps: list[BugStep]
    expected_result: str
    actual_result: str
    status: str = "open"  # "open" | "fixed" | "verified"
    analyst_text: str | None = None
    created_at: str
    # Set once the bug is exported to Jira; jira_status mirrors the live issue status
    jira_key: str | None = None
    jira_url: str | None = None
    jira_status: str | None = None
    # Bug fixer (headless Claude Code run in the service repo)
    fix_status: str | None = None  # "queued" | "running" | "fix_proposed" | "failed"
    fix_service: str | None = None
    fix_branch: str | None = None
    fix_mr_url: str | None = None
    fix_summary: str | None = None
    fix_error: str | None = None
    fix_log: str | None = None
    fix_requested_at: str | None = None
    fix_started_at: str | None = None
    fix_finished_at: str | None = None


class BugGenerateRequest(BaseModel):
    """POST /generate request body."""
    tc_index: int
    analyst_text: str | None = None


class BugExportRequest(BaseModel):
    """POST /{bug_index}/export-jira request body."""
    feature_ticket: str | None = None  # Feature Link — key of the feature epic being tested


class BugPatchRequest(BaseModel):
    """PATCH /{bug_index} request body."""
    status: str = Field(pattern="^(open|fixed|verified)$")
    analyst_text: str | None = None
