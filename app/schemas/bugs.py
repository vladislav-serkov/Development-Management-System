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


class BugGenerateRequest(BaseModel):
    """POST /generate request body."""
    tc_index: int
    analyst_text: str | None = None


class BugPatchRequest(BaseModel):
    """PATCH /{bug_index} request body."""
    status: str = Field(pattern="^(open|fixed|verified)$")
    analyst_text: str | None = None
